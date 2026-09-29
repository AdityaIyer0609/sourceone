from enum import StrEnum


class FreightPermission(StrEnum):
    MANAGE = "freight.manage"


ESTIMATE_NOTE = "Estimate only. Negotiation and orders use the agreed price, not this landed cost."
RATE_UNIT = "KG"
