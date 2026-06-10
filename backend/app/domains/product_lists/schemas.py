import uuid
from datetime import date
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.domains.product_lists.models import (
    ProductListItemAlternativePublic,
    ProductListItemPublic,
)
from app.domains.products.models import ProductPublic
from app.domains.products.retailers import RetailerPublic


class ProductListUpdate(SQLModel):
    name: str | None = None
    description: str | None = None


class ProductListItemCreate(SQLModel):
    product_id: uuid.UUID
    quantity: Decimal = Decimal("1")
    note: str | None = None


class ProductListItemUpdate(SQLModel):
    quantity: Decimal | None = None
    note: str | None = None


class ProductListItemAlternativeDetailPublic(ProductListItemAlternativePublic):
    product: ProductPublic


class ProductListItemDetailPublic(ProductListItemPublic):
    product: ProductPublic
    alternatives: list[ProductListItemAlternativeDetailPublic] = Field(
        default_factory=list
    )


class ProductListItemAlternativesBulkCreateResult(SQLModel):
    data: list[ProductListItemAlternativeDetailPublic]
    created_count: int
    skipped_count: int


class ProductListRetailerPriceHistoryPoint(SQLModel):
    retailer: RetailerPublic
    observed_date: date
    total_price_eur: Decimal
    matched_item_count: int
    total_item_count: int
    has_missing_prices: bool
    has_special_sale: bool
