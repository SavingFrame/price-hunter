import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.domains.common.models import get_datetime_utc

if TYPE_CHECKING:
    from app.domains.accounts.models import User
    from app.domains.products.models import Product


class ProductListBase(SQLModel):
    name: str = Field(
        max_length=255,
        description="User-facing product list name, for example Weekly groceries.",
    )
    description: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional notes about what this product list is for.",
    )


class ProductList(ProductListBase, table=True):
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_product_list_user_name"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    user: "User" = Relationship(back_populates="product_lists")
    items: list["ProductListItem"] = Relationship(back_populates="product_list")


class ProductListPublic(ProductListBase):
    id: uuid.UUID
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProductListsPublic(SQLModel):
    data: list[ProductListPublic]
    count: int


class ProductListItemBase(SQLModel):
    product_list_id: uuid.UUID = Field(foreign_key="productlist.id", index=True)
    product_id: uuid.UUID = Field(foreign_key="product.id", index=True)
    quantity: Decimal = Field(
        default=Decimal("1"),
        sa_column=Column(Numeric(10, 3), nullable=False),
        description="How many units of the canonical product are planned for this list.",
    )
    note: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional note for this list item.",
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProductListItem(ProductListItemBase, table=True):
    __table_args__ = (
        UniqueConstraint(
            "product_list_id",
            "product_id",
            name="uq_product_list_item_product",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    product_list: "ProductList" = Relationship(back_populates="items")
    product: "Product" = Relationship(back_populates="product_list_items")
    alternatives: list["ProductListItemAlternative"] = Relationship(
        back_populates="product_list_item",
    )


class ProductListItemAlternativeBase(SQLModel):
    product_list_item_id: uuid.UUID = Field(
        foreign_key="productlistitem.id",
        index=True,
    )
    product_id: uuid.UUID = Field(foreign_key="product.id", index=True)
    similarity_score: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(6, 4), nullable=True),
        description="Similarity score captured when this alternative was selected.",
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ProductListItemAlternative(ProductListItemAlternativeBase, table=True):
    __table_args__ = (
        UniqueConstraint(
            "product_list_item_id",
            "product_id",
            name="uq_product_list_item_alternative_product",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    product_list_item: "ProductListItem" = Relationship(back_populates="alternatives")
    product: "Product" = Relationship(back_populates="product_list_item_alternatives")


class ProductListItemCreate(ProductListItemBase):
    pass


class ProductListItemPublic(ProductListItemBase):
    id: uuid.UUID


class ProductListItemAlternativeCreate(SQLModel):
    product_id: uuid.UUID
    similarity_score: Decimal | None = None


class ProductListItemAlternativesBulkCreate(SQLModel):
    product_ids: list[uuid.UUID]
    similarity_scores: dict[uuid.UUID, Decimal] = Field(default_factory=dict)


class ProductListItemAlternativePublic(ProductListItemAlternativeBase):
    id: uuid.UUID


class ProductListItemsPublic(SQLModel):
    data: list[ProductListItemPublic]
    count: int
