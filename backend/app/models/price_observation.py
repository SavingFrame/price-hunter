import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, Index, Numeric, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.domains.products.models import Product
    from app.domains.receipts.models import ReceiptItem
    from app.models.retailer import Retailer
    from app.models.store import Store


class PriceObservationBase(SQLModel):
    product_id: uuid.UUID = Field(foreign_key="product.id", index=True)
    retailer_id: uuid.UUID = Field(foreign_key="retailer.id", index=True)
    store_id: uuid.UUID = Field(foreign_key="store.id", index=True)
    observed_date: date = Field(
        index=True,
        description="Date of the price list or observation.",
    )
    retailer_product_code: str = Field(
        index=True,
        max_length=32,
        description="Retailer scoped product code. Original CSV column: šifra or ŠIFRA PROIZVODA.",
    )
    source_product_name: str = Field(
        max_length=255,
        description="Product name exactly as it appeared in the source price list.",
    )
    price_eur: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
        description="Current product price from the source price list.",
    )
    unit_price_eur: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
        description="Original CSV column: cijena za jedinicu mjere (EUR) or CIJENA ZA JEDINICU MJERE.",
    )
    is_special_sale: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="0"),
        description="Whether price_eur comes from the special sale price column.",
    )
    source_file_name: str | None = Field(
        default=None,
        max_length=255,
        description="Name of the imported source CSV file.",
    )


class PriceObservation(PriceObservationBase, table=True):
    __table_args__ = (
        UniqueConstraint(
            "retailer_id",
            "store_id",
            "observed_date",
            "retailer_product_code",
            "product_id",
            name="uq_price_observation_retailer_store_date_code_product",
        ),
        Index(
            "ix_priceobservation_retailer_code",
            "retailer_id",
            "retailer_product_code",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    product: "Product" = Relationship(back_populates="price_observations")
    retailer: "Retailer" = Relationship(back_populates="price_observations")
    store: "Store" = Relationship(back_populates="price_observations")
    receipt_items: list["ReceiptItem"] = Relationship(
        back_populates="price_observation",
    )


class PriceObservationCreate(PriceObservationBase):
    pass


class PriceObservationPublic(PriceObservationBase):
    id: uuid.UUID


class PriceObservationsPublic(SQLModel):
    data: list[PriceObservationPublic]
    count: int
