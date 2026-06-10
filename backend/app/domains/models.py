"""SQLModel table registry."""

from app.domains.accounts.models import User
from app.domains.product_lists.models import (
    ProductList,
    ProductListItem,
    ProductListItemAlternative,
)
from app.domains.products.aliases import ProductAlias
from app.domains.products.models import Product
from app.domains.products.price_observation import PriceObservation
from app.domains.products.price_observation_daily import PriceObservationDaily
from app.domains.products.retailers import Retailer
from app.domains.products.stores import Store
from app.domains.receipts.models import Receipt, ReceiptItem

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
