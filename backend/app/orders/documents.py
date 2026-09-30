"""Fulfilment files for one order. Stored beside product documents, never read from ERP."""

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.errors import NotFound, PermissionDenied, ValidationFailed
from app.identity.service import Actor
from app.models.fulfilment import DOCUMENT_TYPES, OrderDocument
from app.models.order import Order

MAX_BYTES = 8 * 1024 * 1024


def _directory() -> Path:
    from app.core.config import get_settings
    directory = get_settings().document_dir.parent / "order_documents"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _path(document: OrderDocument) -> Path:
    root = _directory().resolve()
    path = (root / document.stored_name).resolve()
    if path.parent != root or not path.is_file():
        raise NotFound("Document file not found", details={"documentId": str(document.id)})
    return path


def _order(session: Session, actor: Actor, order_id: uuid.UUID) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise NotFound("Order not found", details={"orderId": str(order_id)})
    if actor.user_id not in (order.buyer_user_id, order.supplier_user_id):
        raise PermissionDenied("Only the buyer or supplier on this order can open its documents")
    return order


def visible_documents(order: Order) -> list[OrderDocument]:
    """Skip a row whose file is missing so the screen never shows a certificate that was not stored."""
    shown = []
    root = _directory().resolve()
    for document in order.documents:
        path = (root / document.stored_name).resolve()
        if path.parent == root and path.is_file():
            shown.append(document)
    return shown


def save_document(
    session: Session, actor: Actor, order_id: uuid.UUID, *,
    document_type: str, filename: str, content_type: str, content: bytes,
) -> OrderDocument:
    order = _order(session, actor, order_id)
    if actor.user_id != order.supplier_user_id:
        raise PermissionDenied("Only the supplier on this order can attach a document")
    if order.status == "cancelled":
        raise ValidationFailed("A cancelled order cannot receive documents")
    if document_type not in DOCUMENT_TYPES:
        raise ValidationFailed("Choose a fulfilment document type", details={"documentType": document_type})
    if not content or len(content) > MAX_BYTES:
        raise ValidationFailed("Choose a file up to 8 MB", details={"field": "file"})
    stored = uuid.uuid4().hex
    _directory().joinpath(stored).write_bytes(content)
    document = OrderDocument(
        order_id=order.id,
        document_type=document_type,
        stored_name=stored,
        filename=Path(filename or "document").name[:255] or "document",
        content_type=(content_type or "application/octet-stream")[:128],
        byte_size=len(content),
        status="submitted",
        uploaded_by_user_id=actor.user_id,
        created_at=utcnow(),
    )
    session.add(document)
    session.flush()
    return document


def open_document(session: Session, actor: Actor, order_id: uuid.UUID, document_id: uuid.UUID) -> tuple[OrderDocument, Path]:
    order = _order(session, actor, order_id)
    document = session.get(OrderDocument, document_id)
    if document is None or document.order_id != order.id:
        raise NotFound("Document not found", details={"documentId": str(document_id)})
    return document, _path(document)


def review_document(
    session: Session, actor: Actor, order_id: uuid.UUID, document_id: uuid.UUID, *, status: str,
) -> OrderDocument:
    order = _order(session, actor, order_id)
    if actor.user_id != order.buyer_user_id:
        raise PermissionDenied("Only the buyer can accept or reject a document")
    if status not in ("accepted", "rejected"):
        raise ValidationFailed("Accept or reject the document", details={"status": status})
    document = session.get(OrderDocument, document_id)
    if document is None or document.order_id != order.id:
        raise NotFound("Document not found", details={"documentId": str(document_id)})
    _path(document)
    document.status = status
    document.reviewed_by_user_id = actor.user_id
    document.reviewed_at = utcnow()
    session.flush()
    return document
