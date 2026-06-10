import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Numeric, String, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.domains.common.models import get_datetime_utc

if TYPE_CHECKING:
    from app.domains.accounts.models import User
    from app.domains.products.models import Product
    from app.domains.products.price_observation import PriceObservation
    from app.domains.products.retailers import Retailer
    from app.domains.products.stores import Store


class ReceiptStatus(str, enum.Enum):
    DRAFT = "draft"
    COMPLETED = "completed"


class ReceiptBase(SQLModel):
    retailer_id: uuid.UUID = Field(foreign_key="retailer.id", index=True)
    store_id: uuid.UUID | None = Field(default=None, foreign_key="store.id", index=True)
    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", index=True)
    purchase_datetime: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore
        index=True,
        description="Datetime when the purchase was made, as parsed from the receipt.",
    )
    total_eur: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(10, 2), nullable=True),
        description="Final receipt total in EUR.",
    )
    file_key: str = Field(
        max_length=512,
        description="Storage key or path for the uploaded receipt file.",
    )
    status: ReceiptStatus = Field(
        default=ReceiptStatus.DRAFT,
        sa_column=Column(String(32), nullable=False),
        description="User review lifecycle status for the receipt.",
    )
    raw_text: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
        description="Text extracted from the uploaded receipt file.",
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Receipt(ReceiptBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    retailer: "Retailer" = Relationship(back_populates="receipts")
    store: "Store" = Relationship(back_populates="receipts")
    user: "User" = Relationship()
    items: list["ReceiptItem"] = Relationship(back_populates="receipt")


class ReceiptCreate(ReceiptBase):
    pass


class ReceiptPublic(ReceiptBase):
    id: uuid.UUID


class ReceiptsPublic(SQLModel):
    data: list[ReceiptPublic]
    count: int


class ReceiptItemBase(SQLModel):
    receipt_id: uuid.UUID = Field(foreign_key="receipt.id", index=True)
    product_id: uuid.UUID | None = Field(
        default=None, foreign_key="product.id", index=True
    )
    price_observation_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="priceobservation.id",
        index=True,
    )
    line_number: int
    raw_name: str = Field(
        max_length=255,
        description="Product name exactly as parsed from the receipt.",
    )
    normalized_raw_name: str = Field(
        index=True,
        max_length=255,
        description="Normalized search form of raw_name.",
    )
    quantity: Decimal = Field(
        sa_column=Column(Numeric(10, 3), nullable=False),
        description="Purchased quantity parsed from the receipt line.",
    )
    unit_of_measure: str | None = Field(
        default=None,
        max_length=64,
        description="Unit parsed from the receipt line when present, for example kg.",
    )
    unit_price_eur: Decimal | None = Field(
        default=None,
        sa_column=Column(Numeric(10, 2), nullable=True),
        description="Unit price in EUR parsed from the receipt line.",
    )
    line_total_eur: Decimal = Field(
        sa_column=Column(Numeric(10, 2), nullable=False),
        description="Final line total in EUR after any receipt-level line adjustments.",
    )
    is_skipped: bool = Field(
        default=False,
        description="Whether the user intentionally ignored this receipt line.",
    )
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ReceiptItem(ReceiptItemBase, table=True):
    __table_args__ = (
        UniqueConstraint("receipt_id", "line_number", name="uq_receipt_item_line"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    receipt: "Receipt" = Relationship(back_populates="items")
    product: "Product" = Relationship(back_populates="receipt_items")
    price_observation: "PriceObservation" = Relationship(
        back_populates="receipt_items",
    )


class ReceiptItemCreate(ReceiptItemBase):
    pass


class ReceiptItemPublic(ReceiptItemBase):
    id: uuid.UUID


class ReceiptItemsPublic(SQLModel):
    data: list[ReceiptItemPublic]
    count: int
