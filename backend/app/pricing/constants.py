from enum import StrEnum


class PricingPermission(StrEnum):
    VIEW = "pricing.view"
    EDIT = "pricing.edit"
    PUBLISH = "pricing.publish"
    CONFIGURE = "pricing.configure"


class SourceType(StrEnum):
    ERP_FEED = "erp_feed"
    MANUAL = "manual"
    EXTERNAL_API = "external_api"
    SUPPLIER_SUBMISSION = "supplier_submission"


class PublishingPolicy(StrEnum):
    REVIEW_REQUIRED = "review_required"


class ImportBatchStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    IGNORED = "ignored"


class Sector(StrEnum):
    DOMESTIC = "DOMESTIC"
    DEEMED = "DEEMED"
    IMPORT = "IMPORT"


class BenchmarkStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PUBLISHED = "published"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


BENCHMARK_TRANSITIONS: dict[BenchmarkStatus, frozenset[BenchmarkStatus]] = {
    BenchmarkStatus.DRAFT: frozenset({BenchmarkStatus.SUBMITTED, BenchmarkStatus.REJECTED}),
    BenchmarkStatus.SUBMITTED: frozenset({BenchmarkStatus.PUBLISHED, BenchmarkStatus.REJECTED}),
    BenchmarkStatus.PUBLISHED: frozenset({BenchmarkStatus.WITHDRAWN}),
    BenchmarkStatus.REJECTED: frozenset(),
    BenchmarkStatus.WITHDRAWN: frozenset(),
}

# Statuses whose rows form the immutable, published timeline of a series.
TIMELINE_STATUSES = (BenchmarkStatus.PUBLISHED, BenchmarkStatus.WITHDRAWN)


class BenchmarkMethod(StrEnum):
    ADOPTED = "adopted"
    MANUAL = "manual"
    AGGREGATED = "aggregated"


class BenchmarkOrigin(StrEnum):
    SYSTEM_SUGGESTION = "system_suggestion"
    HUMAN = "human"


class InputRole(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"


class SeriesVisibility(StrEnum):
    SIGNED_IN_PLATFORM = "signed_in_platform"


SUPPORTED_CURRENCIES = ("INR", "USD")
SUPPORTED_UNITS = ("KG",)

# DomesticPrice1 columns an admin can choose as the benchmark value. Only one is active.
BENCHMARK_PRICE_FIELDS = ("GrandTotal", "Total", "Basic", "UnitPrice")
DEFAULT_BENCHMARK_PRICE_FIELD = "GrandTotal"

PRICE_BASIS_LABELS = {
    "DELIVERED": "Delivered",
    "EX_WORKS": "Ex-works",
    "IMPORT_ORIGIN": "Import quote (origin region)",
}
TAX_BASIS_LABELS = {
    "GST_EXCLUDED": "GST extra",
    "GST_INCLUDED": "GST included",
}
UNIT_LABELS = {"KG": "kg"}

BENCHMARK_PRICE_KIND = "sourceone_benchmark"
BENCHMARK_PRICE_LABEL = "SourceOne benchmark"
ESTIMATE_PRICE_KIND = "estimated_material_value"
ESTIMATE_LABEL = "Estimated material value at SourceOne benchmark"

HISTORY_RANGES_DAYS = {"1D": 1, "7D": 7, "1M": 30, "3M": 90, "1Y": 365}

# Population standard deviation of point-to-point % changes.
VOLATILITY_LOW_BELOW_PCT = 1.0
VOLATILITY_MEDIUM_BELOW_PCT = 3.0


def label_for(labels: dict[str, str], code: str) -> str:
    return labels.get(code, code)
