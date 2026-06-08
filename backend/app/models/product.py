import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import model_validator
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.price_observation import PriceObservation
    from app.models.price_observation_daily import PriceObservationDaily
    from app.models.product_alias import ProductAlias
    from app.models.product_list import ProductListItem, ProductListItemAlternative
    from app.models.receipt import ReceiptItem


class ProductBase(SQLModel):
    barcode: str | None = Field(
        default=None,
        unique=True,
        index=True,
        max_length=32,
        description="Cross retailer product identifier when present. Original CSV column: barkod or BARKOD.",
    )
    name: str = Field(
        index=True,
        max_length=255,
        description="Canonical or first seen product name. Original CSV column: naziv or NAZIV PROIZVODA.",
    )
    brand: str | None = Field(
        default=None,
        index=True,
        max_length=64,
        description="Original CSV column: marka or MARKA PROIZVODA.",
    )
    net_quantity: str | None = Field(
        default=None,
        max_length=32,
        description="Raw net quantity from the CSV. Original CSV column: neto količina or NETO KOLIČINA.",
    )
    unit_of_measure: str | None = Field(
        default=None,
        max_length=64,
        description="Original CSV column: jedinica mjere or JEDINICA MJERE.",
    )
    category: str | None = Field(
        default=None,
        index=True,
        max_length=64,
        description="Original CSV column: kategorija proizvoda or KATEGORIJA PROIZVODA.",
    )
    image_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Product image URL fetched from Open Food Facts.",
    )


class Product(ProductBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    price_observations: list["PriceObservation"] = Relationship(
        back_populates="product",
    )
    daily_price_observations: list["PriceObservationDaily"] = Relationship(
        back_populates="product",
    )
    aliases: list["ProductAlias"] = Relationship(back_populates="product")
    receipt_items: list["ReceiptItem"] = Relationship(back_populates="product")
    product_list_items: list["ProductListItem"] = Relationship(
        back_populates="product",
    )
    product_list_item_alternatives: list["ProductListItemAlternative"] = Relationship()


class ProductCreate(ProductBase):
    pass


class ProductPublic(ProductBase):
    id: uuid.UUID
    latest_price_eur: Decimal | None = Field(
        default=None,
        description="Product price from one latest available observation.",
    )

    @model_validator(mode="after")
    def set_default_image_url(self) -> "ProductPublic":
        if not self.barcode:
            return self

        cleaned_barcode = self.barcode.strip()
        if not cleaned_barcode.isdigit() or len(cleaned_barcode) <= 4:
            return self

        prefix_length = len(cleaned_barcode) - 4
        groups = [
            cleaned_barcode[index : index + 3] for index in range(0, prefix_length, 3)
        ]
        groups.append(cleaned_barcode[prefix_length:])
        product_path = "/".join(groups)
        self.image_url = (
            "https://openfoodfacts-images.s3.eu-west-3.amazonaws.com/"
            f"data/{product_path}/1.400.jpg"
        )
        return self


class ProductsPublic(SQLModel):
    data: list[ProductPublic]
    count: int
