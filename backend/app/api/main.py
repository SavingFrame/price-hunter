from fastapi import APIRouter

from app.domains.accounts.routes import login, users
from app.domains.dashboard import routes as dashboard
from app.domains.product_lists import routes as product_lists
from app.domains.products import routes as products
from app.domains.receipts import routes as receipts
from app.domains.system import routes as utils

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(products.router)
api_router.include_router(product_lists.router)
api_router.include_router(receipts.router)
api_router.include_router(dashboard.router)

