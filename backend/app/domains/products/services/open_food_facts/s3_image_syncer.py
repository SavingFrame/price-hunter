import gzip
import tempfile
from collections.abc import Generator
from pathlib import Path

import httpx
from psycopg import sql
from sqlmodel import Column, Session, SQLModel, String, Table, func, select, update

from app.domains.products.models import Product


class S3ImageSyncer:
    CHUNK_SIZE = 10000
    KEYS_FILE_URL = (
        "https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/data/data_keys.gz"
    )

    def __init__(self):
        self.file_path = None

    def download_keys(self) -> None:
        response = httpx.get(self.KEYS_FILE_URL)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(response.content)
            self.file_path = Path(f.name)

    def create_temporary_table(self, session: Session) -> Table:
        table = Table(
            "openfoodfacts_image_staging",
            SQLModel.metadata,
            Column("barcode_13", String(255), nullable=False),
            Column("image_url", String(255), nullable=False),
            prefixes=["TEMPORARY"],
            postgresql_on_commit="DROP",
        )
        table.create(session.connection(), checkfirst=True)
        return table

    def copy_pictures_to_temp_table(self, session: Session, table: Table) -> None:
        batch = []
        for barcode_13, image_url in self._iterate_file():
            batch.append((barcode_13, image_url))
            if len(batch) >= self.CHUNK_SIZE:
                self._flush_batch(session, table, batch)
                batch.clear()
        self._flush_batch(session, table, batch)

    def update_product_images(self, session: Session, staging_table: Table) -> None:
        best_image_by_barcode = (
            select(
                staging_table.c.barcode_13,
                func.min(staging_table.c.image_url).label("image_url"),
            )
            .where(staging_table.c.image_url.endswith(".400.jpg"))
            .group_by(staging_table.c.barcode_13)
            .subquery()
        )

        barcode_13 = func.lpad(Product.barcode, 13, "0")
        statement = (
            update(Product)
            .where(Product.barcode.is_not(None))
            .where(Product.image_url.is_(None))
            .where(barcode_13 == best_image_by_barcode.c.barcode_13)
            .values(image_url=best_image_by_barcode.c.image_url)
        )
        session.exec(statement)

    def _flush_batch(
        self, session: Session, table: Table, batch: list[tuple[str, str]]
    ):
        cursor = session.connection().connection.cursor()
        with cursor.copy(
            sql.SQL(
                "COPY {} (barcode_13, image_url) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t')"
            ).format(sql.Identifier(table.name))
        ) as copy:
            for record in batch:
                copy.write_row(record)

    def _iterate_file(self) -> Generator[tuple[str, str], None, None]:
        # Example:
        # data/999/999/917/5305/1.400.jpg
        # data/999/999/917/5305/1.jpg
        # data/999/999/917/5305/1.json.gz
        if not self.file_path:
            raise ValueError("File path is not set. Call download_keys() first.")
        with gzip.open(self.file_path, "rt") as f:
            for image_path in f:
                image_path = image_path.strip()
                if not image_path.endswith(".jpg"):
                    continue

                parts = image_path.split("/")
                if len(parts) < 6:
                    continue

                barcode_13 = "".join(parts[1:5])
                image_url = (
                    "https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/data/"
                    + "/".join(parts[1:])
                )

                yield barcode_13, image_url
