from typing import Literal

from pydantic import Field

from app.schemas.pricing import ApiModel, SpecificationOut


class ProductIn(ApiModel):
    product_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=64)
    subcategory: str | None = Field(default=None, max_length=64)
    description: str | None = None
    uom: str = Field(min_length=1, max_length=16)
    is_active: bool = True
    specifications: dict[str, str | None] | None = None


class ProductEditIn(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=64)
    subcategory: str | None = Field(default=None, max_length=64)
    description: str | None = None
    specifications: dict[str, str | None] | None = None


class ProductActiveIn(ApiModel):
    is_active: bool


class SeriesMapIn(ApiModel):
    series_code: str = Field(min_length=1, max_length=64)
    display_order: int = 0


class SeriesMapActiveIn(ApiModel):
    is_active: bool


class ProductSeriesOut(ApiModel):
    series_code: str
    display_name: str
    currency: str
    display_order: int
    is_active: bool
    availability: Literal["available", "rate_on_request"]


class AdminProductOut(ApiModel):
    product_code: str
    name: str
    category: str
    subcategory: str | None
    description: str | None
    uom: str
    is_active: bool
    benchmark_status: Literal["available", "rate_on_request"]
    listing_count: int
    series: list[ProductSeriesOut]
    specifications: list[SpecificationOut]
