"""When this is on, buyers and suppliers do not see other suppliers. Admins still see every feature."""

from app.core.config import get_settings
from app.identity.constants import IdentityPermission
from app.identity.service import Actor
from app.pricing.constants import PricingPermission


def suppliers_hidden(actor: Actor) -> bool:
    if not get_settings().hide_suppliers:
        return False
    if actor.has(IdentityPermission.MANAGE) or actor.has(PricingPermission.CONFIGURE) or actor.has(PricingPermission.PUBLISH):
        return False
    return True
