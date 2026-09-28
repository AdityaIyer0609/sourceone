from enum import StrEnum


class OrderPermission(StrEnum):
    PLACE = "order.place"
    FULFIL = "order.fulfil"


class OrderStatus(StrEnum):
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    READY = "ready"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# Fulfilment moves one step at a time; nothing moves backwards.
NEXT_STATUS = {
    OrderStatus.PLACED: OrderStatus.CONFIRMED,
    OrderStatus.CONFIRMED: OrderStatus.PROCESSING,
    OrderStatus.PROCESSING: OrderStatus.READY,
    OrderStatus.READY: OrderStatus.DISPATCHED,
    OrderStatus.DISPATCHED: OrderStatus.DELIVERED,
}
FULFILMENT_FLOW = (
    OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
    OrderStatus.READY, OrderStatus.DISPATCHED, OrderStatus.DELIVERED,
)
CANCELLABLE_STATUSES = (OrderStatus.PLACED, OrderStatus.CONFIRMED)
TERMINAL_STATUSES = (OrderStatus.DELIVERED, OrderStatus.CANCELLED)

NUMBER_SEQUENCE = "order_number_seq"
