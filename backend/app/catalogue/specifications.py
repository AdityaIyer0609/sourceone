"""SourceOne product specifications. Values are stored on the product; nothing here is read from ERP."""

import re

from app.core.errors import ValidationFailed
from app.models.catalogue import Product

# Shown on every product, in this order. A missing value is not specified.
CORE_FIELDS = (
    ("grade", "Grade"),
    ("producer", "Producer"),
    ("mfi", "MFI"),
    ("density", "Density"),
    ("application", "Application"),
    ("quality", "Quality"),
)
KEY = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def clean_specifications(raw: dict | None) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in (raw or {}).items():
        code = str(key).strip().lower()
        if KEY.fullmatch(code) is None:
            raise ValidationFailed("Specification names must be short lowercase words", details={"field": key})
        text = "" if value is None else str(value).strip()
        if not text:
            continue
        if len(text) > 255:
            raise ValidationFailed("A specification value is too long", details={"field": code})
        cleaned[code] = text
    return cleaned


def requirement_snapshot(product: Product) -> list[dict]:
    """Rows with a value, frozen for a request, negotiation, or order."""
    return [
        {"key": row["key"], "label": row["label"], "value": row["value"]}
        for row in specification_rows(product) if row.get("value")
    ]


def specification_rows(product: Product) -> list[dict]:
    stored = {str(key): str(value) for key, value in (product.specifications or {}).items() if value}
    rows = [{"key": key, "label": label, "value": stored.get(key)} for key, label in CORE_FIELDS]
    rows.append({"key": "uom", "label": "UOM", "value": product.uom})
    description = (product.description or "").strip()
    rows.append({"key": "description", "label": "Description", "value": description or None})
    for key in sorted(stored):
        if key not in {item[0] for item in CORE_FIELDS}:
            rows.append({"key": key, "label": key.replace("_", " ").title(), "value": stored[key]})
    return rows
