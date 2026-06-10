import enum
import uuid
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.domains.products.price_observation import PriceObservation
    from app.domains.products.price_observation_daily import PriceObservationDaily
    from app.domains.products.stores import Store
    from app.domains.receipts.models import Receipt


class RetailerBase(SQLModel):
    name: str = Field(
        unique=True,
        index=True,
        max_length=64,
        description="Retailer name, for example Konzum or Interspar.",
    )


class Retailer(RetailerBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)

    stores: list["Store"] = Relationship(back_populates="retailer")
    price_observations: list["PriceObservation"] = Relationship(
        back_populates="retailer",
    )
    daily_price_observations: list["PriceObservationDaily"] = Relationship(
        back_populates="retailer",
    )
    receipts: list["Receipt"] = Relationship(back_populates="retailer")


class RetailerCreate(RetailerBase):
    pass


class RetailerPublic(RetailerBase):
    id: uuid.UUID


class RetailerEnum(enum.Enum):
    LIDL = RetailerPublic(name="Lidl", id=uuid.UUID("019dd1b1dae672fd975a29fe3fd69aa9"))
    SPAR = RetailerPublic(name="Spar", id=uuid.UUID("019dd1b1dafb7015973e90e630409a7a"))
    KAUFLAND = RetailerPublic(
        name="Kaufland",
        id=uuid.UUID("019dd1b1db1279aa8922bd29a327c887"),
    )


class RetailersPublic(SQLModel):
    data: list[RetailerPublic]
    count: int
