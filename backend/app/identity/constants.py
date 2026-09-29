from enum import StrEnum


class IdentityPermission(StrEnum):
    MANAGE = "identity.manage"


ROLES = ("platform_admin", "pricing_admin", "buyer", "supplier")
