import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Index, Numeric, String
from sqlmodel import Field, Relationship, SQLModel

from app.domains.common.models import get_datetime_utc

if TYPE_CHECKING:
    from app.domains.products.models import Product
    from app.models.retailer import Retailer


class ProductAliasSource(str, enum.Enum):
    PRICE_CSV = "price_csv"
    RECEIPT = "receipt"
    OPENFOODFACTS = "openfoodfacts"
    MANUAL = "manual"


class ProductAliasBase(SQLModel):
    product_id: uuid.UUID = Field(foreign_key="product.id", index=True)
    retailer_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="retailer.id",
        index=True,
        description="Retailer this alias belongs to when retailer-specific.",
    )
    alias_name: str = Field(
        index=True,
        max_length=255,
        description="Original product name exactly as seen in a source.",
    )
    normalized_alias_name: str = Field(
        index=True,
        max_length=255,
        description="Normalized search form of alias_name.",
    )
    retailer_product_code: str | None = Field(
        default=None,
        max_length=32,
        description="Retailer scoped product code when available.",
    )
    source: ProductAliasSource = Field(
        sa_column=Column(String(32), nullable=False),
        description="Source of the alias.",
    )
    confidence: Decimal = Field(
        default=Decimal("1.0000"),
        sa_column=Column(Numeric(5, 4), nullable=False, server_default="1.0000"),
        description="Confidence score from 0.0000 to 1.0000.",
    )
    first_seen_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_seen_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProductAlias(ProductAliasBase, table=True):
    __table_args__ = (
        Index(
            "uq_product_alias_source_identity",
            "product_id",
            "retailer_id",
            "normalized_alias_name",
            "retailer_product_code",
            "source",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    product: "Product" = Relationship(back_populates="aliases")
    retailer: "Retailer" = Relationship()


class ProductAliasCreate(ProductAliasBase):
    pass


class ProductAliasPublic(ProductAliasBase):
    id: uuid.UUID
