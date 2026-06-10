import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import selectinload
from sqlmodel import delete, func, select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.domains.products.models import Product
from app.domains.receipts.models import (
    Receipt,
    ReceiptItem,
    ReceiptPublic,
    ReceiptStatus,
)
from app.domains.receipts.schemas import (
    ReceiptItemReviewPublic,
    ReceiptItemUpdate,
    ReceiptsPublic,
    ReceiptUpdate,
)
from app.domains.receipts.services.ingestion import receipt_ingestion_service

router = APIRouter(prefix="/receipts", tags=["receipts"])


@router.post("", response_model=ReceiptPublic)
async def create_receipt(
    session: SessionDep,
    current_user: CurrentUser,
    retailer_id: uuid.UUID = Form(...),
    store_id: uuid.UUID | None = Form(default=None),
    file: UploadFile = File(...),
) -> Any:
    content = await file.read()
    return await receipt_ingestion_service.create_receipt_from_upload(
        session=session,
        user_id=current_user.id,
        retailer_id=retailer_id,
        store_id=store_id,
        filename=file.filename,
        content=content,
    )


@router.get("", response_model=ReceiptsPublic)
async def read_receipts(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
) -> ReceiptsPublic:
    count_statement = (
        select(func.count())
        .select_from(Receipt)
        .where(
            Receipt.user_id == current_user.id,
        )
    )
    count = (await session.exec(count_statement)).one()

    statement = (
        select(Receipt)
        .where(Receipt.user_id == current_user.id)
        .order_by(Receipt.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    receipts = (await session.exec(statement)).all()
    return ReceiptsPublic(data=receipts, count=count)


@router.get("/{receipt_id}", response_model=ReceiptPublic)
async def read_receipt(
    receipt_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Receipt:
    receipt = await _get_user_receipt(session, current_user.id, receipt_id)
    return receipt


@router.patch("/{receipt_id}", response_model=ReceiptPublic)
async def update_receipt(
    receipt_id: uuid.UUID,
    receipt_in: ReceiptUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Receipt:
    receipt = await _get_user_receipt(session, current_user.id, receipt_id)

    if receipt_in.status == ReceiptStatus.COMPLETED:
        items = await _get_receipt_items(session, receipt.id)
        incomplete_items = [
            item for item in items if item.product_id is None and not item.is_skipped
        ]
        if incomplete_items:
            raise HTTPException(
                status_code=400,
                detail="All receipt items must be matched or skipped before completion",
            )
        receipt.status = ReceiptStatus.COMPLETED
    elif receipt_in.status == ReceiptStatus.DRAFT:
        receipt.status = ReceiptStatus.DRAFT

    session.add(receipt)
    await session.commit()
    await session.refresh(receipt)
    return receipt


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    receipt_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> None:
    receipt = await _get_user_receipt(session, current_user.id, receipt_id)
    file_key = receipt.file_key

    await session.exec(delete(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id))
    await session.delete(receipt)
    await session.commit()

    (Path(settings.RECEIPT_UPLOAD_DIR) / file_key).unlink(missing_ok=True)


@router.get("/{receipt_id}/items", response_model=list[ReceiptItemReviewPublic])
async def read_receipt_items(
    receipt_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> list[ReceiptItem]:
    receipt = await _get_user_receipt(session, current_user.id, receipt_id)
    items = await _get_receipt_items(session, receipt.id)
    return items


@router.patch("/{receipt_id}/items/{item_id}", response_model=ReceiptItemReviewPublic)
async def update_receipt_item(
    receipt_id: uuid.UUID,
    item_id: uuid.UUID,
    item_in: ReceiptItemUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ReceiptItem:
    receipt = await _get_user_receipt(session, current_user.id, receipt_id)
    item = await session.get(ReceiptItem, item_id)
    if item is None or item.receipt_id != receipt.id:
        raise HTTPException(status_code=404, detail="Receipt item not found")
    if receipt.status == ReceiptStatus.COMPLETED:
        raise HTTPException(
            status_code=400, detail="Completed receipts cannot be edited"
        )

    update_data = item_in.model_dump(exclude_unset=True)

    if "product_id" in update_data:
        product_id = update_data["product_id"]
        if product_id is None:
            item.product_id = None
        else:
            product = await session.get(Product, product_id)
            if product is None:
                raise HTTPException(status_code=404, detail="Product not found")
            item.product_id = product.id
            item.is_skipped = False

    if "is_skipped" in update_data:
        item.is_skipped = bool(update_data["is_skipped"])
        if item.is_skipped:
            item.product_id = None

    session.add(item)
    await session.commit()
    return await _get_receipt_item(session, receipt.id, item.id)


async def _get_user_receipt(
    session: SessionDep,
    user_id: uuid.UUID,
    receipt_id: uuid.UUID,
) -> Receipt:
    statement = select(Receipt).where(
        Receipt.id == receipt_id,
        Receipt.user_id == user_id,
    )
    receipt = (await session.exec(statement)).first()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt


async def _get_receipt_item(
    session: SessionDep,
    receipt_id: uuid.UUID,
    item_id: uuid.UUID,
) -> ReceiptItem:
    statement = (
        select(ReceiptItem)
        .options(selectinload(ReceiptItem.product))
        .where(ReceiptItem.id == item_id, ReceiptItem.receipt_id == receipt_id)
    )
    item = (await session.exec(statement)).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Receipt item not found")
    return item


async def _get_receipt_items(session: SessionDep, receipt_id: uuid.UUID) -> list[ReceiptItem]:
    statement = (
        select(ReceiptItem)
        .options(selectinload(ReceiptItem.product))
        .where(ReceiptItem.receipt_id == receipt_id)
        .order_by(ReceiptItem.line_number)
    )
    return list((await session.exec(statement)).all())
