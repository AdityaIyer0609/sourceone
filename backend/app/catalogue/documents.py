"""SourceOne product files. Stored on disk under the app, never read from the ERP."""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue import products as catalogue
from app.core.config import get_settings
from app.core.errors import NotFound, ValidationFailed
from app.identity.service import Actor
from app.models.product_content import ProductDocument
from app.pricing.constants import PricingPermission

MAX_BYTES = 8 * 1024 * 1024


def _text(value: str, field: str, limit: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > limit:
        raise ValidationFailed(f"{field} is required", details={field: value})
    return cleaned


def _directory() -> Path:
    directory = get_settings().document_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _path(document: ProductDocument) -> Path:
    root = _directory().resolve()
    path = (root / document.stored_name).resolve()
    if path.parent != root:
        raise NotFound("Document file not found")
    return path


def list_documents(session: Session, product_code: str, *, active_only: bool) -> list[ProductDocument]:
    product = catalogue.get_product(session, product_code) if not active_only else catalogue.get_active_product(session, product_code)
    stmt = select(ProductDocument).where(ProductDocument.product_id == product.id).order_by(ProductDocument.created_at, ProductDocument.name)
    if active_only:
        stmt = stmt.where(ProductDocument.is_active.is_(True))
    return list(session.scalars(stmt).all())


def save_document(
    session: Session,
    actor: Actor,
    product_code: str,
    *,
    name: str,
    document_type: str,
    filename: str,
    content_type: str,
    content: bytes,
) -> ProductDocument:
    actor.require(PricingPermission.EDIT, PricingPermission.CONFIGURE)
    if not content or len(content) > MAX_BYTES:
        raise ValidationFailed("Choose a file up to 8 MB", details={"field": "file"})
    label = _text(name, "name", 120)
    kind = _text(document_type, "documentType", 32)
    product = catalogue.get_product(session, product_code)
    stored = uuid.uuid4().hex
    document = ProductDocument(
        product_id=product.id,
        name=label,
        document_type=kind,
        stored_name=stored,
        filename=Path(filename or "document").name[:255] or "document",
        content_type=(content_type or "application/octet-stream")[:128],
        byte_size=len(content),
        is_active=True,
        uploaded_by_user_id=actor.user_id,
    )
    _directory().joinpath(stored).write_bytes(content)
    session.add(document)
    session.flush()
    return document


def set_document_active(session: Session, actor: Actor, product_code: str, document_id: uuid.UUID, *, is_active: bool) -> ProductDocument:
    actor.require(PricingPermission.EDIT, PricingPermission.CONFIGURE)
    product = catalogue.get_product(session, product_code)
    document = session.get(ProductDocument, document_id)
    if document is None or document.product_id != product.id:
        raise NotFound("Document not found", details={"documentId": str(document_id)})
    document.is_active = is_active
    session.flush()
    return document


def open_document(session: Session, actor: Actor, product_code: str, document_id: uuid.UUID) -> tuple[ProductDocument, Path]:
    actor.require(PricingPermission.VIEW)
    product = catalogue.get_active_product(session, product_code)
    document = session.get(ProductDocument, document_id)
    if document is None or document.product_id != product.id or not document.is_active:
        raise NotFound("Document not found", details={"documentId": str(document_id)})
    path = _path(document)
    if not path.is_file():
        raise NotFound("Document file not found", details={"documentId": str(document_id)})
    return document, path
