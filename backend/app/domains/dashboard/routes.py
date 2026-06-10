from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter
from sqlmodel import select

from app.api.deps import SessionDep
from app.domains.dashboard.schemas import PriceMover, PriceMoversPublic
from app.domains.products.models import Product
from app.domains.products.price_observation_daily import PriceObservationDaily
from app.domains.products.retailers import Retailer

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/price-movers", response_model=PriceMoversPublic)
async def read_price_movers(session: SessionDep, limit: int = 10):
    bounded_limit = min(max(limit, 1), 50)

    current_date = date.today()
    previous_date = current_date - timedelta(days=1)

    current_prices = (
        select(
            PriceObservationDaily.product_id.label("product_id"),
            PriceObservationDaily.retailer_id.label("retailer_id"),
            PriceObservationDaily.price_eur_avg.label("current_price_eur"),
        )
        .where(
            PriceObservationDaily.observed_date == current_date,
        )
        .subquery()
    )
    previous_prices = (
        select(
            PriceObservationDaily.product_id.label("product_id"),
            PriceObservationDaily.retailer_id.label("retailer_id"),
            PriceObservationDaily.price_eur_avg.label("previous_price_eur"),
        )
        .where(
            PriceObservationDaily.observed_date == previous_date,
        )
        .subquery()
    )

    absolute_change = (
        current_prices.c.current_price_eur - previous_prices.c.previous_price_eur
    )
    percent_change = absolute_change / previous_prices.c.previous_price_eur * 100

    base_statement = (
        select(
            Product,
            Retailer,
            previous_prices.c.previous_price_eur,
            current_prices.c.current_price_eur,
            absolute_change.label("absolute_change_eur"),
            percent_change.label("percent_change"),
        )
        .join(Product, Product.id == current_prices.c.product_id)
        .join(Retailer, Retailer.id == current_prices.c.retailer_id)
        .join(
            previous_prices,
            (previous_prices.c.product_id == current_prices.c.product_id)
            & (previous_prices.c.retailer_id == current_prices.c.retailer_id),
        )
        .where(previous_prices.c.previous_price_eur > 0)
    )

    price_drops = (await session.exec(
        base_statement.where(absolute_change < 0)
        .order_by(percent_change.asc(), absolute_change.asc())
        .limit(bounded_limit),
    )).all()
    price_increases = (await session.exec(
        base_statement.where(absolute_change > 0)
        .order_by(percent_change.desc(), absolute_change.desc())
        .limit(bounded_limit),
    )).all()

    return PriceMoversPublic(
        current_date=current_date,
        previous_date=previous_date,
        price_drops=[
            build_price_mover(
                row, current_date=current_date, previous_date=previous_date
            )
            for row in price_drops
        ],
        price_increases=[
            build_price_mover(
                row, current_date=current_date, previous_date=previous_date
            )
            for row in price_increases
        ],
    )


def build_price_mover(
    row: tuple[Product, Retailer, Decimal, Decimal, Decimal, Decimal],
    *,
    current_date: date,
    previous_date: date,
) -> PriceMover:
    (
        product,
        retailer,
        previous_price_eur,
        current_price_eur,
        absolute_change_eur,
        percent_change,
    ) = row

    return PriceMover(
        product=product,
        retailer=retailer,
        current_date=current_date,
        previous_date=previous_date,
        previous_price_eur=previous_price_eur,
        current_price_eur=current_price_eur,
        absolute_change_eur=absolute_change_eur,
        percent_change=percent_change,
    )
