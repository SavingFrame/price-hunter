from fastapi import APIRouter

from app.api.routes import (
    private,
    product_lists,
    products,
    receipts,
    utils,
)
from app.core.config import settings
from app.domains.accounts.routes import login, users
from app.domains.dashboard import routes as dashboard

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(products.router)
api_router.include_router(product_lists.router)
api_router.include_router(receipts.router)
api_router.include_router(dashboard.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
