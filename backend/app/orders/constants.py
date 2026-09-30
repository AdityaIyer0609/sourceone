from enum import StrEnum


class OrderPermission(StrEnum):
    PLACE = "order.place"
    FULFIL = "order.fulfil"
    APPROVE = "order.approve"


class OrderStatus(StrEnum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    READY = "ready"
    DISPATCHED = "dispatched"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# Fulfilment moves one step at a time; nothing moves backwards.
NEXT_STATUS = {
    OrderStatus.PLACED: OrderStatus.CONFIRMED,
    OrderStatus.CONFIRMED: OrderStatus.PROCESSING,
    OrderStatus.PROCESSING: OrderStatus.READY,
    OrderStatus.READY: OrderStatus.DISPATCHED,
    OrderStatus.DISPATCHED: OrderStatus.IN_TRANSIT,
    OrderStatus.IN_TRANSIT: OrderStatus.DELIVERED,
}
FULFILMENT_FLOW = (
    OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
    OrderStatus.READY, OrderStatus.DISPATCHED, OrderStatus.IN_TRANSIT, OrderStatus.DELIVERED,
)
SHIPMENT_STATUSES = (OrderStatus.DISPATCHED, OrderStatus.IN_TRANSIT)
CANCELLABLE_STATUSES = (OrderStatus.PLACED, OrderStatus.CONFIRMED)
TERMINAL_STATUSES = (OrderStatus.DELIVERED, OrderStatus.CANCELLED)

NUMBER_SEQUENCE = "order_number_seq"
