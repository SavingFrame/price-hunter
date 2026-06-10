import datetime
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import case, update
from sqlmodel import Session, select

from app.core.db import engine
from app.domains.products.aliases import ProductAlias, ProductAliasSource
from app.domains.products.models import Product
from app.domains.products.retailers import RetailerEnum
from app.domains.products.services.price_csv_importer import (
    BaseRetailerPriceCsvParser,
    KauflandPriceCsvParser,
    LidlPriceCsvParser,
    PriceCsvImporter,
    SparPriceCsvParser,
)
from app.domains.products.services.price_downloader import (
    BasePriceDownloader,
    KauflandPriceDownloader,
    LidlPriceDownloader,
    SparPriceDownloader,
    StorePriceCsvNotFound,
)
from app.domains.products.stores import Store

logger = logging.getLogger(__name__)

RetailerImport = tuple[uuid.UUID, BasePriceDownloader, BaseRetailerPriceCsvParser]
PRIMARY_NAME_RETAILER_PRIORITY = {
    RetailerEnum.KAUFLAND.value.id: 1,
    RetailerEnum.SPAR.value.id: 2,
    RetailerEnum.LIDL.value.id: 3,
}


class PriceCsvImportJob:
    def supported_retailer_ids(self) -> list[uuid.UUID]:
        return [retailer_id for retailer_id, _, _ in self._retailer_imports()]

    def import_retailer(self, retailer_id: uuid.UUID, date: datetime.date) -> None:
        _, downloader, parser = self._get_retailer_import(retailer_id)
        store_ids = self._get_retailer_store_ids(retailer_id)

        if not store_ids:
            logger.info(
                "No stores found for retailer %s, skipping CSV import.",
                parser.retailer_name,
            )
            return

        try:
            downloader.download_prices_list(date=date)
        except Exception:
            logger.exception(
                "Failed to download price list for retailer %s on %s, skipping retailer.",
                parser.retailer_name,
                date,
            )
            return

        if not downloader.has_price_files:
            logger.info(
                "No price CSV files found for retailer %s on %s, skipping retailer.",
                parser.retailer_name,
                date,
            )
            return

        importer = PriceCsvImporter(
            parser=parser,
            observed_date=date,
        )
        for store_id in store_ids:
            try:
                self._import_store_price_csv(
                    downloader=downloader,
                    importer=importer,
                    store_id=store_id,
                )
            except StorePriceCsvNotFound as exc:
                logger.info(
                    "Skipping price CSV import for retailer %s, store %s, date %s: %s",
                    parser.retailer_name,
                    store_id,
                    date,
                    exc,
                )
            except Exception:
                logger.exception(
                    "Failed to import price CSV for retailer %s, store %s, date %s. Continuing.",
                    parser.retailer_name,
                    store_id,
                    date,
                )

    @staticmethod
    def _clean_product_name(value: str) -> str:
        cleaned = " ".join(value.strip().split())
        for suffix in ("_OC", "_C"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip()
        for suffix in (" PET", " LIM"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)].rstrip()
        return cleaned[:255]

    def reconcile_product_names(self) -> int:
        priority = case(
            *[
                (ProductAlias.retailer_id == retailer_id, priority_value)
                for retailer_id, priority_value in PRIMARY_NAME_RETAILER_PRIORITY.items()
            ],
            else_=99,
        )
        alias_statement = (
            select(
                ProductAlias.product_id,
                ProductAlias.alias_name,
            )
            .where(ProductAlias.source == ProductAliasSource.PRICE_CSV.value)
            .order_by(
                ProductAlias.product_id,
                priority,
                ProductAlias.last_seen_at.desc(),
                ProductAlias.alias_name,
            )
        )

        updated_count = 0
        product_names: dict[uuid.UUID, str] = {}
        with Session(engine) as session:
            for product_id, alias_name in session.exec(alias_statement):
                if product_id in product_names:
                    continue

                product_name = self._clean_product_name(alias_name)
                if product_name:
                    product_names[product_id] = product_name

            for product_id, product_name in product_names.items():
                result = session.exec(
                    update(Product)
                    .where(
                        Product.id == product_id,
                        Product.name != product_name,
                    )
                    .values(name=product_name),
                )
                updated_count += result.rowcount or 0

            session.commit()

        logger.info("Reconciled product display names: updated=%s", updated_count)
        return updated_count

    def _retailer_imports(self) -> Sequence[RetailerImport]:
        return [
            (RetailerEnum.SPAR.value.id, SparPriceDownloader(), SparPriceCsvParser()),
            (RetailerEnum.LIDL.value.id, LidlPriceDownloader(), LidlPriceCsvParser()),
            (
                RetailerEnum.KAUFLAND.value.id,
                KauflandPriceDownloader(),
                KauflandPriceCsvParser(),
            ),
        ]

    def _get_retailer_import(self, retailer_id: uuid.UUID) -> RetailerImport:
        for import_config in self._retailer_imports():
            if import_config[0] == retailer_id:
                return import_config
        raise ValueError(f"Unknown retailer id {retailer_id}.")

    def _get_retailer_store_ids(self, retailer_id: uuid.UUID) -> Sequence[uuid.UUID]:
        with Session(engine) as session:
            stores = session.exec(
                select(Store.id).where(Store.retailer_id == retailer_id)
            ).all()
            return stores

    def _import_store_price_csv(
        self,
        downloader: BasePriceDownloader,
        importer: PriceCsvImporter,
        store_id: uuid.UUID,
    ) -> None:
        with Session(engine) as session:
            store = session.get(Store, store_id)
            if store is None:
                logger.warning(
                    "Store %s disappeared before CSV import, skipping.",
                    store_id,
                )
                return

            rows = downloader.download_price_csv_for_store(store=store)
            importer.import_prices(
                session=session,
                rows=rows,
                store=store,
            )
