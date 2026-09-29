import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel


class DocumentOut(ApiModel):
    id: uuid.UUID
    name: str
    document_type: str
    filename: str
    is_active: bool
    created_at: datetime


class DocumentActiveIn(ApiModel):
    is_active: bool


class AnswerOut(ApiModel):
    id: uuid.UUID
    body: str
    supplier_name: str
    organisation: str
    created_at: datetime


class QuestionOut(ApiModel):
    id: uuid.UUID
    body: str
    asked_by: str
    organisation: str
    status: Literal["open", "answered"]
    created_at: datetime
    answers: list[AnswerOut]


class QuestionListOut(ApiModel):
    can_ask: bool
    can_answer: bool
    questions: list[QuestionOut]


class QuestionIn(ApiModel):
    body: str = Field(min_length=1, max_length=2000)
