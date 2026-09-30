"""Explain which listed suppliers fit a quantity and destination. No score and no invented distance."""

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from app.catalogue import products as catalogue
from app.catalogue.listings import eligible_listings
from app.core.errors import ValidationFailed
from app.freight import service as freight
from app.pricing.constants import SUPPORTED_UNITS
from app.suppliers.service import performance

PIN = re.compile(r"^[1-9][0-9]{5}$")
AVAILABILITY_LABEL = {"in_stock": "in stock", "limited": "limited", "on_request": "on request"}


def _quantity_text(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _money(amount: Decimal, currency: str) -> dict:
    return {"amount": f"{amount:.4f}", "currency": currency}


def _performance_reasons(rates: dict) -> list[str]:
    response = rates["response_time"]
    acceptance = rates["acceptance"]
    cancellation = rates["order_cancellation"]
    reasons = []
    if response["available"]:
        reasons.append(
            f"Average response time is {response['average_hours']} hours from {response['sample_count']} supplier replies"
        )
    else:
        reasons.append("Response time is not calculated yet")
    if acceptance["available"]:
        reasons.append(
            f"Acceptance is {acceptance['percent']}% from {acceptance['count']} of {acceptance['total']} decided negotiations"
        )
    else:
        reasons.append("Acceptance is not calculated yet")
    if cancellation["available"]:
        reasons.append(
            f"Order cancellation is {cancellation['percent']}% from {cancellation['count']} of {cancellation['total']} orders"
        )
    else:
        reasons.append("Order cancellation is not calculated yet")
    reasons.append("On-time delivery is not calculated yet")
    reasons.append("Quality history is not calculated yet")
    return reasons


def _freight_reason(status: str, match: str | None, amount: Decimal | None, currency: str) -> str:
    if status != "estimated" or amount is None:
        return "Freight is on request because no saved lane matches this dispatch PIN and destination"
    shown = f"{amount:.4f} {currency}"
    if match == "lane":
        return f"Freight {shown} is estimated from a saved lane"
    if match == "zone":
        return f"Freight {shown} is estimated from a saved zone rule"
    if match == "default":
        return f"Freight {shown} is estimated from the default rate"
    return f"Freight {shown} is estimated"


def match_suppliers(
    session: Session,
    *,
    product_code: str,
    quantity: Decimal,
    uom: str,
    destination_pin: str,
    currency: str | None = None,
) -> dict:
    if quantity <= 0:
        raise ValidationFailed("Quantity must be greater than zero", details={"quantity": str(quantity)})
    unit = uom.strip().upper()
    if unit not in SUPPORTED_UNITS:
        raise ValidationFailed("Quantity unit is not supported", details={"uom": uom})
    pin = destination_pin.strip()
    if PIN.fullmatch(pin) is None:
        raise ValidationFailed("Delivery PIN must be 6 digits", details={"destinationPin": pin})
    product = catalogue.get_active_product(session, product_code)
    if unit != product.uom:
        raise ValidationFailed("Quantity unit must match the product", details={"uom": unit, "productUom": product.uom})

    rows = []
    for listing in eligible_listings(session, product, currency=currency):
        quote = freight.estimate(
            session,
            supplier_user_id=listing.supplier_user_id,
            product_code=product.product_code,
            quantity=quantity,
            destination_pin=pin,
            include_distance=False,
        )
        origin = quote["origin_pin"]
        meets = quantity >= listing.minimum_quantity
        rates = performance(session, listing.supplier.organisation_id)
        reasons = [
            f"Lists {product.name}",
            (
                f"Quantity {_quantity_text(quantity)} {unit} meets the minimum of {_quantity_text(listing.minimum_quantity)} {listing.uom}"
                if meets else
                f"Quantity {_quantity_text(quantity)} {unit} is below the minimum of {_quantity_text(listing.minimum_quantity)} {listing.uom}"
            ),
            f"Availability is {AVAILABILITY_LABEL.get(listing.availability, listing.availability)}",
        ]
        if origin:
            label = f" ({quote['origin_label']})" if quote["origin_label"] else ""
            reasons.append(f"Dispatch PIN {origin}{label}")
        else:
            reasons.append("No dispatch PIN is stored, so a freight lane cannot be matched")
        freight_status = "estimated" if quote["freight"] is not None else "on_request"
        reasons.append(_freight_reason(freight_status, quote["match"], quote["freight"], listing.currency))
        reasons.extend(_performance_reasons(rates))
        rows.append({
            "supplier_user_id": listing.supplier_user_id,
            "supplier_name": listing.supplier.full_name,
            "organisation": listing.supplier.organisation.name,
            "organisation_id": listing.supplier.organisation_id,
            "asking_price": _money(listing.asking_price, listing.currency),
            "minimum_quantity": _quantity_text(listing.minimum_quantity),
            "uom": listing.uom,
            "availability": listing.availability,
            "origin_pin": origin,
            "origin_label": quote["origin_label"],
            "meets_minimum": meets,
            "freight_status": freight_status,
            "freight": _money(quote["freight"], listing.currency) if quote["freight"] is not None else None,
            "freight_match": quote["match"] if freight_status == "estimated" else None,
            "reasons": reasons,
            **rates,
        })
    rows.sort(key=lambda row: (
        Decimal(row["asking_price"]["amount"]),
        0 if row["freight_status"] == "estimated" else 1,
        row["organisation"].casefold(),
    ))
    return {
        "product_code": product.product_code,
        "quantity": _quantity_text(quantity),
        "uom": unit,
        "destination_pin": pin,
        "matches": rows,
    }
