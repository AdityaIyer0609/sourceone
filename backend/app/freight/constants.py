from decimal import Decimal
from enum import StrEnum


class FreightPermission(StrEnum):
    MANAGE = "freight.manage"


ESTIMATE_NOTE = "Estimate only. Negotiation and orders use the agreed price, not this landed cost."
DEFAULT_NOTE = "Default rate per kg. No lane or PIN zone matched. This is not a measured distance. Estimate only."
DISTANCE_NOTE = "Estimated road distance. Distance-based freight only. Not the supplier asking price, benchmark, or order price."
RATE_UNIT = "KG"
# Used for the road-distance option when an admin has not saved a ₹/km rate.
DEFAULT_RATE_PER_KM = Decimal("2.0000")
