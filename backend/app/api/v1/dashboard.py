"""Buyer procurement dashboard. Figures come from orders and negotiations; spend is the agreed order total."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_any
from app.api.v1.negotiations import quantity_text
from app.dashboard.service import buyer_dashboard, supplier_dashboard
from app.identity.service import Actor
from app.negotiation.constants import NegotiationPermission
from app.orders.constants import OrderPermission
from app.schemas.dashboard import (
    AlertOut,
    DashboardActivityOut,
    DashboardOut,
    DeliveryOut,
    MetricOut,
    SpendOut,
    SpendSliceOut,
    SupplierDashboardOut,
    SupplierDocumentNoteOut,
    SupplierListingNoteOut,
    SupplierPanelOut,
    SupplierPerformanceOut,
    SupplierWorkOut,
    VarianceOut,
)
from app.schemas.pricing import Money
from app.schemas.supplier import CountRateOut, ResponseTimeOut

router = APIRouter(tags=["dashboard"])

Buyer = Annotated[Actor, Depends(require_any(OrderPermission.PLACE, NegotiationPermission.BUY))]
SupplierActor = Annotated[Actor, Depends(require_any(OrderPermission.FULFIL, NegotiationPermission.SUPPLY))]


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


def _metric(row: dict) -> MetricOut:
    return MetricOut(
        available=row["available"],
        note=row["note"],
        percent=row.get("percent"),
        average_hours=row.get("average_hours"),
    )


def _slice(row: dict) -> SpendSliceOut:
    return SpendSliceOut(
        label=row["label"], currency=row["currency"], amount=f"{row['amount']:.2f}", order_count=row["order_count"],
    )


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(db: DbSession, actor: Buyer):
    data = buyer_dashboard(db, actor)
    return DashboardOut(
        active_orders=data["active_orders"],
        open_negotiations=data["open_negotiations"],
        open_requests=data["open_requests"],
        pending_actions=data["pending_actions"],
        spend=[SpendOut(currency=row["currency"], amount=f"{row['amount']:.2f}") for row in data["spend"]],
        spend_by_product=[_slice(row) for row in data["spend_by_product"]],
        spend_by_supplier=[_slice(row) for row in data["spend_by_supplier"]],
        variance=[
            VarianceOut(
                order_id=row["order_id"],
                order_number=row["order_number"],
                product_name=row["product_name"],
                agreed_unit_price=_money(row["agreed_unit_price"], row["currency"], 4),
                snapshot=_money(row["snapshot"], row["currency"], 4),
                unit_difference=_money(row["unit_difference"], row["currency"], 4),
                material_difference=_money(row["material_difference"], row["currency"], 2),
            )
            for row in data["variance"]
        ],
        delivery=DeliveryOut(**data["delivery"]),
        suppliers=[
            SupplierPanelOut(
                organisation_id=row["organisation_id"],
                organisation=row["organisation"],
                acceptance=_metric(row["acceptance"]),
                order_cancellation=_metric(row["order_cancellation"]),
                quality=_metric(row["quality"]),
                response_time=_metric(row["response_time"]),
            )
            for row in data["suppliers"]
        ],
        alerts=[AlertOut(**row) for row in data["alerts"]],
        orders_by_status=data["orders_by_status"],
        recent_orders=[_activity(row) for row in data["recent_orders"]],
        recent_negotiations=[_activity(row) for row in data["recent_negotiations"]],
    )


def _rate(row: dict) -> CountRateOut:
    return CountRateOut(
        available=row["available"], note=row["note"], count=row["count"], total=row["total"], percent=row.get("percent"),
    )


@router.get("/supplier-dashboard", response_model=SupplierDashboardOut)
def get_supplier_dashboard(db: DbSession, actor: SupplierActor):
    data = supplier_dashboard(db, actor)
    rates = data["performance"]
    return SupplierDashboardOut(
        open_requests=data["open_requests"],
        open_negotiations=data["open_negotiations"],
        orders_to_confirm=data["orders_to_confirm"],
        listings_to_review=data["listings_to_review"],
        requests=[SupplierWorkOut(**row) for row in data["requests"]],
        negotiations=[SupplierWorkOut(**row) for row in data["negotiations"]],
        orders=[SupplierWorkOut(**row) for row in data["orders"]],
        listings=[
            SupplierListingNoteOut(
                id=row["id"],
                product_code=row["product_code"],
                product_name=row["product_name"],
                availability=row["availability"],
                is_active=row["is_active"],
                asking_price=_money(row["asking_price"], row["currency"], 4),
            )
            for row in data["listings"]
        ],
        documents=[SupplierDocumentNoteOut(**row) for row in data["documents"]],
        performance=SupplierPerformanceOut(
            acceptance=_rate(rates["acceptance"]),
            order_cancellation=_rate(rates["order_cancellation"]),
            on_time_delivery=_rate(rates["on_time_delivery"]),
            quality=_rate(rates["quality"]),
            response_time=ResponseTimeOut(**rates["response_time"]),
        ),
        alerts=[AlertOut(**row) for row in data["alerts"]],
    )
