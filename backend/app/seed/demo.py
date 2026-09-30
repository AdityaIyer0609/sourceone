"""Demo data for the SourceOne V1 pricing demo.

    python -m app.seed.demo [--reset]

All ERP rows below are synthetic fixtures shaped like the ERP price list (DomesticPrice1). They are
not read from, and do not imply, a live ERP connection. Every benchmark flow goes through the
service layer, so the seeded data obeys the same lifecycle and four-eyes rules as the API.
"""

import argparse
import math
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.catalogue import market_average
from app.catalogue import products
from app.catalogue.resolver import normalize_text
from app.core.clock import business_today, start_of_business_day, utcnow
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.identity.passwords import hash_password
from app.identity.service import actor_for
from app.models.catalogue import Grade, GradeEquivalence, Market, MarketAlias, Producer, ProducerGradeAlias, Product
from app.freight.constants import DEFAULT_RATE_PER_KM
from app.models.freight import FreightDistanceRate, FreightRule
from app.models.listing import AskingPriceAverage, SupplierListing
from app.models.identity import Organisation, Role, User, UserRole
from app.models.pricing import RateSeries, RateSource, SourceRate
from app.negotiation import service as negotiation_service
from app.orders import service as order_service
from app.orders.constants import NEXT_STATUS, OrderStatus
from app.pricing import ingestion, service
from app.pricing.constants import PublishingPolicy, SeriesVisibility, SourceType

ERP_SOURCE_CODE = "ERP-DOMESTICPRICE1-DEMO"
DEMO_NOTE = "DEMO FIXTURE: synthetic rows shaped like ERP DomesticPrice1; not from a live ERP connection."

DEMO_TABLES = (
    "product_answers", "product_questions", "product_documents", "requirement_responses", "order_documents", "purchase_request_suppliers", "purchase_requests", "pin_coordinates", "road_distances", "freight_distance_rates", "freight_defaults", "freight_rules", "asking_price_averages", "supplier_listings", "erp_price_row_imports", "erp_grades", "erp_customers", "erp_sync_runs", "order_status_events", "order_approvals", "orders", "negotiation_versions", "negotiations", "product_rate_series", "products", "pricing_audit_events", "benchmark_rate_inputs", "benchmark_rates", "source_rates", "import_batches",
    "rate_series", "rate_sources", "market_aliases", "grade_equivalence", "producer_grade_aliases",
    "markets", "grades", "producers", "user_roles", "users", "organisations",
)

ERP_PROFILE = {
    "table": "DomesticPrice1",
    "row_key_field": "SrNo",
    "as_of_field": "SysDate",
    "value_field": "UnitPrice",
    "must_equal_fields": ["Basic", "Total", "GrandTotal"],
    "must_be_empty_fields": ["CashDis", "LocDis", "Trade", "Special", "QD", "AQD", "MOU", "Frieght", "GSTAMT", "QtySlab"],
    "unit": "KG",
    "fields": {
        "producer": "Company",
        "quality": "Quality",
        "grade": "Grade",
        "location": "Location",
        "sector": "Sector",
        "application": "Appilcation",
        "currency": "Currency",
    },
    "identity_fields": ["producer", "quality", "grade", "location", "sector", "application"],
    "route_separator": " to ",
    "route_market": "destination",
    "sectors": {
        "DOMESTIC": {"code": "DOMESTIC", "price_basis": "DELIVERED", "tax_basis": "GST_EXCLUDED", "benchmark_eligible": True},
        "DEEMED": {"code": "DEEMED", "price_basis": "DELIVERED", "tax_basis": "GST_EXCLUDED", "benchmark_eligible": False},
        "IMPORT": {"code": "IMPORT", "price_basis": "IMPORT_ORIGIN", "tax_basis": "GST_EXCLUDED", "benchmark_eligible": True},
    },
    "freight": "not_added",
    "gst": "excluded",
    "qty_slabs": "ignored",
    "fx": "none",
}

# Batch offsets in days before today (business timezone).
BATCH_OFFSETS = (36, 29, 22, 15, 8, 3)

# (SrNo, Company, Quality, Grade, Location, Sector, Appilcation, Currency, values per batch; None = row absent)
ERP_LINES = [
    (1, "Reliance", "PP", "H030SG", "Jamnagar to Ahmedabad", "Domestic", "Raffia", "INR",
     ["97.50", "98.25", "98.25", "99.10", "98.60", "99.40"]),
    (2, "Reliance", "PP", "H030SG", "Jamnagar to Ahmedabad", "Deemed", "Raffia", "INR",
     ["88.70", "89.40", "89.40", "90.20", "89.70", "90.45"]),
    (3, "IOCL", "PP", "1030RG", "Vadodara to Ahmedabad", "Domestic", "Raffia", "INR",
     ["97.20", "97.80", "98.10", "98.60", "98.40", "99.00"]),
    (4, "HMEL", "PP", "HP030R", "Bathinda to Gandhidham", "Domestic", "Raffia", "INR",
     ["96.80", "97.30", "97.90", "98.20", "98.10", "98.70"]),
    (5, "Reliance", "PP", "H110MA", "Hazira to Ahmedabad", "Domestic", "Multifilament", "INR",
     ["101.20", "101.20", "102.40", "102.40", "103.10", "103.10"]),
    (6, "IOCL", "LDPE", "24FS040", "Panipat to Gandhidham", "Domestic", "Lamination", "INR",
     ["112.50", "113.20", "113.80", None, None, None]),
    (7, "Reliance", "LLDPE", "F18S010", "Jamnagar to Ahmedabad", "Domestic", "Liner", "INR",
     ["104.60", "105.10", "105.10", "105.90", "106.30", "106.80"]),
    (8, "OQ", "PP", "PP-R030", "Middle East", "Import", "Raffia", "USD",
     ["1.085", "1.092", "1.104", "1.118", "1.126", "1.135"]),
    (9, "Borouge", "LLDPE", "FB2230", "Middle East", "Import", "Liner", "USD",
     ["1.142", "1.150", "1.155", "1.161", "1.170", "1.176"]),
    (10, "Reliance", "PP", "H999XX", "Jamnagar to Ahmedabad", "Domestic", "Raffia", "INR",
     [None, None, None, None, None, "99.90"]),
]

PRODUCERS = [
    ("RELIANCE", "Reliance Industries"),
    ("IOCL", "Indian Oil Corporation"),
    ("HMEL", "HPCL-Mittal Energy"),
    ("OQ", "OQ Marketing"),
    ("BOROUGE", "Borouge"),
]
GRADES = [
    ("PP-RAFFIA", "PP Raffia", "PP", "Raffia", "polypropylene"),
    ("PP-MULTIFIL", "PP Multifilament", "PP", "Multifilament", "polypropylene"),
    ("LDPE-LAM", "LDPE Lamination", "LDPE", "Lamination", "polyethylene"),
    ("LLDPE-LINER", "LLDPE Liner", "LLDPE", "Liner", "polyethylene"),
]
MARKETS = [
    ("AHMEDABAD", "Ahmedabad", "domestic", "Gujarat", "IN", ["Ahmedabad", "Amdavad"]),
    ("GANDHIDHAM", "Gandhidham", "domestic", "Gujarat", "IN", ["Gandhidham"]),
    ("MIDDLE-EAST", "Middle East (import origin)", "import_origin", None, None, ["Middle East"]),
]
# (producer code, raw ERP grade text, producer grade code, SourceOne grade code)
GRADE_MAPPINGS = [
    ("RELIANCE", "H030SG", "RIL-RAF-030", "PP-RAFFIA"),
    ("RELIANCE", "H110MA", "RIL-MFL-110", "PP-MULTIFIL"),
    ("RELIANCE", "F18S010", "RIL-LLD-18", "LLDPE-LINER"),
    ("IOCL", "1030RG", "IOC-RAF-1030", "PP-RAFFIA"),
    ("IOCL", "24FS040", "IOC-LDL-24", "LDPE-LAM"),
    ("HMEL", "HP030R", "HMEL-RAF-30", "PP-RAFFIA"),
    ("OQ", "PP-R030", "OQ-RAF-30", "PP-RAFFIA"),
    ("BOROUGE", "FB2230", "BRG-LLD-2230", "LLDPE-LINER"),
]
# (code, name, grade, market, price basis, currency, display order)
SERIES = [
    ("PP-RAFFIA-AHMEDABAD-INR", "PP Raffia, Ahmedabad", "PP-RAFFIA", "AHMEDABAD", "DELIVERED", "INR", 10),
    ("PP-RAFFIA-GANDHIDHAM-INR", "PP Raffia, Gandhidham", "PP-RAFFIA", "GANDHIDHAM", "DELIVERED", "INR", 20),
    ("PP-MULTIFIL-AHMEDABAD-INR", "PP Multifilament, Ahmedabad", "PP-MULTIFIL", "AHMEDABAD", "DELIVERED", "INR", 30),
    ("LDPE-LAM-GANDHIDHAM-INR", "LDPE Lamination, Gandhidham", "LDPE-LAM", "GANDHIDHAM", "DELIVERED", "INR", 40),
    ("LLDPE-LINER-AHMEDABAD-INR", "LLDPE Liner, Ahmedabad", "LLDPE-LINER", "AHMEDABAD", "DELIVERED", "INR", 50),
    ("PP-RAFFIA-MIDDLE-EAST-USD", "PP Raffia, Middle East import", "PP-RAFFIA", "MIDDLE-EAST", "IMPORT_ORIGIN", "USD", 60),
]
DEMO_PRODUCT_NOTE = "Demo catalogue item."
# (code, name, category, subcategory, description, mapped series codes; first is the default context)
PRODUCTS = [
    ("PP-RAFFIA-A", "PP Raffia Grade A", "Polymers", "Polypropylene",
     "Raffia-grade PP homopolymer for woven sacks, FIBC and tapes.",
     ["PP-RAFFIA-AHMEDABAD-INR", "PP-RAFFIA-GANDHIDHAM-INR"]),
    ("PP-RAFFIA-B", "PP Raffia Grade B", "Polymers", "Polypropylene",
     "Secondary raffia grade. No SourceOne benchmark series is mapped yet.",
     []),
    ("PP-MULTIFIL-A", "PP Multifilament Grade A", "Polymers", "Polypropylene",
     "Multifilament-grade PP for yarns, ropes and nonwoven applications.",
     ["PP-MULTIFIL-AHMEDABAD-INR"]),
    ("LDPE-LAM-A", "LDPE Lamination Grade A", "Polymers", "Polyethylene",
     "Extrusion-coating LDPE for lamination of woven fabric and paper.",
     ["LDPE-LAM-GANDHIDHAM-INR"]),
    ("LLDPE-LINER-A", "LLDPE Liner Grade A", "Polymers", "Polyethylene",
     "Film-grade LLDPE for bag liners and heavy-duty films.",
     ["LLDPE-LINER-AHMEDABAD-INR"]),
    ("PP-RAFFIA-IMP-A", "PP Raffia Import Grade A", "Polymers", "Polypropylene",
     "Imported raffia-grade PP, quoted at the Middle East origin region.",
     ["PP-RAFFIA-MIDDLE-EAST-USD"]),
]
# SourceOne catalogue specifications for the demo products. Not read from ERP.
PRODUCT_SPECS = {
    "PP-RAFFIA-A": {"grade": "PP Raffia", "application": "Raffia", "quality": "Prime", "mfi": "3.0 g/10 min", "density": "0.900 g/cm3"},
    "PP-RAFFIA-B": {"grade": "PP Raffia", "application": "Raffia", "quality": "Off-grade"},
    "PP-MULTIFIL-A": {"grade": "PP Multifilament", "application": "Multifilament", "quality": "Prime", "mfi": "12 g/10 min", "density": "0.905 g/cm3"},
    "LDPE-LAM-A": {"grade": "LDPE Lamination", "application": "Lamination", "quality": "Prime", "mfi": "4 g/10 min", "density": "0.923 g/cm3"},
    "LLDPE-LINER-A": {"grade": "LLDPE Liner", "application": "Liner", "quality": "Prime", "mfi": "1.0 g/10 min", "density": "0.918 g/cm3"},
    "PP-RAFFIA-IMP-A": {"grade": "PP Raffia", "producer": "Borouge", "application": "Raffia", "quality": "Prime", "mfi": "3.0 g/10 min", "density": "0.900 g/cm3"},
}
# Development password for the seeded sign-in accounts. Not a production secret.
DEMO_PASSWORD = "SourceOne-demo"
# email, seed key, name, organisation, role, system account
USERS = [
    ("system@sourceone.local", "system", "SourceOne System", "SOURCEONE", None, True),
    ("admin@demo.sourceone", "asha", "Asha Mehta", "SOURCEONE", "platform_admin", False),
    ("pricing@demo.sourceone", "ravi", "Ravi Iyer", "SOURCEONE", "pricing_admin", False),
    ("meera@sourceone.demo", "meera", "Meera Shah", "SOURCEONE", "pricing_admin", False),
    ("buyer@demo.sourceone", "buyer", "Arjun Patel", "ARDENT", "buyer", False),
    ("supplier@demo.sourceone", "supplier", "Zoya Khan", "ZENITH", "supplier", False),
    ("neil@harbour.demo", "neil", "Neil Desai", "HARBOUR", "supplier", False),
]
# Existing demo rows keep their user id; only the sign-in email changes.
LOGIN_EMAILS = {
    "asha@sourceone.demo": "admin@demo.sourceone",
    "ravi@sourceone.demo": "pricing@demo.sourceone",
    "buyer@ardent.demo": "buyer@demo.sourceone",
    "supplier@zenith.demo": "supplier@demo.sourceone",
}
ORGANISATIONS = [
    ("SOURCEONE", "SourceOne", "platform"),
    ("ARDENT", "Ardent Packaging (demo buyer)", "buyer"),
    ("ZENITH", "Zenith Polymers (demo supplier)", "supplier"),
    ("HARBOUR", "Harbour Polytrade (demo supplier)", "supplier"),
]
# Asking prices are the supplier's own offers. They are not ERP prices and not SourceOne benchmarks.
LISTINGS = [
    ("supplier", "PP-RAFFIA-A", "500", "100.2500", "INR", "in_stock", True),
    ("neil", "PP-RAFFIA-A", "1000", "101.4000", "INR", "limited", True),
    ("supplier", "PP-MULTIFIL-A", "500", "104.7500", "INR", "in_stock", True),
    ("supplier", "LDPE-LAM-A", "250", "114.0000", "INR", "on_request", True),
    ("supplier", "PP-RAFFIA-B", "500", "98.0000", "INR", "in_stock", False),
]
# SourceOne-owned lanes. These are not ERP freight rates.
DISPATCH = {
    "ZENITH": ("361140", "Jamnagar"),
    "HARBOUR": ("394510", "Hazira"),
    "KUTCH": ("370201", "Gandhidham"),
    "SAURASHTRA": ("360001", "Rajkot"),
    "COASTLINE": ("395003", "Surat"),
}
# key, email, name, organisation code, organisation name. Dispatch pins are in DISPATCH.
MARKET_SUPPLIERS = [
    ("mira", "mira@demo.sourceone", "Mira Shah", "KUTCH", "Kutch Resins (demo supplier)"),
    ("kabir", "kabir@demo.sourceone", "Kabir Joshi", "SAURASHTRA", "Saurashtra Poly (demo supplier)"),
    ("leela", "leela@demo.sourceone", "Leela Nair", "COASTLINE", "Coastline Polymers (demo supplier)"),
]
# supplier, product, MOQ, price 30 days ago, price today, currency, availability.
# Today's price is the live asking price. The month of averages is built from these paths.
MARKET_OFFERS = [
    ("supplier", "PP-RAFFIA-A", "500", "98.4000", "100.2500", "INR", "in_stock"),
    ("neil", "PP-RAFFIA-A", "1000", "99.1000", "101.4000", "INR", "limited"),
    ("mira", "PP-RAFFIA-A", "750", "97.8000", "99.9000", "INR", "in_stock"),
    ("kabir", "PP-RAFFIA-A", "500", "100.2000", "102.2000", "INR", "in_stock"),
    ("supplier", "PP-MULTIFIL-A", "500", "102.5000", "104.7500", "INR", "in_stock"),
    ("neil", "PP-MULTIFIL-A", "800", "103.8000", "106.1000", "INR", "in_stock"),
    ("leela", "PP-MULTIFIL-A", "500", "101.9000", "103.4000", "INR", "limited"),
    ("supplier", "LDPE-LAM-A", "250", "111.5000", "114.0000", "INR", "on_request"),
    ("mira", "LDPE-LAM-A", "500", "110.2000", "112.5000", "INR", "in_stock"),
    ("leela", "LDPE-LAM-A", "400", "113.0000", "115.7500", "INR", "in_stock"),
    ("neil", "LLDPE-LINER-A", "500", "94.8000", "96.5000", "INR", "in_stock"),
    ("kabir", "LLDPE-LINER-A", "600", "95.4000", "97.2500", "INR", "in_stock"),
    ("leela", "LLDPE-LINER-A", "500", "94.1000", "95.8000", "INR", "limited"),
]
MARKET_HISTORY_DAYS = 31
# origin pin, origin label, destination pin, destination label, ₹ or $ per kg, currency, minimum, active, from
FREIGHT_RULES = [
    ("361140", "Jamnagar", "390020", "Vadodara", "1.2500", "INR", "1500", True, date(2026, 1, 1)),
    ("361140", "Jamnagar", "380015", "Ahmedabad", "1.1000", "INR", "1200", True, date(2026, 1, 1)),
    ("394510", "Hazira", "390020", "Vadodara", "1.8000", "INR", "2000", True, date(2026, 1, 1)),
    ("370201", "Gandhidham", "390020", "Vadodara", "1.6000", "INR", "1800", True, date(2026, 1, 1)),
    ("360001", "Rajkot", "390020", "Vadodara", "1.4500", "INR", "1600", True, date(2026, 1, 1)),
    ("395003", "Surat", "390020", "Vadodara", "2.1000", "INR", "2200", True, date(2026, 1, 1)),
    ("361140", "Jamnagar", "370201", "Gandhidham", "0.9000", "INR", None, False, date(2026, 1, 1)),
    ("361140", "Jamnagar", "390020", "Vadodara", "0.0200", "USD", None, True, date(2026, 1, 1)),
]


def erp_rows(batch_index: int, as_of: date) -> list[dict]:
    rows = []
    for sr_no, company, quality, grade, location, sector, application, currency, values in ERP_LINES:
        value = values[batch_index]
        if value is None:
            continue
        rows.append({
            "SrNo": sr_no, "SysDate": as_of.isoformat(), "Company": company, "Quality": quality,
            "Grade": grade, "Location": location, "Sector": sector, "Appilcation": application,
            "Currency": currency, "UnitPrice": value, "Basic": value, "Total": value, "GrandTotal": value,
            "CurrencyCon": "1", "CashDis": None, "LocDis": "0", "Trade": "0", "Special": None, "QD": "0",
            "AQD": None, "MOU": None, "Frieght": "0", "GSTPER": "0", "GSTAMT": "0", "QtySlab": "",
        })
    return rows


def _reset(session: Session) -> None:
    session.execute(text(f"TRUNCATE {', '.join(DEMO_TABLES)} RESTART IDENTITY CASCADE"))


def _reference_data(session: Session) -> dict:
    orgs = {code: Organisation(code=code, name=name, org_type=kind) for code, name, kind in ORGANISATIONS}
    session.add_all(orgs.values())
    session.flush()

    roles = {r.code: r for r in session.scalars(select(Role))}
    users = {}
    for email, key, name, org, role, is_system in USERS:
        user = User(
            email=email, full_name=name, organisation_id=orgs[org].id, is_system=is_system,
            password_hash=None if is_system else hash_password(DEMO_PASSWORD),
        )
        session.add(user)
        session.flush()
        if role:
            session.add(UserRole(user_id=user.id, role_id=roles[role].id))
        users[key] = user

    producers = {code: Producer(code=code, name=name) for code, name in PRODUCERS}
    grades = {
        code: Grade(code=code, name=name, polymer=polymer, application=app, category=category)
        for code, name, polymer, app, category in GRADES
    }
    markets = {
        code: Market(code=code, name=name, market_type=kind, state=state, country_code=country)
        for code, name, kind, state, country, _ in MARKETS
    }
    session.add_all([*producers.values(), *grades.values(), *markets.values()])
    session.flush()

    for code, _, _, _, _, aliases in MARKETS:
        for alias in aliases:
            session.add(MarketAlias(alias=alias, alias_normalized=normalize_text(alias), market_id=markets[code].id))
    for producer, raw_grade, producer_code, grade in GRADE_MAPPINGS:
        session.add(ProducerGradeAlias(
            producer_id=producers[producer].id, alias=raw_grade,
            alias_normalized=normalize_text(raw_grade), producer_grade_code=producer_code,
        ))
        session.add(GradeEquivalence(
            producer_id=producers[producer].id, producer_grade_code=producer_code,
            grade_id=grades[grade].id, notes="Demo equivalence",
        ))

    session.add_all([
        RateSource(
            code=ERP_SOURCE_CODE, name="ERP price list (demo fixtures)", source_type=SourceType.ERP_FEED,
            is_active=True, priority=10, staleness_days=14, publishing_policy=PublishingPolicy.REVIEW_REQUIRED,
            default_unit="KG", normalization_profile=ERP_PROFILE, profile_version=1,
            owner_organisation_id=orgs["SOURCEONE"].id,
            description="Demo source shaped like ERP DomesticPrice1. Rows are fixtures; no ERP connection exists.",
        ),
        RateSource(
            code=get_settings().erp_rate_source_code, name="ERP price list (read-only sync)",
            source_type=SourceType.ERP_FEED, is_active=True, priority=10, staleness_days=14,
            publishing_policy=PublishingPolicy.REVIEW_REQUIRED, default_unit="KG",
            normalization_profile={
                **ERP_PROFILE, "benchmark_field": "GrandTotal", "value_field": "GrandTotal", "must_equal_fields": [],
            },
            profile_version=1, owner_organisation_id=orgs["SOURCEONE"].id,
            description="Rows read from ERP DomesticPrice1 by the admin ERP sync. Empty until an ERP sync runs.",
        ),
        RateSource(
            code=service.MANUAL_SOURCE_CODE, name="SourceOne manual entry", source_type=SourceType.MANUAL,
            is_active=True, priority=20, staleness_days=7, publishing_policy=PublishingPolicy.REVIEW_REQUIRED,
            default_unit="KG", owner_organisation_id=orgs["SOURCEONE"].id,
            description="Benchmarks entered by pricing admins with a reason and evidence reference.",
        ),
    ])
    series = {}
    for code, name, grade, market, basis, currency, order in SERIES:
        series[code] = RateSeries(
            code=code, display_name=name, grade_id=grades[grade].id, market_id=markets[market].id,
            price_basis=basis, tax_basis="GST_EXCLUDED", currency=currency, unit="KG",
            visibility=SeriesVisibility.SIGNED_IN_PLATFORM, is_active=True, display_order=order,
        )
    session.add_all(series.values())
    session.flush()

    for code, name, category, subcategory, description, series_codes in PRODUCTS:
        product = products.create_product(
            session, product_code=code, name=name, category=category, subcategory=subcategory,
            description=f"{DEMO_PRODUCT_NOTE} {description}", uom="KG",
            specifications=PRODUCT_SPECS.get(code),
        )
        for order, series_code in enumerate(series_codes):
            products.map_rate_series(session, product, series[series_code], display_order=(order + 1) * 10)
    catalogue = {code: session.scalar(select(Product).where(Product.product_code == code)) for code, *_ in PRODUCTS}
    for user_key, product_code, minimum, price, currency, availability, active in LISTINGS:
        session.add(SupplierListing(
            supplier_user_id=users[user_key].id, product_id=catalogue[product_code].id, uom="KG",
            minimum_quantity=Decimal(minimum), asking_price=Decimal(price), currency=currency,
            availability=availability, is_active=active,
        ))
    session.flush()
    seen: set[tuple] = set()
    for _user_key, product_code, _minimum, _price, currency, _availability, active in LISTINGS:
        if not active:
            continue
        key = (catalogue[product_code].id, currency)
        if key in seen:
            continue
        seen.add(key)
        market_average.record(session, catalogue[product_code].id, currency)
    ensure_demo_freight(session)
    return {"users": users, "series": series}


def _rate(result: ingestion.IngestResult, sr_no: int) -> SourceRate:
    return next(r for r in result.source_rates if r.source_identity_key == str(sr_no))


def _suggestion(result: ingestion.IngestResult, series: RateSeries):
    return next((b for b in result.suggestions if b.series_id == series.id), None)


def seed(session: Session) -> dict:
    ref = _reference_data(session)
    users, series = ref["users"], ref["series"]
    asha, ravi, meera = (actor_for(session, users[n]) for n in ("asha", "ravi", "meera"))
    system_id = users["system"].id

    today = business_today(utcnow())
    batch_dates = [today - timedelta(days=offset) for offset in BATCH_OFFSETS]
    last = len(batch_dates) - 1

    for index, as_of in enumerate(batch_dates):
        at = start_of_business_day(as_of) + timedelta(hours=5)  # 10:30 IST
        result = ingestion.ingest_price_list(
            session, source_code=ERP_SOURCE_CODE, source_as_of_date=as_of, rows=erp_rows(index, as_of),
            triggered_by_id=system_id, notes=DEMO_NOTE, now=at,
        )
        publish_at = at + timedelta(hours=2)

        # Ahmedabad raffia has two producers, so an admin chooses; unchanged re-entries are skipped.
        ril = _rate(result, 1)
        if index == last:
            iocl_draft = service.select_source_rate(session, ravi, source_rate_id=_rate(result, 3).id, now=at)
        if not ril.is_unchanged:
            draft = service.select_source_rate(session, asha, source_rate_id=ril.id, now=at)
            service.submit_benchmark(session, asha, draft.id, now=at)
            service.publish_benchmark(session, asha, draft.id, now=publish_at)

        # Single-producer series receive system suggestions; the latest Gandhidham one stays pending.
        for code in ("PP-RAFFIA-GANDHIDHAM-INR", "PP-MULTIFIL-AHMEDABAD-INR", "LDPE-LAM-GANDHIDHAM-INR",
                     "LLDPE-LINER-AHMEDABAD-INR", "PP-RAFFIA-MIDDLE-EAST-USD"):
            suggestion = _suggestion(result, series[code])
            if suggestion is None:
                continue
            if code == "PP-RAFFIA-GANDHIDHAM-INR" and index == last:
                continue
            service.publish_benchmark(session, ravi, suggestion.id, now=publish_at)

        if index == last:
            liner_latest = _suggestion(result, series["LLDPE-LINER-AHMEDABAD-INR"])
            service.withdraw_benchmark(
                session, ravi, liner_latest.id, now=publish_at + timedelta(hours=3),
                reason="Producer issued a revised circular; value under review",
            )

    manual_day = today - timedelta(days=1)
    manual_at = start_of_business_day(manual_day) + timedelta(hours=6)
    manual = service.create_manual_benchmark(
        session, meera, series_id=series["PP-MULTIFIL-AHMEDABAD-INR"].id, value=Decimal("103.60"),
        currency="INR", unit="KG", source_as_of_date=manual_day,
        reason="Producer circular received ahead of the ERP update",
        evidence_ref="DEMO-CIRCULAR-RIL-MFL", now=manual_at,
    )
    service.submit_benchmark(session, meera, manual.id, now=manual_at)
    service.publish_benchmark(session, ravi, manual.id, now=manual_at + timedelta(hours=1))

    rejected_day = today - timedelta(days=2)
    rejected_at = start_of_business_day(rejected_day) + timedelta(hours=6)
    ldpe = service.create_manual_benchmark(
        session, meera, series_id=series["LDPE-LAM-GANDHIDHAM-INR"].id, value=Decimal("118.00"),
        currency="INR", unit="KG", source_as_of_date=rejected_day,
        reason="Market feedback from a distributor call", now=rejected_at,
    )
    service.submit_benchmark(session, meera, ldpe.id, now=rejected_at)
    service.reject_benchmark(
        session, ravi, ldpe.id, reason="No producer evidence; await the circular", now=rejected_at + timedelta(hours=1)
    )
    session.flush()
    _negotiations(session, users)
    ensure_market_month(session)
    ensure_demo_freight(session)
    return {"batches": len(batch_dates), "pending_iocl_draft": str(iocl_draft.id)}


# (product, quantity kg, [(party, offered price, message)], outcome); offers alternate buyer/supplier.
NEGOTIATIONS = [
    ("PP-RAFFIA-A", "12000", [
        ("buyer", "98.20", "Monthly requirement for woven sack line, delivery Ahmedabad."),
    ], None),
    ("PP-MULTIFIL-A", "8000", [
        ("buyer", "101.50", "Looking for a quarter-long rate for yarn production."),
        ("supplier", "103.20", "Can hold this rate for 8 MT with dispatch in 3 days."),
        ("buyer", "102.40", "We can commit the full quantity at this level."),
        ("supplier", "102.90", "Best we can do for this lot."),
    ], None),
    ("PP-RAFFIA-IMP-A", "25000", [
        ("buyer", "1.110", "Import lot for next month, CIF Mundra."),
        ("supplier", "1.128", "Rate valid for this week's allocation."),
    ], "accept"),
    ("LDPE-LAM-A", "5000", [
        ("buyer", "108.00", "Spot requirement for lamination."),
    ], "reject"),
]

# Accepted negotiations that become demo orders: (product, quantity kg, offers, final order status).
ORDERED_NEGOTIATIONS = [
    ("PP-RAFFIA-A", "10000", [
        ("buyer", "98.60", "Replenishment lot for the sack line."),
        ("supplier", "99.20", "Can dispatch from Ahmedabad this week."),
    ], OrderStatus.CONFIRMED),
    ("PP-MULTIFIL-A", "6000", [
        ("buyer", "102.80", "Yarn line top-up."),
    ], OrderStatus.PROCESSING),
    ("PP-RAFFIA-A", "15000", [
        ("buyer", "97.80", "Quarterly volume, staggered delivery."),
        ("supplier", "98.30", "Holding 15 MT for you."),
        ("buyer", "98.00", "Final from our side."),
    ], OrderStatus.DELIVERED),
    ("LDPE-LAM-A", "4000", [
        ("buyer", "112.00", "Lamination trial lot."),
        ("supplier", "113.00", "Trial lot price."),
    ], OrderStatus.CANCELLED),
]
STEP = timedelta(minutes=10)
FULFILMENT_NOTES = {
    OrderStatus.CONFIRMED: "Order accepted; slot booked on the Ahmedabad line.",
    OrderStatus.PROCESSING: "Material allocated from current production.",
    OrderStatus.READY: "Packed and palletised; quality certificate attached.",
    OrderStatus.DISPATCHED: None,
    OrderStatus.IN_TRANSIT: "Vehicle left the plant.",
    OrderStatus.DELIVERED: "Received at buyer plant; delivery challan signed.",
}


def _negotiate(session, parties, users, product_code, quantity, offers, at):
    _, first_price, first_message = offers[0]
    negotiation = negotiation_service.create_negotiation(
        session, parties["buyer"], product_code=product_code, quantity=Decimal(quantity),
        offered_price=Decimal(first_price), message=first_message, supplier_user_id=users["supplier"].id, now=at,
    )
    for party, price, message in offers[1:]:
        at += STEP
        negotiation_service.make_offer(session, parties[party], negotiation.id, price=Decimal(price),
                                       message=message, now=at)
    return negotiation, at + STEP


def _negotiations(session: Session, users: dict) -> None:
    parties = {"buyer": actor_for(session, users["buyer"]), "supplier": actor_for(session, users["supplier"])}
    buyer, supplier = parties["buyer"], parties["supplier"]
    at = utcnow() - timedelta(hours=8)
    for product_code, quantity, offers, outcome in NEGOTIATIONS:
        negotiation, at = _negotiate(session, parties, users, product_code, quantity, offers, at)
        if outcome == "accept":
            negotiation_service.accept_offer(session, buyer, negotiation.id, now=at)
        elif outcome == "reject":
            negotiation_service.reject_offer(session, supplier, negotiation.id, now=at,
                                             reason="Cannot supply below the current lamination price.")
        at += STEP

    for product_code, quantity, offers, final_status in ORDERED_NEGOTIATIONS:
        negotiation, at = _negotiate(session, parties, users, product_code, quantity, offers, at)
        accepting = parties[negotiation_service.awaiting_party(negotiation)]
        negotiation_service.accept_offer(session, accepting, negotiation.id, now=at)
        at += STEP
        order = order_service.create_from_negotiation(session, buyer, negotiation.id, destination_pin="390020", now=at)
        if final_status == OrderStatus.CANCELLED:
            at += STEP
            order_service.cancel_order(session, buyer, order.id, now=at, reason="Trial postponed by production.")
            continue
        status = OrderStatus.PLACED
        while status != final_status:
            status = NEXT_STATUS[status]
            at += STEP
            order_service.advance_order(session, supplier, order.id, to_status=status,
                                        note=FULFILMENT_NOTES[status], now=at)
        at += STEP


def ensure_demo_freight(session: Session) -> int:
    """Add SourceOne freight lanes for the demo suppliers. Does not read ERP freight."""
    for code, (pin, label) in DISPATCH.items():
        org = session.scalar(select(Organisation).where(Organisation.code == code))
        if org is None:
            continue
        org.dispatch_pin = pin
        org.dispatch_label = label
    added = 0
    for origin_pin, origin_label, destination_pin, destination_label, rate, currency, minimum, active, effective_from in FREIGHT_RULES:
        exists = session.scalar(select(FreightRule.id).where(
            FreightRule.origin_pin == origin_pin,
            FreightRule.destination_pin == destination_pin,
            FreightRule.currency == currency,
            FreightRule.is_active.is_(active),
        ))
        if exists is not None:
            continue
        session.add(FreightRule(
            origin_pin=origin_pin, origin_label=origin_label,
            destination_pin=destination_pin, destination_label=destination_label,
            rate_per_kg=Decimal(rate), rate_unit="KG", currency=currency,
            minimum_freight=Decimal(minimum) if minimum else None,
            is_active=active, effective_from=effective_from, effective_to=None,
        ))
        added += 1
    if session.scalar(select(FreightDistanceRate).where(FreightDistanceRate.currency == "INR")) is None:
        session.add(FreightDistanceRate(currency="INR", rate_per_km=DEFAULT_RATE_PER_KM, minimum_freight=None, is_active=True))
        added += 1
    return added


def ensure_demo_specifications(session: Session) -> int:
    """Fill demo catalogue specs only where a product has none yet."""
    updated = 0
    for code, specs in PRODUCT_SPECS.items():
        product = session.scalar(select(Product).where(Product.product_code == code))
        if product is None or product.specifications:
            continue
        product.specifications = specs
        updated += 1
    return updated


def ensure_demo_accounts(session: Session) -> int:
    """Point the four sign-in accounts at the existing demo users and set the development password."""
    password = hash_password(DEMO_PASSWORD)
    updated = 0
    for old, new in LOGIN_EMAILS.items():
        current = session.scalar(select(User).where(User.email == new))
        legacy = session.scalar(select(User).where(User.email == old))
        if current is None and legacy is not None:
            legacy.email = new
            current = legacy
        if current is None or current.is_system:
            continue
        current.password_hash = password
        updated += 1
    return updated


def ensure_demo_listings(session: Session) -> int:
    """Add the demo supplier catalogue when reference data already exists."""
    org = session.scalar(select(Organisation).where(Organisation.code == "HARBOUR"))
    if org is None:
        org = Organisation(code="HARBOUR", name="Harbour Polytrade (demo supplier)", org_type="supplier")
        session.add(org)
        session.flush()
    user = session.scalar(select(User).where(User.email == "neil@harbour.demo"))
    if user is None:
        user = User(email="neil@harbour.demo", full_name="Neil Desai", organisation_id=org.id, is_system=False)
        session.add(user)
        session.flush()
        role = session.scalar(select(Role).where(Role.code == "supplier"))
        session.add(UserRole(user_id=user.id, role_id=role.id))
    users = {
        "supplier": session.scalar(select(User).where(User.email == "supplier@demo.sourceone")),
        "neil": user,
    }
    if users["supplier"] is None:
        return 0
    added = 0
    for user_key, product_code, minimum, price, currency, availability, active in LISTINGS:
        product = session.scalar(select(Product).where(Product.product_code == product_code))
        if product is None:
            continue
        exists = session.scalar(select(SupplierListing.id).where(
            SupplierListing.supplier_user_id == users[user_key].id,
            SupplierListing.product_id == product.id,
        ))
        if exists is not None:
            continue
        session.add(SupplierListing(
            supplier_user_id=users[user_key].id, product_id=product.id, uom="KG",
            minimum_quantity=Decimal(minimum), asking_price=Decimal(price), currency=currency,
            availability=availability, is_active=active,
        ))
        added += 1
    return added


def _price_path(start: str, end: str, days: int, phase: float) -> list[Decimal]:
    """Daily asking price from a month ago up to today's listing price, with a small wave."""
    opened, closed = Decimal(start), Decimal(end)
    path = []
    for index in range(days):
        if index == days - 1:
            path.append(closed)
            continue
        progress = Decimal(index) / Decimal(days - 1)
        wave = Decimal(str(round(math.sin(index / 2.7 + phase) * 0.45, 4)))
        path.append((opened + (closed - opened) * progress + wave).quantize(Decimal("0.0001")))
    return path


def ensure_market_month(session: Session) -> int:
    """Give several materials a month of supplier asking prices so the live graph can move.

    Safe to run again: once a material already has the month of points, it is left alone.
    """
    role = session.scalar(select(Role).where(Role.code == "supplier"))
    if role is None:
        return 0
    password = hash_password(DEMO_PASSWORD)
    users = {
        "supplier": session.scalar(select(User).where(User.email == "supplier@demo.sourceone")),
        "neil": session.scalar(select(User).where(User.email == "neil@harbour.demo")),
    }
    if users["supplier"] is None:
        return 0
    for key, email, name, org_code, org_name in MARKET_SUPPLIERS:
        org = session.scalar(select(Organisation).where(Organisation.code == org_code))
        if org is None:
            org = Organisation(code=org_code, name=org_name, org_type="supplier")
            session.add(org)
            session.flush()
        pin, label = DISPATCH[org_code]
        org.dispatch_pin = pin
        org.dispatch_label = label
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name, organisation_id=org.id, is_system=False, password_hash=password)
            session.add(user)
            session.flush()
            session.add(UserRole(user_id=user.id, role_id=role.id))
        else:
            user.password_hash = password
            user.is_active = True
        users[key] = user
    if users["neil"] is not None:
        users["neil"].password_hash = password
    return _write_market_month(session, users)


def _write_market_month(session: Session, users: dict) -> int:
    sample = session.scalar(select(Product).where(Product.product_code == "PP-RAFFIA-A"))
    if sample is None:
        return 0
    existing = session.scalar(
        select(func.count()).select_from(AskingPriceAverage).where(AskingPriceAverage.product_id == sample.id)
    )
    if existing and existing >= MARKET_HISTORY_DAYS - 1:
        return 0

    phases = {"supplier": 0.0, "neil": 1.1, "mira": 2.2, "kabir": 3.0, "leela": 0.6}
    by_product: dict[str, list] = {}
    for offer in MARKET_OFFERS:
        by_product.setdefault(offer[1], []).append(offer)

    written = 0
    today = business_today(utcnow())
    for product_code, offers in by_product.items():
        product = session.scalar(select(Product).where(Product.product_code == product_code))
        if product is None:
            continue
        paths = []
        for user_key, _code, minimum, start, end, currency, availability in offers:
            user = users.get(user_key)
            if user is None:
                continue
            listing = session.scalar(select(SupplierListing).where(
                SupplierListing.supplier_user_id == user.id, SupplierListing.product_id == product.id,
            ))
            if listing is None:
                listing = SupplierListing(
                    supplier_user_id=user.id, product_id=product.id, uom="KG",
                    minimum_quantity=Decimal(minimum), asking_price=Decimal(end), currency=currency,
                    availability=availability, is_active=True,
                )
                session.add(listing)
            else:
                listing.asking_price = Decimal(end)
                listing.is_active = True
                listing.availability = availability
                listing.currency = currency
            paths.append(_price_path(start, end, MARKET_HISTORY_DAYS, phases[user_key]))
        if not paths:
            continue
        session.flush()
        session.execute(delete(AskingPriceAverage).where(
            AskingPriceAverage.product_id == product.id, AskingPriceAverage.currency == offers[0][5],
        ))
        for day in range(MARKET_HISTORY_DAYS):
            prices = [path[day] for path in paths]
            average = (sum(prices, Decimal(0)) / len(prices)).quantize(Decimal("0.0001"))
            session.add(AskingPriceAverage(
                product_id=product.id,
                currency=offers[0][5],
                average_price=average,
                supplier_count=len(prices),
                recorded_at=start_of_business_day(today - timedelta(days=MARKET_HISTORY_DAYS - 1 - day)) + timedelta(hours=4),
            ))
            written += 1
    session.flush()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed SourceOne pricing demo data")
    parser.add_argument("--reset", action="store_true", help="truncate demo tables first (keeps roles/permissions)")
    args = parser.parse_args()
    with SessionLocal() as session:
        if args.reset:
            _reset(session)
        elif session.scalar(select(Organisation.id).limit(1)) is not None:
            accounts = ensure_demo_accounts(session)
            added = ensure_demo_listings(session)
            points = ensure_market_month(session)
            freight = ensure_demo_freight(session)
            specs = ensure_demo_specifications(session)
            session.commit()
            total = session.scalar(text("SELECT count(*) FROM supplier_listings"))
            lanes = session.scalar(text("SELECT count(*) FROM freight_rules"))
            print(f"Demo data already present. Sign-in accounts updated: {accounts}. Supplier listings added: {added}. Market-rate points written: {points}. supplier_listings: {total}. Freight rules added: {freight}. freight_rules: {lanes}. Specifications filled: {specs}")
            return 0
        summary = seed(session)
        session.commit()
        counts = {
            table: session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("users", "producers", "grades", "markets", "rate_series", "import_batches",
                          "source_rates", "benchmark_rates", "pricing_audit_events", "products",
                          "product_rate_series", "negotiations", "negotiation_versions", "orders",
                          "order_status_events", "supplier_listings", "freight_rules")
        }
    print(f"Seeded {summary['batches']} demo ERP batches (fixtures, no ERP connection).")
    for table, count in counts.items():
        print(f"  {table}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
