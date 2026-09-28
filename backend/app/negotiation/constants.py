from enum import StrEnum


class NegotiationPermission(StrEnum):
    BUY = "negotiation.buy"
    SUPPLY = "negotiation.supply"


class NegotiationStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    COUNTERED = "countered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


ACTIVE_STATUSES = (NegotiationStatus.OPEN, NegotiationStatus.COUNTERED)
TERMINAL_STATUSES = (NegotiationStatus.ACCEPTED, NegotiationStatus.REJECTED, NegotiationStatus.CANCELLED)


class BenchmarkSnapshotState(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    RATE_ON_REQUEST = "rate_on_request"


NUMBER_SEQUENCE = "negotiation_number_seq"
