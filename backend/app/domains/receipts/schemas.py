import uuid

from sqlmodel import SQLModel

from app.domains.products.models import ProductPublic
from app.domains.receipts.models import (
    ReceiptItemPublic,
    ReceiptPublic,
    ReceiptStatus,
)


class ReceiptItemReviewPublic(ReceiptItemPublic):
    product: ProductPublic | None = None


class ReceiptsPublic(SQLModel):
    data: list[ReceiptPublic]
    count: int


class ReceiptUpdate(SQLModel):
    status: ReceiptStatus | None = None


class ReceiptItemUpdate(SQLModel):
    product_id: uuid.UUID | None = None
    is_skipped: bool | None = None
