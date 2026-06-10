import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.domains.receipts.models import Receipt
    from app.models.price_observation import PriceObservation
    from app.models.retailer import Retailer


class StoreBase(SQLModel):
    retailer_id: uuid.UUID = Field(foreign_key="retailer.id", index=True)
    store_code: str = Field(
        index=True,
        max_length=64,
        description="Retailer scoped store code from the source file or retailer data.",
    )
    name: str = Field(
        max_length=255,
        description="Store name, for example a branch or supermarket name.",
    )
    address: str = Field(
        default="",
        max_length=255,
        description="Store address when available.",
    )
    prefix: str = Field(
        default="",
        max_length=255,
        description="Prefix to be used in finding corresponding file in list of stores",
    )


class Store(StoreBase, table=True):
    __table_args__ = (
        UniqueConstraint("retailer_id", "store_code", name="uq_store_retailer_code"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    retailer: "Retailer" = Relationship(back_populates="stores")
    price_observations: list["PriceObservation"] = Relationship(back_populates="store")
    receipts: list["Receipt"] = Relationship(back_populates="store")


class StoreCreate(StoreBase):
    pass


class StorePublic(StoreBase):
    id: uuid.UUID


class StoresPublic(SQLModel):
    data: list[StorePublic]
    count: int
