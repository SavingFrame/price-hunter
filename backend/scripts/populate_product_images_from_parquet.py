#!/usr/bin/env python3
"""Populate product.image_url and product aliases from an Open Food Facts Parquet export.

Run from the repository root:

    uvx --with duckdb python backend/scripts/populate_product_images_from_parquet.py \
        ./food.parquet --db ./backend/app.db

By default, only products with a missing image_url or Open Food Facts alias are updated
and a SQLite backup is created next to the database before writing.
"""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

import duckdb

OPENFOODFACTS_IMAGE_BASE_URL = "https://images.openfoodfacts.org/images/products"
ALIAS_NAME_LANGUAGE_PRIORITY = ("hr", "main", "en")


LANGUAGE_PRIORITY = {
    "hr": 0,
    "en": 1,
    "cs": 2,
    "fr": 3,
    "de": 4,
    "es": 5,
    "it": 6,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate product.image_url and product aliases from an "
            "Open Food Facts Parquet file."
        )
    )
    parser.add_argument("parquet", type=Path, help="Path to Open Food Facts parquet file")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("backend/app.db"),
        help="Path to SQLite database. Default: backend/app.db",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Update products even when image_url or Open Food Facts alias exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute matches but do not update the database.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a SQLite backup before updating.",
    )
    return parser.parse_args()


def openfoodfacts_product_path(code: str) -> str:
    code = code.strip()
    if len(code) <= 3:
        return code
    groups = [code[index : index + 3] for index in range(0, len(code) - 4, 3)]
    groups.append(code[len(code) - 4 :])
    return "/".join(groups)


def image_language(key: str) -> str:
    parts = key.rsplit("_", 1)
    return parts[1] if len(parts) == 2 else ""


def image_sort_key(image: dict[str, Any]) -> tuple[int, int, int, str]:
    key = str(image.get("key") or "")
    sizes = image.get("sizes") or {}
    language = image_language(key)
    has_400 = int(bool(sizes.get("400")))
    has_full = int(bool(sizes.get("full")))
    return (
        LANGUAGE_PRIORITY.get(language, 99),
        -has_400,
        -has_full,
        key,
    )


def select_image_url(code: str, images: list[dict[str, Any]] | None) -> str | None:
    if not images:
        return None

    front_images = [
        image
        for image in images
        if str(image.get("key") or "").startswith("front_") and image.get("rev")
    ]
    if not front_images:
        return None

    selected = sorted(front_images, key=image_sort_key)[0]
    key = selected["key"]
    rev = selected["rev"]
    product_path = openfoodfacts_product_path(code)
    return f"{OPENFOODFACTS_IMAGE_BASE_URL}/{product_path}/{key}.{rev}.400.jpg"


def select_alias_name(
    product_names: list[dict[str, Any]] | None,
) -> str | None:
    if not product_names:
        return None

    names_by_language: dict[str, str] = {}
    for product_name in product_names:
        language = str(product_name.get("lang") or "")
        text = str(product_name.get("text") or "").strip()
        if language and text and language not in names_by_language:
            names_by_language[language] = text[:255]

    for language in ALIAS_NAME_LANGUAGE_PRIORITY:
        name = names_by_language.get(language)
        if name:
            return name

    return None


def load_products_to_enrich(
    sqlite_connection: sqlite3.Connection,
    overwrite: bool,
) -> dict[str, dict[str, Any]]:
    where_clause = "barcode IS NOT NULL"
    if not overwrite:
        where_clause += (
            " AND ((product.image_url IS NULL OR product.image_url = '') "
            "OR NOT EXISTS ("
            "SELECT 1 FROM productalias "
            "WHERE productalias.product_id = product.id "
            "AND productalias.source = 'openfoodfacts'))"
        )

    rows = sqlite_connection.execute(
        f"""
        SELECT product.id, product.barcode, product.image_url,
            EXISTS (
                SELECT 1
                FROM productalias
                WHERE productalias.product_id = product.id
                    AND productalias.source = 'openfoodfacts'
            ) AS has_openfoodfacts_alias
        FROM product
        WHERE {where_clause}
        """
    ).fetchall()
    return {
        str(barcode): {
            "id": str(product_id),
            "barcode": str(barcode),
            "needs_image": overwrite or not image_url,
            "needs_alias": overwrite or not has_openfoodfacts_alias,
        }
        for product_id, barcode, image_url, has_openfoodfacts_alias in rows
        if barcode
    }


def find_product_enrichments(
    parquet_path: Path,
    products_by_barcode: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    if not products_by_barcode:
        return {}

    duckdb_connection = duckdb.connect()
    duckdb_connection.execute("CREATE TEMP TABLE target_barcodes(barcode VARCHAR)")
    duckdb_connection.executemany(
        "INSERT INTO target_barcodes VALUES (?)",
        [(barcode,) for barcode in products_by_barcode],
    )

    rows = duckdb_connection.execute(
        """
        SELECT parquet.code, parquet.images, parquet.product_name
        FROM read_parquet(?) AS parquet
        INNER JOIN target_barcodes AS target
            ON parquet.code = target.barcode
        WHERE parquet.images IS NOT NULL OR parquet.product_name IS NOT NULL
        """,
        [str(parquet_path)],
    ).fetchall()

    enrichments: dict[str, dict[str, str]] = {}
    for code, images, product_names in rows:
        product = products_by_barcode[code]
        product_enrichment: dict[str, str] = {}

        if product["needs_image"]:
            image_url = select_image_url(code, images)
            if image_url:
                product_enrichment["image_url"] = image_url

        if product["needs_alias"]:
            alias_name = select_alias_name(product_names)
            if alias_name:
                product_enrichment["alias_name"] = alias_name

        if product_enrichment:
            enrichments[product["id"]] = product_enrichment

    return enrichments


def create_backup(db_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_suffix(f".before-product-enrichment-{timestamp}.db")
    shutil.copy2(db_path, backup_path)
    return backup_path


def main() -> None:
    args = parse_args()
    parquet_path = args.parquet.resolve()
    db_path = args.db.resolve()

    if not parquet_path.exists():
        raise SystemExit(f"Parquet file does not exist: {parquet_path}")
    if not db_path.exists():
        raise SystemExit(f"SQLite database does not exist: {db_path}")

    sqlite_connection = sqlite3.connect(db_path)
    products_by_barcode = load_products_to_enrich(
        sqlite_connection=sqlite_connection,
        overwrite=args.overwrite,
    )
    print(f"Products considered: {len(products_by_barcode)}")

    enrichments = find_product_enrichments(
        parquet_path=parquet_path,
        products_by_barcode=products_by_barcode,
    )
    image_count = sum("image_url" in enrichment for enrichment in enrichments.values())
    alias_name_count = sum("alias_name" in enrichment for enrichment in enrichments.values())
    print(f"Matching image URLs found: {image_count}")
    print(f"Matching alias names found: {alias_name_count}")

    for product_id, enrichment in list(enrichments.items())[:10]:
        print(f"  {product_id}: {enrichment}")

    if args.dry_run:
        print("Dry run complete. No database rows were updated.")
        return

    if enrichments and not args.no_backup:
        backup_path = create_backup(db_path)
        print(f"Backup created: {backup_path}")

    updated = 0
    aliases_inserted = 0
    for product_id, enrichment in enrichments.items():
        if image_url := enrichment.get("image_url"):
            cursor = sqlite_connection.execute(
                "UPDATE product SET image_url = ? WHERE id = ?",
                [image_url, product_id],
            )
            updated += cursor.rowcount

        if alias_name := enrichment.get("alias_name"):
            normalized_alias_name = " ".join(alias_name.strip().lower().split())
            cursor = sqlite_connection.execute(
                """
                INSERT OR IGNORE INTO productalias (
                    id,
                    product_id,
                    alias_name,
                    normalized_alias_name,
                    source,
                    confidence,
                    first_seen_at,
                    last_seen_at
                )
                VALUES (lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2)))
                    || '-' || lower(hex(randomblob(2))) || '-' || lower(hex(randomblob(2)))
                    || '-' || lower(hex(randomblob(6))), ?, ?, ?, 'openfoodfacts',
                    0.8000, datetime('now'), datetime('now'))
                """,
                [product_id, alias_name, normalized_alias_name],
            )
            aliases_inserted += cursor.rowcount

    sqlite_connection.commit()
    sqlite_connection.close()
    print(f"Product rows updated: {updated}")
    print(f"Aliases inserted: {aliases_inserted}")


if __name__ == "__main__":
    main()
