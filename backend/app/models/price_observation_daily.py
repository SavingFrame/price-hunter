import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, Numeric
from sqlmodel import Field, Relationship, SQLModel, UniqueConstraint, text

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.retailer import Retailer


class PriceObservationDailyBase(SQLModel):
    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "observed_date",
            "retailer_id",
            name="uq_price_observation_daily",
        ),
    )

    product_id: uuid.UUID = Field(foreign_key="product.id", index=True)
    retailer_id: uuid.UUID = Field(foreign_key="retailer.id", index=True)
    observed_date: date = Field(
        index=True,
        description="Date of the price list or observation.",
    )
    price_eur_min: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
        description="Minimum product price from the source price list.",
    )
    price_eur_max: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
        description="Maximum product price from the source price list.",
    )
    price_eur_avg: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
        description="Average product price from the source price list.",
    )
    is_special_sale: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False),
        description="Whether price_eur comes from the special sale price column.",
    )
    is_special_sale: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="0"),
        description="Whether price_eur comes from the special sale price column.",
    )


class PriceObservationDaily(PriceObservationDailyBase, table=True):
    id: uuid.UUID = Field(
        sa_column_kwargs={"server_default": text("uuidv7()")},
        primary_key=True,
    )

    product: "Product" = Relationship(back_populates="daily_price_observations")
    retailer: "Retailer" = Relationship(back_populates="daily_price_observations")
