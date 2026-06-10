from datetime import date
from decimal import Decimal
from typing import ClassVar

from sqlmodel import SQLModel

from app.domains.products.models import ProductPublic
from app.domains.products.price_observation import PriceObservationPublic
from app.domains.products.retailers import RetailerPublic
from app.domains.products.stores import StorePublic


class NestedPriceObservation(PriceObservationPublic):
    product: ClassVar
    retailer: RetailerPublic
    store: StorePublic


class RetailerPriceObservationSummary(SQLModel):
    retailer: RetailerPublic
    observed_date: date
    average_price_eur: Decimal | None
    min_price_eur: Decimal | None
    max_price_eur: Decimal | None
    average_unit_price_eur: Decimal
    min_unit_price_eur: Decimal
    max_unit_price_eur: Decimal
    store_count: int
    has_store_price_variance: bool
    has_special_sale: bool


class RetailerDailyRetailPriceHistoryPoint(SQLModel):
    retailer: RetailerPublic
    observed_date: date
    average_price_eur: Decimal | None
    min_price_eur: Decimal | None
    max_price_eur: Decimal | None
    has_special_sale: bool


class SimilarProductPublic(SQLModel):
    product: ProductPublic
    retailers: list[RetailerPublic]
    latest_price_eur: Decimal | None
    average_price_eur: Decimal | None
    latest_observed_date: date | None
    score: Decimal
