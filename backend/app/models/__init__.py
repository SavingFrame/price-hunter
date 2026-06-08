"""SQLModel table registry."""

from app.models.price_observation import PriceObservation
from app.models.price_observation_daily import PriceObservationDaily
from app.models.product import Product
from app.models.product_alias import ProductAlias
from app.models.product_list import (
    ProductList,
    ProductListItem,
    ProductListItemAlternative,
)
from app.models.receipt import Receipt, ReceiptItem
from app.models.retailer import Retailer
from app.models.store import Store
from app.models.user import User

__all__ = [
    "PriceObservation",
    "PriceObservationDaily",
    "Product",
    "ProductAlias",
    "ProductList",
    "ProductListItem",
    "ProductListItemAlternative",
    "Receipt",
    "ReceiptItem",
    "Retailer",
    "Store",
    "User",
]
