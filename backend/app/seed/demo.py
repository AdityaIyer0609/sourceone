"""Demo data for the SourceOne V1 pricing demo.

    python -m app.seed.demo [--reset]

All ERP rows below are synthetic fixtures shaped like the ERP price list (DomesticPrice1). They are
not read from, and do not imply, a live ERP connection. Every benchmark flow goes through the
service layer, so the seeded data obeys the same lifecycle and four-eyes rules as the API.
"""

import argparse
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.catalogue import products
from app.catalogue.resolver import normalize_text
from app.core.clock import business_today, start_of_business_day, utcnow
from app.db.session import SessionLocal
from app.identity.service import actor_for
from app.models.catalogue import Grade, GradeEquivalence, Market, MarketAlias, Producer, ProducerGradeAlias
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
    "order_status_events", "orders", "negotiation_versions", "negotiations", "product_rate_series", "products", "pricing_audit_events", "benchmark_rate_inputs", "benchmark_rates", "source_rates", "import_batches",
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
USERS = [
    ("system@sourceone.local", "SourceOne System", "SOURCEONE", None, True),
    ("asha@sourceone.demo", "Asha Mehta", "SOURCEONE", "platform_admin", False),
    ("ravi@sourceone.demo", "Ravi Iyer", "SOURCEONE", "pricing_admin", False),
    ("meera@sourceone.demo", "Meera Shah", "SOURCEONE", "pricing_admin", False),
    ("buyer@ardent.demo", "Arjun Patel", "ARDENT", "buyer", False),
    ("supplier@zenith.demo", "Zoya Khan", "ZENITH", "supplier", False),
]
ORGANISATIONS = [
    ("SOURCEONE", "SourceOne", "platform"),
    ("ARDENT", "Ardent Packaging (demo buyer)", "buyer"),
    ("ZENITH", "Zenith Polymers (demo supplier)", "supplier"),
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
    for email, name, org, role, is_system in USERS:
        user = User(email=email, full_name=name, organisation_id=orgs[org].id, is_system=is_system)
        session.add(user)
        session.flush()
        if role:
            session.add(UserRole(user_id=user.id, role_id=roles[role].id))
        users[email.split("@")[0]] = user

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
        )
        for order, series_code in enumerate(series_codes):
            products.map_rate_series(session, product, series[series_code], display_order=(order + 1) * 10)
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
        order = order_service.create_from_negotiation(session, buyer, negotiation.id, now=at)
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed SourceOne pricing demo data")
    parser.add_argument("--reset", action="store_true", help="truncate demo tables first (keeps roles/permissions)")
    args = parser.parse_args()
    with SessionLocal() as session:
        if args.reset:
            _reset(session)
        elif session.scalar(select(Organisation.id).limit(1)) is not None:
            print("Demo data already present; re-run with --reset to rebuild it.")
            return 1
        summary = seed(session)
        session.commit()
        counts = {
            table: session.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in ("users", "producers", "grades", "markets", "rate_series", "import_batches",
                          "source_rates", "benchmark_rates", "pricing_audit_events", "products",
                          "product_rate_series", "negotiations", "negotiation_versions", "orders",
                          "order_status_events")
        }
    print(f"Seeded {summary['batches']} demo ERP batches (fixtures, no ERP connection).")
    for table, count in counts.items():
        print(f"  {table}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
