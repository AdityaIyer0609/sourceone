import uuid

from pydantic import Field

from app.schemas.pricing import ApiModel


class AdminUserOut(ApiModel):
    id: uuid.UUID
    full_name: str
    email: str
    organisation: str
    roles: list[str]
    is_active: bool
    is_system: bool


class AdminUserIn(ApiModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    role: str


class UserActiveIn(ApiModel):
    is_active: bool


class UserRoleIn(ApiModel):
    role: str
