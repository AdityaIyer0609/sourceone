"""Product documents and questions. Files stay in SourceOne; nothing is read from the ERP."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import DbSession, require_any
from app.catalogue import documents, questions
from app.identity.service import Actor
from app.models.product_content import ProductDocument, ProductQuestion
from app.negotiation.constants import NegotiationPermission
from app.pricing.constants import PricingPermission
from app.schemas.product_content import (
    AnswerOut,
    DocumentActiveIn,
    DocumentOut,
    QuestionIn,
    QuestionListOut,
    QuestionOut,
)

router = APIRouter(tags=["product-content"])

Viewer = Annotated[Actor, Depends(require_any(PricingPermission.VIEW))]
Editor = Annotated[Actor, Depends(require_any(PricingPermission.EDIT, PricingPermission.CONFIGURE))]
Buyer = Annotated[Actor, Depends(require_any(NegotiationPermission.BUY))]
Supplier = Annotated[Actor, Depends(require_any(NegotiationPermission.SUPPLY))]


def _document(document: ProductDocument) -> DocumentOut:
    return DocumentOut(
        id=document.id, name=document.name, document_type=document.document_type,
        filename=document.filename, is_active=document.is_active, created_at=document.created_at,
    )


def _question(question: ProductQuestion) -> QuestionOut:
    return QuestionOut(
        id=question.id,
        body=question.body,
        asked_by=question.buyer.full_name,
        organisation=question.buyer.organisation.name,
        status=question.status,
        created_at=question.created_at,
        answers=[
            AnswerOut(
                id=answer.id, body=answer.body, supplier_name=answer.supplier.full_name,
                organisation=answer.supplier.organisation.name, created_at=answer.created_at,
            )
            for answer in question.answers
        ],
    )


@router.get("/products/{product_code}/documents", response_model=list[DocumentOut])
def list_documents(product_code: str, db: DbSession, _: Viewer):
    return [_document(row) for row in documents.list_documents(db, product_code, active_only=True)]


@router.get("/products/{product_code}/documents/{document_id}/file")
def download_document(product_code: str, document_id: uuid.UUID, db: DbSession, actor: Viewer):
    document, path = documents.open_document(db, actor, product_code, document_id)
    return FileResponse(path, media_type=document.content_type, filename=document.filename)


@router.get("/admin/products/{product_code}/documents", response_model=list[DocumentOut])
def list_admin_documents(product_code: str, db: DbSession, _: Editor):
    return [_document(row) for row in documents.list_documents(db, product_code, active_only=False)]


@router.post("/admin/products/{product_code}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    product_code: str,
    db: DbSession,
    actor: Editor,
    name: Annotated[str, Form()],
    documentType: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    content = await file.read()
    document = documents.save_document(
        db, actor, product_code, name=name, document_type=documentType,
        filename=file.filename or "document", content_type=file.content_type or "application/octet-stream",
        content=content,
    )
    db.commit()
    return _document(document)


@router.post("/admin/products/{product_code}/documents/{document_id}/active", response_model=DocumentOut)
def set_document_active(
    product_code: str, document_id: uuid.UUID, body: DocumentActiveIn, db: DbSession, actor: Editor,
):
    document = documents.set_document_active(db, actor, product_code, document_id, is_active=body.is_active)
    db.commit()
    return _document(document)


@router.get("/products/{product_code}/questions", response_model=QuestionListOut)
def list_questions(product_code: str, db: DbSession, actor: Viewer):
    return QuestionListOut(
        can_ask=actor.has(NegotiationPermission.BUY),
        can_answer=questions.can_answer(db, actor, product_code),
        questions=[_question(row) for row in questions.list_questions(db, product_code)],
    )


@router.post("/products/{product_code}/questions", response_model=QuestionOut, status_code=201)
def ask_question(product_code: str, body: QuestionIn, db: DbSession, actor: Buyer):
    question = questions.ask(db, actor, product_code, body.body)
    db.commit()
    return _question(question)


@router.post("/products/{product_code}/questions/{question_id}/answers", response_model=QuestionOut, status_code=201)
def answer_question(product_code: str, question_id: uuid.UUID, body: QuestionIn, db: DbSession, actor: Supplier):
    question = questions.answer(db, actor, product_code, question_id, body.body)
    db.commit()
    return _question(question)
