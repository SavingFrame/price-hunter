from datetime import date
from decimal import Decimal

from sqlmodel import SQLModel

from app.domains.products.models import ProductPublic
from app.domains.products.retailers import RetailerPublic


class PriceMover(SQLModel):
    product: ProductPublic
    retailer: RetailerPublic
    current_date: date
    previous_date: date
    previous_price_eur: Decimal
    current_price_eur: Decimal
    absolute_change_eur: Decimal
    percent_change: Decimal


class PriceMoversPublic(SQLModel):
    current_date: date | None
    previous_date: date | None
    price_drops: list[PriceMover]
    price_increases: list[PriceMover]
