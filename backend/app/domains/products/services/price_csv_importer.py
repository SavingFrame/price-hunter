import datetime as dt
import logging
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar, TypeVar

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.domains.products.aliases import ProductAlias, ProductAliasSource
from app.domains.products.models import Product
from app.domains.products.price_observation import PriceObservation
from app.domains.products.retailers import RetailerEnum
from app.domains.products.stores import Store

logger = logging.getLogger(__name__)

CsvRow = Mapping[str, str | None]
BulkRow = dict[str, Any]
ChunkItem = TypeVar("ChunkItem")
BULK_INSERT_CHUNK_SIZE = 5000


def _chunks(
    values: list[ChunkItem],
    size: int = BULK_INSERT_CHUNK_SIZE,
) -> Iterable[list[ChunkItem]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


@dataclass(frozen=True)
class NormalizedPriceRow:
    retailer_product_code: str
    source_product_name: str
    barcode: str | None
    brand: str | None
    net_quantity: str | None
    unit_of_measure: str | None
    category: str | None
    price_eur: Decimal | None
    unit_price_eur: Decimal
    is_special_sale: bool


class BaseRetailerPriceCsvParser:
    retailer_id: ClassVar[uuid.UUID]
    retailer_name: ClassVar[str]
    delimiter: ClassVar[str]
    encoding: ClassVar[str] = "cp1250"
    columns: ClassVar[dict[str, str]]

    def normalize_row(self, row: CsvRow) -> NormalizedPriceRow | None:
        name = self.clean(row.get(self.columns["name"]))
        code = self.clean(row.get(self.columns["code"]))
        unit_price = self.parse_decimal(row.get(self.columns["unit_price"]))
        retail_price = self.parse_decimal(row.get(self.columns["retail_price"]))
        if unit_price is None and retail_price is None:
            return None
        if not name or not code or unit_price is None:
            return None

        retail_price = retail_price or unit_price
        unit_price = unit_price or retail_price

        special_sale_price = self.parse_decimal(
            row.get(self.columns["special_sale_price"])
        )

        return NormalizedPriceRow(
            retailer_product_code=code,
            source_product_name=name,
            barcode=self.clean(row.get(self.columns["barcode"])),
            brand=self.clean(row.get(self.columns["brand"])),
            net_quantity=self.clean(row.get(self.columns["net_quantity"])),
            unit_of_measure=self.clean(row.get(self.columns["unit_of_measure"])),
            category=self.clean(row.get(self.columns["category"])),
            price_eur=(
                special_sale_price if special_sale_price is not None else retail_price
            ),
            unit_price_eur=unit_price,
            is_special_sale=special_sale_price is not None,
        )

    @staticmethod
    def parse_decimal(value: Any) -> Decimal | None:
        clean_value = BaseRetailerPriceCsvParser.clean(value)
        if clean_value is None:
            return None
        normalized = (
            clean_value.replace(".", "").replace(",", ".")
            if "," in clean_value
            else clean_value
        )
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None

    @staticmethod
    def clean(value: Any) -> str | None:
        if value is None:
            return None
        clean_value = str(value).strip()
        return clean_value or None


class LidlPriceCsvParser(BaseRetailerPriceCsvParser):
    retailer_id = RetailerEnum.LIDL.value.id
    retailer_name = RetailerEnum.LIDL.value.name
    delimiter = ","
    columns = {
        "name": "NAZIV",
        "code": "ŠIFRA",
        "brand": "MARKA",
        "net_quantity": "NETO_KOLIČINA",
        "unit_of_measure": "JEDINICA_MJERE",
        "retail_price": "MALOPRODAJNA_CIJENA",
        "unit_price": "CIJENA_ZA_JEDINICU_MJERE",
        "special_sale_price": "MPC_ZA_VRIJEME_POSEBNOG_OBLIKA_PRODAJE",
        "barcode": "BARKOD",
        "category": "KATEGORIJA_PROIZVODA",
    }


class SparPriceCsvParser(BaseRetailerPriceCsvParser):
    retailer_id = RetailerEnum.SPAR.value.id
    retailer_name = RetailerEnum.SPAR.value.name
    delimiter = ";"
    columns = {
        "name": "naziv",
        "code": "šifra",
        "brand": "marka",
        "net_quantity": "neto količina",
        "unit_of_measure": "jedinica mjere",
        "retail_price": "MPC (EUR)",
        "unit_price": "cijena za jedinicu mjere (EUR)",
        "special_sale_price": "MPC za vrijeme posebnog oblika prodaje (EUR)",
        "barcode": "barkod",
        "category": "kategorija proizvoda",
    }


class KauflandPriceCsvParser(BaseRetailerPriceCsvParser):
    retailer_id = RetailerEnum.KAUFLAND.value.id
    retailer_name = RetailerEnum.KAUFLAND.value.name
    delimiter = "\t"
    encoding = "utf-8-sig"
    columns = {
        "name": "naziv proizvoda",
        "code": "šifra proizvoda",
        "brand": "marka proizvoda",
        "net_quantity": "neto količina(KG)",
        "unit_of_measure": "jedinica mjere",
        "retail_price": "maloprod.cijena(EUR)",
        "unit_price": "cijena jed.mj.(EUR)",
        "special_sale_price": "MPC poseb.oblik prod",
        "barcode": "barkod",
        "category": "kategorija proizvoda",
    }


class PriceCsvImporter:
    def __init__(
        self,
        parser: BaseRetailerPriceCsvParser,
        observed_date: dt.date,
    ) -> None:
        self.parser = parser
        self.observed_date = observed_date
        self._products_by_barcode: dict[str, uuid.UUID] = {}
        self._products_by_retailer_code: dict[str, uuid.UUID] = {}

    def import_prices(
        self,
        session: Session,
        rows: Iterable[CsvRow],
        store: Store,
    ) -> None:
        self._products_by_barcode.clear()
        self._products_by_retailer_code.clear()
        if self.parser.retailer_id != store.retailer_id:
            raise ValueError(
                f"CSV parser {self.parser.retailer_name} does not match store retailer."
            )

        normalized_rows = []
        for raw_row in rows:
            normalized_row = self.parser.normalize_row(raw_row)
            if normalized_row:
                normalized_rows.append(normalized_row)

        self._upsert_barcode_products(normalized_rows, session=session)
        self._insert_products_without_barcode(normalized_rows, session=session)
        aliases = {}
        observations = {}

        for row in normalized_rows:
            product_id = self._get_product_id(row)
            if product_id is None:
                continue

            normalized_alias_name = self._normalize_alias_name(row.source_product_name)
            aliases[
                (
                    product_id,
                    store.retailer_id,
                    normalized_alias_name,
                    row.retailer_product_code,
                    ProductAliasSource.PRICE_CSV.value,
                )
            ] = {
                "product_id": product_id,
                "retailer_id": store.retailer_id,
                "alias_name": row.source_product_name,
                "normalized_alias_name": normalized_alias_name,
                "retailer_product_code": row.retailer_product_code,
                "source": ProductAliasSource.PRICE_CSV.value,
                "confidence": Decimal("0.9500"),
                "first_seen_at": func.now(),
                "last_seen_at": func.now(),
            }
            observations[
                (
                    store.retailer_id,
                    store.id,
                    self.observed_date,
                    row.retailer_product_code,
                    product_id,
                )
            ] = {
                "retailer_id": store.retailer_id,
                "store_id": store.id,
                "observed_date": self.observed_date,
                "retailer_product_code": row.retailer_product_code,
                "product_id": product_id,
                "source_product_name": row.source_product_name,
                "price_eur": row.price_eur,
                "unit_price_eur": row.unit_price_eur,
                "is_special_sale": row.is_special_sale,
                "source_file_name": None,
            }

        self._insert_observations(list(observations.values()), session=session)

        self._insert_aliases(list(aliases.values()), session=session)

        session.commit()

    def _upsert_barcode_products(
        self, rows: list[NormalizedPriceRow], session: Session
    ) -> None:
        barcode_rows = {row.barcode: row for row in rows if row.barcode}
        if not barcode_rows:
            return

        product_rows = [
            {
                "barcode": row.barcode,
                "name": row.source_product_name,
                "brand": row.brand,
                "net_quantity": row.net_quantity,
                "unit_of_measure": row.unit_of_measure,
                "category": row.category,
            }
            for row in barcode_rows.values()
        ]
        for product_rows_chunk in _chunks(product_rows):
            stmt = insert(Product).values(product_rows_chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["barcode"],
                set_={
                    "brand": func.coalesce(Product.brand, stmt.excluded.brand),
                    "net_quantity": func.coalesce(
                        Product.net_quantity, stmt.excluded.net_quantity
                    ),
                    "unit_of_measure": func.coalesce(
                        Product.unit_of_measure, stmt.excluded.unit_of_measure
                    ),
                    "category": func.coalesce(Product.category, stmt.excluded.category),
                },
            ).returning(Product.id, Product.barcode)
            results = session.exec(stmt)
            for product_id, barcode in results:
                self._products_by_barcode[barcode] = product_id

    def _insert_products_without_barcode(
        self, rows: list[NormalizedPriceRow], session: Session
    ) -> None:
        rows_by_code = {
            row.retailer_product_code: row
            for row in rows
            if not row.barcode and row.retailer_product_code
        }
        if not rows_by_code:
            return

        existing_products = session.exec(
            select(
                PriceObservation.retailer_product_code,
                PriceObservation.product_id,
            ).where(
                PriceObservation.retailer_id == self.parser.retailer_id,
                PriceObservation.retailer_product_code.in_(list(rows_by_code)),
            )
        )
        existing_product_codes = set()
        for retailer_product_code, product_id in existing_products:
            if retailer_product_code in existing_product_codes:
                continue
            existing_product_codes.add(retailer_product_code)
            self._products_by_retailer_code[retailer_product_code] = product_id

        missing_rows = [
            row
            for retailer_product_code, row in rows_by_code.items()
            if retailer_product_code not in existing_product_codes
        ]
        if not missing_rows:
            return

        product_rows: list[BulkRow] = []
        for row in missing_rows:
            product_id = uuid.uuid7()
            product_rows.append(
                {
                    "id": product_id,
                    "barcode": None,
                    "name": row.source_product_name,
                    "brand": row.brand,
                    "net_quantity": row.net_quantity,
                    "unit_of_measure": row.unit_of_measure,
                    "category": row.category,
                }
            )
            self._products_by_retailer_code[row.retailer_product_code] = product_id

        for product_rows_chunk in _chunks(product_rows):
            session.exec(insert(Product).values(product_rows_chunk))

    def _get_product_id(self, row: NormalizedPriceRow) -> uuid.UUID | None:
        if row.barcode:
            result = self._products_by_barcode.get(row.barcode)
        else:
            result = self._products_by_retailer_code.get(row.retailer_product_code)

        if not result:
            logger.warning(
                "Product not found for row with barcode %s and retailer product code %s",
                row.barcode,
                row.retailer_product_code,
            )
        return result

    def _insert_observations(self, rows: list[BulkRow], session: Session) -> None:
        if not rows:
            return

        for rows_chunk in _chunks(rows):
            stmt = insert(PriceObservation).values(rows_chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_price_observation_retailer_store_date_code_product",
                set_={
                    "source_product_name": stmt.excluded.source_product_name,
                    "price_eur": stmt.excluded.price_eur,
                    "unit_price_eur": stmt.excluded.unit_price_eur,
                    "is_special_sale": stmt.excluded.is_special_sale,
                },
            )
            session.exec(stmt)

    def _insert_aliases(self, rows: list[BulkRow], session: Session) -> None:
        if not rows:
            return

        for rows_chunk in _chunks(rows):
            stmt = insert(ProductAlias).values(rows_chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[
                    ProductAlias.product_id,
                    ProductAlias.retailer_id,
                    ProductAlias.normalized_alias_name,
                    ProductAlias.retailer_product_code,
                    ProductAlias.source,
                ],
                set_={
                    "alias_name": stmt.excluded.alias_name,
                    "confidence": stmt.excluded.confidence,
                    "last_seen_at": stmt.excluded.last_seen_at,
                },
            )
            session.exec(stmt)

    @staticmethod
    def _normalize_alias_name(value: str) -> str:
        return " ".join(value.strip().lower().split())
