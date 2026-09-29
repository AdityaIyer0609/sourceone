"""Buyer procurement dashboard. Figures come from orders and negotiations; spend is the agreed order total."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.api.v1.negotiations import quantity_text
from app.dashboard.service import buyer_dashboard
from app.identity.service import Actor
from app.negotiation.constants import NegotiationPermission
from app.orders.constants import OrderPermission
from app.schemas.dashboard import DashboardActivityOut, DashboardOut, SpendOut
from app.schemas.pricing import Money

router = APIRouter(tags=["dashboard"])

Buyer = Annotated[Actor, Depends(require_any(OrderPermission.PLACE, NegotiationPermission.BUY))]


def _money(amount: Decimal | None, currency: str, places: int) -> Money | None:
    if amount is None:
        return None
    return Money(amount=f"{amount:.{places}f}", currency=currency)


def _activity(row: dict) -> DashboardActivityOut:
    places = 2 if row["value_kind"] == "order_total" else 4
    return DashboardActivityOut(
        kind=row["kind"],
        id=row["id"],
        reference=row["reference"],
        product_name=row["product_name"],
        counterparty=row["counterparty"],
        quantity=quantity_text(row["quantity"]),
        uom=row["uom"],
        value=_money(row["value"], row["currency"], places),
        value_kind=row["value_kind"],
        status=row["status"],
        updated_at=row["updated_at"],
        can_reorder=row["can_reorder"],
    )


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: DbSession, actor: Buyer):
    data = buyer_dashboard(db, actor)
    return DashboardOut(
        active_orders=data["active_orders"],
        open_negotiations=data["open_negotiations"],
        pending_actions=data["pending_actions"],
        spend=[SpendOut(currency=row["currency"], amount=f"{row['amount']:.2f}") for row in data["spend"]],
        orders_by_status=data["orders_by_status"],
        recent_orders=[_activity(row) for row in data["recent_orders"]],
        recent_negotiations=[_activity(row) for row in data["recent_negotiations"]],
    )
