import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.domains.receipts.models import Receipt, ReceiptItem, ReceiptStatus
from app.domains.receipts.services.parser import (
    UnsupportedReceiptParserError,
    get_receipt_parser,
)
from app.domains.receipts.services.product_matcher import receipt_product_matcher
from app.models.retailer import Retailer
from app.models.store import Store


class ReceiptIngestionService:
    async def create_receipt_from_upload(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        retailer_id: uuid.UUID,
        store_id: uuid.UUID | None,
        filename: str | None,
        content: bytes,
    ) -> Receipt:
        retailer = await self._get_retailer(session, retailer_id)
        try:
            parser = get_receipt_parser(retailer.name)
        except UnsupportedReceiptParserError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        await self._validate_store(session, retailer.id, store_id)

        parsed_receipt = await parser.parse(content)
        file_key = self._store_receipt_file(content=content, filename=filename)

        receipt = Receipt(
            retailer_id=retailer.id,
            store_id=store_id,
            user_id=user_id,
            purchase_datetime=parsed_receipt.purchase_datetime,
            total_eur=parsed_receipt.total_eur,
            file_key=file_key,
            status=ReceiptStatus.DRAFT,
            raw_text=parsed_receipt.raw_text,
        )
        session.add(receipt)
        await session.flush()

        receipt_items: list[ReceiptItem] = []
        for parsed_item in parsed_receipt.items:
            product = await receipt_product_matcher.find_matching_product(
                session,
                retailer.id,
                parsed_item,
            )
            if product is not None:
                await receipt_product_matcher.create_or_update_product_alias(
                    session=session,
                    retailer_id=retailer.id,
                    parsed_item=parsed_item,
                    product=product,
                )
            receipt_items.append(
                ReceiptItem(
                    receipt_id=receipt.id,
                    product_id=product.id if product else None,
                    line_number=parsed_item.line_number,
                    raw_name=parsed_item.raw_name,
                    normalized_raw_name=parsed_item.normalized_raw_name,
                    quantity=parsed_item.quantity,
                    unit_of_measure=parsed_item.unit_of_measure,
                    unit_price_eur=parsed_item.unit_price_eur,
                    line_total_eur=parsed_item.line_total_eur,
                ),
            )

        session.add_all(receipt_items)
        await session.commit()
        await session.refresh(receipt)
        return receipt

    async def _get_retailer(
        self, session: AsyncSession, retailer_id: uuid.UUID
    ) -> Retailer:
        retailer = await session.get(Retailer, retailer_id)
        if retailer is None:
            raise HTTPException(status_code=404, detail="Retailer not found")
        return retailer

    async def _validate_store(
        self,
        session: AsyncSession,
        retailer_id: uuid.UUID,
        store_id: uuid.UUID | None,
    ) -> None:
        if store_id is None:
            return
        store = await session.get(Store, store_id)
        if store is None or store.retailer_id != retailer_id:
            raise HTTPException(status_code=400, detail="Invalid store for retailer")

    def _store_receipt_file(self, content: bytes, filename: str | None) -> str:
        upload_dir = Path(settings.RECEIPT_UPLOAD_DIR)
        upload_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename or "receipt.pdf").suffix or ".pdf"
        file_key = f"{uuid.uuid4()}{suffix}"
        (upload_dir / file_key).write_bytes(content)
        return file_key


receipt_ingestion_service = ReceiptIngestionService()
