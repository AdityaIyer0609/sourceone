from enum import StrEnum


class RequestStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    IN_NEGOTIATION = "in_negotiation"
    CONVERTED = "converted"
    CANCELLED = "cancelled"


NUMBER_SEQUENCE = "purchase_request_number_seq"
