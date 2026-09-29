from pydantic import Field

from app.schemas.pricing import ApiModel


class LoginIn(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class UserOut(ApiModel):
    email: str
    full_name: str
    organisation: str
    roles: list[str]


class LoginOut(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
