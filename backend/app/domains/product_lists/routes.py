import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import case, literal, nullslast, true
from sqlalchemy.orm import selectinload
from sqlmodel import delete, func, select

from app.api.deps import CurrentUser, SessionDep
from app.domains.common.models import get_datetime_utc
from app.domains.product_lists.models import (
    ProductList,
    ProductListBase,
    ProductListItem,
    ProductListItemAlternative,
    ProductListItemAlternativeCreate,
    ProductListItemAlternativesBulkCreate,
    ProductListPublic,
    ProductListsPublic,
)
from app.domains.product_lists.schemas import (
    ProductListItemAlternativeDetailPublic,
    ProductListItemAlternativesBulkCreateResult,
    ProductListItemCreate,
    ProductListItemDetailPublic,
    ProductListItemUpdate,
    ProductListRetailerPriceHistoryPoint,
    ProductListUpdate,
)
from app.domains.products.models import Product
from app.domains.products.price_observation import PriceObservation
from app.domains.products.retailers import Retailer
from app.domains.receipts.models import Receipt, ReceiptItem

router = APIRouter(prefix="/product-lists", tags=["product-lists"])

PRICE_HISTORY_STALENESS_DAYS = 30


@router.post("", response_model=ProductListPublic)
async def create_product_list(
    list_in: ProductListBase,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductList:
    existing_list = (await session.exec(
        select(ProductList).where(
            ProductList.user_id == current_user.id,
            ProductList.name == list_in.name,
        )
    )).first()
    if existing_list is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product list with this name already exists",
        )

    product_list = ProductList(
        user_id=current_user.id,
        name=list_in.name,
        description=list_in.description,
    )
    session.add(product_list)
    await session.commit()
    await session.refresh(product_list)
    return product_list


@router.post("/from-receipt/{receipt_id}", response_model=ProductListPublic)
async def create_product_list_from_receipt(
    receipt_id: uuid.UUID,
    list_in: ProductListBase,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductList:
    receipt = (await session.exec(
        select(Receipt).where(
            Receipt.id == receipt_id,
            Receipt.user_id == current_user.id,
        )
    )).first()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    existing_list = (await session.exec(
        select(ProductList).where(
            ProductList.user_id == current_user.id,
            ProductList.name == list_in.name,
        )
    )).first()
    if existing_list is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product list with this name already exists",
        )

    receipt_items = (await session.exec(
        select(ReceiptItem)
        .where(
            ReceiptItem.receipt_id == receipt.id,
            ReceiptItem.is_skipped == False,  # noqa: E712
            ReceiptItem.product_id.is_not(None),
        )
        .order_by(ReceiptItem.line_number)
    )).all()
    if not receipt_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Receipt has no matched items to add to a product list",
        )

    quantities: dict[uuid.UUID, Decimal] = {}
    for item in receipt_items:
        if item.product_id is None:
            continue
        quantities[item.product_id] = (
            quantities.get(item.product_id, Decimal("0")) + item.quantity
        )

    product_list = ProductList(
        user_id=current_user.id,
        name=list_in.name,
        description=list_in.description,
    )
    session.add(product_list)
    await session.flush()

    for product_id, quantity in quantities.items():
        session.add(
            ProductListItem(
                product_list_id=product_list.id,
                product_id=product_id,
                quantity=quantity,
            )
        )

    await session.commit()
    await session.refresh(product_list)
    return product_list


@router.get("", response_model=ProductListsPublic)
async def read_product_lists(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> ProductListsPublic:
    count = (await session.exec(
        select(func.count())
        .select_from(ProductList)
        .where(ProductList.user_id == current_user.id)
    )).one()
    product_lists = (await session.exec(
        select(ProductList)
        .where(ProductList.user_id == current_user.id)
        .order_by(ProductList.created_at.desc())
        .offset(skip)
        .limit(limit)
    )).all()

    return ProductListsPublic(data=product_lists, count=count)


@router.get("/{product_list_id}", response_model=ProductListPublic)
async def read_product_list(
    product_list_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductList:
    return await _get_user_product_list(session, current_user.id, product_list_id)


@router.patch("/{product_list_id}", response_model=ProductListPublic)
async def update_product_list(
    product_list_id: uuid.UUID,
    list_in: ProductListUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductList:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    update_data = list_in.model_dump(exclude_unset=True)
    product_list.sqlmodel_update(update_data)
    product_list.updated_at = get_datetime_utc()
    session.add(product_list)
    await session.commit()
    await session.refresh(product_list)
    return product_list


@router.delete("/{product_list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product_list(
    product_list_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    await session.exec(
        delete(ProductListItem).where(
            ProductListItem.product_list_id == product_list.id,
        )
    )
    await session.delete(product_list)
    await session.commit()


@router.get(
    "/{product_list_id}/price-history/retail/chart",
    response_model=list[ProductListRetailerPriceHistoryPoint],
)
async def product_list_retail_price_history_chart(
    product_list_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    alternative_fallback_order: Literal["cheapest", "similar"] = "cheapest",
) -> list[ProductListRetailerPriceHistoryPoint]:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    total_item_count = (await session.exec(
        select(func.count())
        .select_from(ProductListItem)
        .where(ProductListItem.product_list_id == product_list.id)
    )).one()
    if total_item_count == 0:
        return []

    list_items = (
        select(
            ProductListItem.id.label("item_id"),
            ProductListItem.quantity.label("quantity"),
        )
        .where(ProductListItem.product_list_id == product_list.id)
        .subquery("list_items")
    )

    primary_candidates = select(
        ProductListItem.id.label("item_id"),
        ProductListItem.product_id.label("product_id"),
        literal(0).label("fallback_rank"),
        literal(None).label("similarity_score"),
    ).where(ProductListItem.product_list_id == product_list.id)

    alternative_candidates = (
        select(
            ProductListItem.id.label("item_id"),
            ProductListItemAlternative.product_id.label("product_id"),
            literal(1).label("fallback_rank"),
            ProductListItemAlternative.similarity_score.label("similarity_score"),
        )
        .join(
            ProductListItemAlternative,
            ProductListItemAlternative.product_list_item_id == ProductListItem.id,
        )
        .where(ProductListItem.product_list_id == product_list.id)
    )

    candidate_products = primary_candidates.union_all(alternative_candidates).subquery(
        "candidate_products"
    )

    daily_obs = (
        select(
            PriceObservation.retailer_id.label("retailer_id"),
            candidate_products.c.item_id.label("item_id"),
            PriceObservation.product_id.label("product_id"),
            candidate_products.c.fallback_rank.label("fallback_rank"),
            candidate_products.c.similarity_score.label("similarity_score"),
            PriceObservation.observed_date.label("observed_date"),
            func.avg(PriceObservation.price_eur).label("price_eur"),
            func.bool_or(PriceObservation.is_special_sale).label("is_special_sale"),
        )
        .join(
            candidate_products,
            candidate_products.c.product_id == PriceObservation.product_id,
        )
        .where(PriceObservation.price_eur.is_not(None))
        .group_by(
            PriceObservation.retailer_id,
            candidate_products.c.item_id,
            PriceObservation.product_id,
            candidate_products.c.fallback_rank,
            candidate_products.c.similarity_score,
            PriceObservation.observed_date,
        )
        .subquery("daily_obs")
    )

    retailers_sq = select(daily_obs.c.retailer_id).distinct().subquery("retailers")
    sample_dates = select(daily_obs.c.observed_date).distinct().subquery("sample_dates")

    grid = (
        select(
            retailers_sq.c.retailer_id.label("retailer_id"),
            list_items.c.item_id.label("item_id"),
            list_items.c.quantity.label("quantity"),
            sample_dates.c.observed_date.label("observed_date"),
        )
        .select_from(retailers_sq)
        .join(list_items, true())
        .join(sample_dates, true())
        .subquery("grid")
    )

    # Fill each (retailer, list item, date) cell with the nearest-in-time
    # observation inside the staleness window so every retailer prices the
    # full basket on every sampled date. Primary products are always preferred;
    # alternatives are only used as a fallback when no primary price is matched.
    # Past observations are preferred over equally-distant future ones
    # (forward-fill bias), but future observations are used when no past data
    # exists in the window, which is needed for products newly added to a
    # retailer's catalog.
    min_observed_date = grid.c.observed_date - timedelta(
        days=PRICE_HISTORY_STALENESS_DAYS,
    )
    max_observed_date = grid.c.observed_date + timedelta(
        days=PRICE_HISTORY_STALENESS_DAYS,
    )
    date_diff = grid.c.observed_date - daily_obs.c.observed_date
    primary_date_order = case(
        (daily_obs.c.fallback_rank == 0, func.abs(date_diff)),
        else_=0,
    )
    alternative_date_order = case(
        (daily_obs.c.fallback_rank == 1, func.abs(date_diff)),
        else_=0,
    )
    alternative_price_order = case(
        (daily_obs.c.fallback_rank == 1, daily_obs.c.price_eur),
        else_=0,
    )
    alternative_similarity_order = case(
        (daily_obs.c.fallback_rank == 1, daily_obs.c.similarity_score),
        else_=0,
    )
    alternative_order_by = (
        [alternative_price_order.asc(), alternative_date_order.asc()]
        if alternative_fallback_order == "cheapest"
        else [nullslast(alternative_similarity_order.desc()), alternative_date_order.asc()]
    )

    ranked_matches = (
        select(
            grid.c.retailer_id.label("retailer_id"),
            grid.c.observed_date.label("observed_date"),
            grid.c.quantity.label("quantity"),
            daily_obs.c.price_eur.label("price_eur"),
            daily_obs.c.is_special_sale.label("is_special_sale"),
            func.row_number()
            .over(
                partition_by=(
                    grid.c.retailer_id,
                    grid.c.item_id,
                    grid.c.observed_date,
                ),
                order_by=(
                    daily_obs.c.fallback_rank.asc(),
                    primary_date_order.asc(),
                    *alternative_order_by,
                    date_diff.desc(),
                    daily_obs.c.price_eur.asc(),
                ),
            )
            .label("match_rank"),
        )
        .select_from(grid)
        .join(
            daily_obs,
            (daily_obs.c.retailer_id == grid.c.retailer_id)
            & (daily_obs.c.item_id == grid.c.item_id)
            & (daily_obs.c.observed_date >= min_observed_date)
            & (daily_obs.c.observed_date <= max_observed_date),
        )
        .subquery("ranked_matches")
    )

    best_matches = (
        select(ranked_matches)
        .where(ranked_matches.c.match_rank == 1)
        .subquery("best_matches")
    )

    statement = (
        select(
            Retailer,
            best_matches.c.observed_date,
            func.coalesce(
                func.sum(best_matches.c.price_eur * best_matches.c.quantity),
                0,
            ).label("total_price_eur"),
            func.count(best_matches.c.price_eur).label("matched_item_count"),
            func.bool_or(best_matches.c.is_special_sale).label("has_special_sale"),
        )
        .select_from(best_matches)
        .join(Retailer, Retailer.id == best_matches.c.retailer_id)
        .group_by(Retailer.id, best_matches.c.observed_date)
        .order_by(best_matches.c.observed_date, Retailer.name)
    )

    rows = (await session.exec(statement)).all()
    return [
        ProductListRetailerPriceHistoryPoint(
            retailer=retailer,
            observed_date=observed_date,
            total_price_eur=total_price_eur,
            matched_item_count=matched_item_count,
            total_item_count=total_item_count,
            has_missing_prices=matched_item_count < total_item_count,
            has_special_sale=bool(has_special_sale),
        )
        for (
            retailer,
            observed_date,
            total_price_eur,
            matched_item_count,
            has_special_sale,
        ) in rows
    ]


@router.get(
    "/{product_list_id}/items",
    response_model=list[ProductListItemDetailPublic],
)
async def read_product_list_items(
    product_list_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[ProductListItem]:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    return await _get_product_list_items(session, product_list.id)


@router.post(
    "/{product_list_id}/items",
    response_model=ProductListItemDetailPublic,
)
async def create_product_list_item(
    product_list_id: uuid.UUID,
    item_in: ProductListItemCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductListItem:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    product = await session.get(Product, item_in.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    existing_item = (await session.exec(
        select(ProductListItem).where(
            ProductListItem.product_list_id == product_list.id,
            ProductListItem.product_id == product.id,
        )
    )).first()
    if existing_item is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product is already in this list",
        )

    item = ProductListItem(
        product_list_id=product_list.id,
        product_id=product.id,
        quantity=item_in.quantity,
        note=item_in.note,
    )
    session.add(item)
    await session.commit()
    return await _get_product_list_item(session, product_list.id, item.id)


@router.patch(
    "/{product_list_id}/items/{item_id}",
    response_model=ProductListItemDetailPublic,
)
async def update_product_list_item(
    product_list_id: uuid.UUID,
    item_id: uuid.UUID,
    item_in: ProductListItemUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductListItem:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    item = await _get_product_list_item(session, product_list.id, item_id)

    update_data = item_in.model_dump(exclude_unset=True)
    item.sqlmodel_update(update_data)
    item.updated_at = get_datetime_utc()

    session.add(item)
    await session.commit()
    return await _get_product_list_item(session, product_list.id, item.id)


@router.delete(
    "/{product_list_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product_list_item(
    product_list_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    item = await _get_product_list_item(session, product_list.id, item_id)
    await session.exec(
        delete(ProductListItemAlternative).where(
            ProductListItemAlternative.product_list_item_id == item.id,
        ),
    )
    await session.delete(item)
    await session.commit()


@router.get(
    "/{product_list_id}/items/{item_id}/alternatives",
    response_model=list[ProductListItemAlternativeDetailPublic],
)
async def read_product_list_item_alternatives(
    product_list_id: uuid.UUID,
    item_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[ProductListItemAlternative]:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    item = await _get_product_list_item(session, product_list.id, item_id)
    return await _get_product_list_item_alternatives(session, item.id)


@router.post(
    "/{product_list_id}/items/{item_id}/alternatives",
    response_model=ProductListItemAlternativeDetailPublic,
)
async def create_product_list_item_alternative(
    product_list_id: uuid.UUID,
    item_id: uuid.UUID,
    alternative_in: ProductListItemAlternativeCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductListItemAlternative:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    item = await _get_product_list_item(session, product_list.id, item_id)
    product = await session.get(Product, alternative_in.product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    if product.id == item.product_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary product cannot be added as an alternative",
        )

    existing_alternative = (await session.exec(
        select(ProductListItemAlternative).where(
            ProductListItemAlternative.product_list_item_id == item.id,
            ProductListItemAlternative.product_id == product.id,
        ),
    )).first()
    if existing_alternative is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Product is already an alternative for this item",
        )

    alternative = ProductListItemAlternative(
        product_list_item_id=item.id,
        product_id=product.id,
        similarity_score=alternative_in.similarity_score,
    )
    session.add(alternative)
    await session.commit()
    return await _get_product_list_item_alternative(session, item.id, alternative.id)


@router.post(
    "/{product_list_id}/items/{item_id}/alternatives/bulk",
    response_model=ProductListItemAlternativesBulkCreateResult,
)
async def bulk_create_product_list_item_alternatives(
    product_list_id: uuid.UUID,
    item_id: uuid.UUID,
    alternatives_in: ProductListItemAlternativesBulkCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ProductListItemAlternativesBulkCreateResult:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    item = await _get_product_list_item(session, product_list.id, item_id)

    requested_product_ids = list(dict.fromkeys(alternatives_in.product_ids))
    if not requested_product_ids:
        return ProductListItemAlternativesBulkCreateResult(
            data=await _get_product_list_item_alternatives(session, item.id),
            created_count=0,
            skipped_count=0,
        )

    existing_product_ids = set(
        (await session.exec(
            select(Product.id).where(Product.id.in_(requested_product_ids)),
        )).all(),
    )
    missing_product_ids = set(requested_product_ids) - existing_product_ids
    if missing_product_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more products were not found",
        )

    existing_alternative_product_ids = set(
        (await session.exec(
            select(ProductListItemAlternative.product_id).where(
                ProductListItemAlternative.product_list_item_id == item.id,
                ProductListItemAlternative.product_id.in_(requested_product_ids),
            ),
        )).all(),
    )
    product_ids_to_create = [
        product_id
        for product_id in requested_product_ids
        if product_id != item.product_id
        and product_id not in existing_alternative_product_ids
    ]

    for product_id in product_ids_to_create:
        session.add(
            ProductListItemAlternative(
                product_list_item_id=item.id,
                product_id=product_id,
                similarity_score=alternatives_in.similarity_scores.get(product_id),
            ),
        )

    await session.commit()

    return ProductListItemAlternativesBulkCreateResult(
        data=await _get_product_list_item_alternatives(session, item.id),
        created_count=len(product_ids_to_create),
        skipped_count=len(requested_product_ids) - len(product_ids_to_create),
    )


@router.delete(
    "/{product_list_id}/items/{item_id}/alternatives/{alternative_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_product_list_item_alternative(
    product_list_id: uuid.UUID,
    item_id: uuid.UUID,
    alternative_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    product_list = await _get_user_product_list(session, current_user.id, product_list_id)
    item = await _get_product_list_item(session, product_list.id, item_id)
    alternative = await _get_product_list_item_alternative(
        session,
        item.id,
        alternative_id,
    )
    await session.delete(alternative)
    await session.commit()


async def _get_user_product_list(
    session: SessionDep,
    user_id: uuid.UUID,
    product_list_id: uuid.UUID,
) -> ProductList:
    product_list = (await session.exec(
        select(ProductList).where(
            ProductList.id == product_list_id,
            ProductList.user_id == user_id,
        )
    )).first()
    if product_list is None:
        raise HTTPException(status_code=404, detail="Product list not found")
    return product_list


async def _get_product_list_item(
    session: SessionDep,
    product_list_id: uuid.UUID,
    item_id: uuid.UUID,
) -> ProductListItem:
    item = (await session.exec(
        select(ProductListItem)
        .options(
            selectinload(ProductListItem.product),
            selectinload(ProductListItem.alternatives).selectinload(
                ProductListItemAlternative.product
            ),
        )
        .where(
            ProductListItem.id == item_id,
            ProductListItem.product_list_id == product_list_id,
        )
    )).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Product list item not found")
    return item


async def _get_product_list_item_alternative(
    session: SessionDep,
    product_list_item_id: uuid.UUID,
    alternative_id: uuid.UUID,
) -> ProductListItemAlternative:
    alternative = (await session.exec(
        select(ProductListItemAlternative)
        .options(selectinload(ProductListItemAlternative.product))
        .where(
            ProductListItemAlternative.id == alternative_id,
            ProductListItemAlternative.product_list_item_id == product_list_item_id,
        ),
    )).first()
    if alternative is None:
        raise HTTPException(
            status_code=404, detail="Product list item alternative not found"
        )
    return alternative


async def _get_product_list_item_alternatives(
    session: SessionDep,
    product_list_item_id: uuid.UUID,
) -> list[ProductListItemAlternative]:
    return list(
        (await session.exec(
            select(ProductListItemAlternative)
            .options(selectinload(ProductListItemAlternative.product))
            .where(
                ProductListItemAlternative.product_list_item_id == product_list_item_id
            )
            .order_by(
                ProductListItemAlternative.created_at, ProductListItemAlternative.id
            ),
        )).all()
    )


async def _get_product_list_items(
    session: SessionDep,
    product_list_id: uuid.UUID,
) -> list[ProductListItem]:
    return list(
        (await session.exec(
            select(ProductListItem)
            .options(
                selectinload(ProductListItem.product),
                selectinload(ProductListItem.alternatives).selectinload(
                    ProductListItemAlternative.product
                ),
            )
            .where(ProductListItem.product_list_id == product_list_id)
            .order_by(ProductListItem.created_at, ProductListItem.id)
        )).all()
    )
