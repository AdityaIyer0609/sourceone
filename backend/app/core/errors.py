from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    status_code = 400

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFound(DomainError):
    code = "NOT_FOUND"
    status_code = 404


class ValidationFailed(DomainError):
    code = "VALIDATION_FAILED"
    status_code = 422


class NotAuthenticated(DomainError):
    code = "NOT_AUTHENTICATED"
    status_code = 401


class PermissionDenied(DomainError):
    code = "PERMISSION_DENIED"
    status_code = 403


class InvalidStateTransition(DomainError):
    code = "INVALID_STATE_TRANSITION"
    status_code = 409


class DuplicateEffectiveFrom(DomainError):
    code = "DUPLICATE_EFFECTIVE_FROM"
    status_code = 409


class PublishedBenchmarkImmutable(DomainError):
    code = "PUBLISHED_BENCHMARK_IMMUTABLE"
    status_code = 409


class StaleRowVersion(DomainError):
    code = "STALE_ROW_VERSION"
    status_code = 409


class SourceRateUnresolved(DomainError):
    code = "SOURCE_RATE_UNRESOLVED"
    status_code = 422


class SourceRateNotEligible(DomainError):
    code = "SOURCE_RATE_NOT_ELIGIBLE"
    status_code = 422


class SourceInactive(DomainError):
    code = "SOURCE_INACTIVE"
    status_code = 422


class FourEyesRequired(DomainError):
    code = "FOUR_EYES_REQUIRED"
    status_code = 403


class CurrencyUnitMismatch(DomainError):
    code = "CURRENCY_OR_UNIT_MISMATCH"
    status_code = 422


class SeriesMismatch(DomainError):
    code = "SERIES_MISMATCH"
    status_code = 422


class DuplicateProductCode(DomainError):
    code = "DUPLICATE_PRODUCT_CODE"
    status_code = 409


class DuplicateProductMapping(DomainError):
    code = "DUPLICATE_PRODUCT_MAPPING"
    status_code = 409


class NegotiationClosed(DomainError):
    code = "NEGOTIATION_CLOSED"
    status_code = 409


class AwaitingCounterparty(DomainError):
    code = "AWAITING_COUNTERPARTY"
    status_code = 409


class DuplicateOrder(DomainError):
    code = "DUPLICATE_ORDER"
    status_code = 409


class OrderClosed(DomainError):
    code = "ORDER_CLOSED"
    status_code = 409


async def _domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error_handler)
