import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import case, desc, or_
from sqlalchemy.orm import selectinload
from sqlmodel import func, select

from app.api.deps import SessionDep
from app.domains.products.aliases import ProductAlias
from app.domains.products.models import Product, ProductPublic, ProductsPublic
from app.domains.products.price_observation import PriceObservation
from app.domains.products.price_observation_daily import PriceObservationDaily
from app.domains.products.retailers import Retailer
from app.domains.products.schemas import (
    NestedPriceObservation,
    RetailerDailyRetailPriceHistoryPoint,
    RetailerPriceObservationSummary,
    SimilarProductPublic,
)
from app.domains.products.services.similarity import product_similarity_service

router = APIRouter(prefix="/products", tags=["products"])


def serialize_products_with_latest_price(
    rows: list[tuple[Product, Decimal]],
) -> list[ProductPublic]:
    products = []
    for product, latest_price_eur in rows:
        product_public = ProductPublic.model_validate(product)
        product_public.latest_price_eur = latest_price_eur
        products.append(product_public)

    return products


@router.get("", response_model=ProductsPublic)
async def read_products(
    session: SessionDep,
    skip: int = 0,
    limit: int = 20,
    q: str | None = None,
):
    search = q.strip() if q else None

    coverage_date = func.current_date() - 1

    latest_product_price_subquery = (
        select(PriceObservationDaily.price_eur_avg)
        .where(PriceObservationDaily.product_id == Product.id)
        .order_by(desc(PriceObservationDaily.observed_date), PriceObservationDaily.id)
        .limit(1)
        .scalar_subquery()
    )

    if not search:
        count_statement = select(
            func.count(func.distinct(PriceObservationDaily.product_id)),
        ).where(PriceObservationDaily.observed_date == coverage_date)
        count = (await session.exec(count_statement)).one()

        product_coverage = (
            select(
                PriceObservationDaily.product_id.label("product_id"),
                func.count(func.distinct(PriceObservationDaily.retailer_id)).label(
                    "retailer_count",
                ),
                func.sum(PriceObservationDaily.observation_count).label(
                    "observation_count"
                ),
            )
            .where(PriceObservationDaily.observed_date == coverage_date)
            .group_by(PriceObservationDaily.product_id)
            .cte("product_coverage")
        )
        has_image = (Product.image_url.is_not(None)) & (Product.image_url != "")

        statement = (
            select(
                Product,
                latest_product_price_subquery.label("latest_price_eur"),
            )
            .join(product_coverage, product_coverage.c.product_id == Product.id)
            .order_by(
                has_image.desc(),
                desc(product_coverage.c.retailer_count),
                desc(product_coverage.c.observation_count),
                Product.id,
            )
            .offset(skip)
            .limit(limit)
        )
        rows = (await session.exec(statement)).all()

        return ProductsPublic(
            count=count,
            data=serialize_products_with_latest_price(rows),
        )

    normalized_search = search.lower()
    normalized_search_pattern = f"%{normalized_search}%"
    alias_name = func.lower(ProductAlias.alias_name)
    normalized_alias_name = func.lower(ProductAlias.normalized_alias_name)
    alias_search_filter = or_(
        ProductAlias.retailer_product_code == search,
        alias_name.like(normalized_search_pattern),
        normalized_alias_name.like(normalized_search_pattern),
        alias_name.op("%")(normalized_search),
        normalized_alias_name.op("%")(normalized_search),
    )
    alias_similarity_score = func.greatest(
        func.coalesce(func.similarity(alias_name, normalized_search), 0),
        func.coalesce(func.word_similarity(normalized_search, alias_name), 0),
        func.coalesce(func.similarity(normalized_alias_name, normalized_search), 0),
        func.coalesce(
            func.word_similarity(normalized_search, normalized_alias_name),
            0,
        ),
    )
    alias_scores = (
        select(
            ProductAlias.product_id.label("product_id"),
            func.max(alias_similarity_score).label("alias_score"),
        )
        .where(alias_search_filter)
        .group_by(ProductAlias.product_id)
        .cte("alias_scores")
    )
    product_name = func.lower(Product.name)
    product_brand = func.lower(Product.brand)
    product_category = func.lower(Product.category)
    product_search_filter = or_(
        Product.barcode == search,
        product_name.like(normalized_search_pattern),
        product_brand.like(normalized_search_pattern),
        product_category.like(normalized_search_pattern),
        product_name.op("%")(normalized_search),
        product_brand.op("%")(normalized_search),
        product_category.op("%")(normalized_search),
        alias_scores.c.product_id.is_not(None),
    )
    similarity_score = func.greatest(
        func.coalesce(func.similarity(product_name, normalized_search), 0),
        func.coalesce(func.similarity(product_brand, normalized_search), 0),
        func.coalesce(func.similarity(product_category, normalized_search), 0),
        func.coalesce(alias_scores.c.alias_score, 0),
    )
    has_image = (Product.image_url.is_not(None)) & (Product.image_url != "")

    count_statement = (
        select(func.count())
        .select_from(Product)
        .outerjoin(alias_scores, alias_scores.c.product_id == Product.id)
        .where(product_search_filter)
    )
    count = (await session.exec(count_statement)).one()

    product_coverage = (
        select(
            PriceObservationDaily.product_id.label("product_id"),
            func.count(func.distinct(PriceObservationDaily.retailer_id)).label(
                "retailer_count",
            ),
            func.sum(PriceObservationDaily.observation_count).label(
                "observation_count"
            ),
        )
        .where(PriceObservationDaily.observed_date == coverage_date)
        .group_by(PriceObservationDaily.product_id)
        .cte("product_coverage")
    )

    statement = (
        select(
            Product,
            latest_product_price_subquery.label("latest_price_eur"),
        )
        .outerjoin(alias_scores, alias_scores.c.product_id == Product.id)
        .outerjoin(product_coverage, product_coverage.c.product_id == Product.id)
        .where(product_search_filter)
        .order_by(
            case((Product.barcode == search, 0), else_=1),
            desc(similarity_score),
            has_image.desc(),
            desc(func.coalesce(product_coverage.c.retailer_count, 0)),
            desc(func.coalesce(product_coverage.c.observation_count, 0)),
            Product.id,
        )
        .offset(skip)
        .limit(limit)
    )
    rows = (await session.exec(statement)).all()

    return ProductsPublic(
        count=count,
        data=serialize_products_with_latest_price(rows),
    )


@router.get("/{product_id}", response_model=ProductPublic)
async def read_product(product_id: uuid.UUID, session: SessionDep):
    statement = select(Product).where(Product.id == product_id)
    product = (await session.exec(statement)).one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}/similar", response_model=list[SimilarProductPublic])
async def read_similar_products(
    product_id: uuid.UUID,
    session: SessionDep,
    limit: int = 20,
):
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    limit = max(1, min(limit, 50))
    return [
        SimilarProductPublic(
            product=ProductPublic.model_validate(candidate.product),
            retailers=candidate.retailers,
            latest_price_eur=candidate.latest_price_eur,
            average_price_eur=candidate.average_price_eur,
            latest_observed_date=candidate.latest_observed_date,
            score=candidate.score,
        )
        for candidate in await product_similarity_service.find_similar_products(
            session=session,
            product_id=product_id,
            limit=limit,
        )
    ]


@router.get(
    "/{product_id}/price-observations",
    response_model=list[NestedPriceObservation],
)
async def product_price_observations(product_id: uuid.UUID, session: SessionDep):
    statement = (
        select(PriceObservation)
        .options(
            selectinload(PriceObservation.retailer),
            selectinload(PriceObservation.store),
        )
        .where(PriceObservation.product_id == product_id)
        .order_by(PriceObservation.price_eur)
    )
    price_observations = (await session.exec(statement)).all()
    return price_observations


@router.get(
    "/{product_id}/price-history/retail/chart",
    response_model=list[RetailerDailyRetailPriceHistoryPoint],
)
async def product_daily_retail_price_history_chart(
    product_id: uuid.UUID,
    session: SessionDep,
):
    statement = (
        select(
            Retailer,
            PriceObservationDaily.observed_date,
            PriceObservationDaily.price_eur_avg.label("average_price_eur"),
            PriceObservationDaily.price_eur_min.label("min_price_eur"),
            PriceObservationDaily.price_eur_max.label("max_price_eur"),
            PriceObservationDaily.is_special_sale.label("has_special_sale"),
        )
        .join(Retailer, Retailer.id == PriceObservationDaily.retailer_id)
        .where(PriceObservationDaily.product_id == product_id)
        .order_by(PriceObservationDaily.observed_date, Retailer.name)
    )

    rows = (await session.exec(statement)).all()
    return [
        RetailerDailyRetailPriceHistoryPoint(
            retailer=retailer,
            observed_date=observed_date,
            average_price_eur=average_price_eur,
            min_price_eur=min_price_eur,
            max_price_eur=max_price_eur,
            has_special_sale=bool(has_special_sale),
        )
        for (
            retailer,
            observed_date,
            average_price_eur,
            min_price_eur,
            max_price_eur,
            has_special_sale,
        ) in rows
    ]


@router.get(
    "/{product_id}/price-observations/grouped",
    response_model=list[RetailerPriceObservationSummary],
)
async def grouped_product_price_observations(product_id: uuid.UUID, session: SessionDep):
    latest_observations = (
        select(
            PriceObservationDaily.retailer_id,
            func.max(PriceObservationDaily.observed_date).label("observed_date"),
        )
        .where(PriceObservationDaily.product_id == product_id)
        .group_by(PriceObservationDaily.retailer_id)
        .subquery()
    )

    statement = (
        select(
            Retailer,
            PriceObservationDaily.observed_date.label("observed_date"),
            PriceObservationDaily.price_eur_avg.label("average_price_eur"),
            PriceObservationDaily.price_eur_min.label("min_price_eur"),
            PriceObservationDaily.price_eur_max.label("max_price_eur"),
            (
                PriceObservationDaily.price_eur_min
                != PriceObservationDaily.price_eur_max
            ).label("has_store_price_variance"),
            PriceObservationDaily.unit_price_eur_avg.label("average_unit_price_eur"),
            PriceObservationDaily.unit_price_eur_min.label("min_unit_price_eur"),
            PriceObservationDaily.unit_price_eur_max.label("max_unit_price_eur"),
            PriceObservationDaily.is_special_sale.label("has_special_sale"),
            PriceObservationDaily.observation_count.label("store_count"),
        )
        .join(Retailer, Retailer.id == PriceObservationDaily.retailer_id)
        .join(
            latest_observations,
            (latest_observations.c.retailer_id == PriceObservationDaily.retailer_id)
            & (
                latest_observations.c.observed_date
                == PriceObservationDaily.observed_date
            ),
        )
        .where(PriceObservationDaily.product_id == product_id)
        .order_by(PriceObservationDaily.price_eur_avg)
    )

    rows = (await session.exec(statement)).all()
    return [
        RetailerPriceObservationSummary(
            retailer=retailer,
            observed_date=observed_date,
            average_price_eur=average_price_eur,
            min_price_eur=min_price_eur,
            max_price_eur=max_price_eur,
            average_unit_price_eur=average_unit_price_eur,
            min_unit_price_eur=min_unit_price_eur,
            max_unit_price_eur=max_unit_price_eur,
            store_count=store_count,
            has_store_price_variance=has_store_price_variance,
            has_special_sale=bool(has_special_sale),
        )
        for (
            retailer,
            observed_date,
            average_price_eur,
            min_price_eur,
            max_price_eur,
            has_store_price_variance,
            average_unit_price_eur,
            min_unit_price_eur,
            max_unit_price_eur,
            has_special_sale,
            store_count,
        ) in rows
    ]
