import logging
from collections.abc import Mapping
from dataclasses import dataclass

import openfoodfacts
from sqlmodel import Session, select

from app.core.config import settings
from app.models.price_observation import PriceObservation  # noqa: F401
from app.models.product import Product
from app.models.retailer import Retailer  # noqa: F401
from app.models.store import Store  # noqa: F401

logger = logging.getLogger(__name__)

OPENFOODFACTS_FIELDS = ["code", "image_url", "image_front_url"]


@dataclass(frozen=True)
class ProductImageSyncResult:
    checked: int = 0
    updated: int = 0
    missing_openfoodfacts_product: int = 0
    missing_openfoodfacts_image: int = 0
    failed: int = 0


class OpenFoodFactsProductImageSyncer:
    def __init__(self) -> None:
        self.api = openfoodfacts.API(
            user_agent=f"{settings.PROJECT_NAME}/0.1.0 (price-hunter product images)",
        )

    def sync_missing_product_images(
        self,
        session: Session,
        limit: int | None = None,
    ) -> ProductImageSyncResult:
        statement = select(Product).where(
            Product.image_url.is_(None),
            Product.barcode.is_not(None),
        )
        if limit is not None:
            statement = statement.limit(limit)

        checked = 0
        updated = 0
        missing_product = 0
        missing_image = 0
        failed = 0

        products = session.exec(statement).all()
        for product in products:
            checked += 1
            if not product.barcode:
                continue

            try:
                off_product = self.api.product.get(
                    product.barcode,
                    fields=OPENFOODFACTS_FIELDS,
                )
            except Exception:
                failed += 1
                logger.exception(
                    "Failed to fetch Open Food Facts product for barcode %s",
                    product.barcode,
                )
                continue

            if not off_product:
                missing_product += 1
                continue

            image_url = self._get_image_url(off_product)
            if not image_url:
                missing_image += 1
                continue

            product.image_url = image_url
            session.add(product)
            updated += 1

        session.commit()
        return ProductImageSyncResult(
            checked=checked,
            updated=updated,
            missing_openfoodfacts_product=missing_product,
            missing_openfoodfacts_image=missing_image,
            failed=failed,
        )

    @staticmethod
    def _get_image_url(product: Mapping[str, object]) -> str | None:
        for field_name in ("image_url", "image_front_url"):
            value = product.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
