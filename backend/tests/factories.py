import copy
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogue.resolver import normalize_text
from app.identity.service import Actor, actor_for
from app.models.catalogue import Grade, GradeEquivalence, Market, MarketAlias, Producer, ProducerGradeAlias
from app.models.identity import Organisation, Role, User, UserRole
from app.models.pricing import RateSeries, RateSource
from app.pricing import ingestion, service
from app.pricing.constants import PublishingPolicy, SeriesVisibility, SourceType
from app.seed.demo import ERP_PROFILE


@dataclass
class World:
    session: Session
    suffix: str
    users: dict[str, User] = field(default_factory=dict)
    actors: dict[str, Actor] = field(default_factory=dict)
    producers: dict[str, Producer] = field(default_factory=dict)
    series: dict[str, RateSeries] = field(default_factory=dict)
    erp_source: RateSource | None = None
    manual_source: RateSource | None = None
    market_text: str = ""
    import_market_text: str = ""

    def ingest(self, as_of: date, rows: list[dict], **kwargs) -> ingestion.IngestResult:
        return ingestion.ingest_price_list(
            self.session, source_code=self.erp_source.code, source_as_of_date=as_of, rows=rows,
            triggered_by_id=self.users["system"].id, notes="test fixture", **kwargs,
        )

    def row(self, sr_no: int, value: str, *, producer: str = "A", sector: str = "Domestic",
            grade: str = "RAF-1", currency: str = "INR", location: str | None = None, **overrides) -> dict:
        location = location or f"Plant to {self.market_text}"
        row = {
            "SrNo": sr_no, "Company": self.producers[producer].code, "Quality": "PP", "Grade": grade,
            "Location": location, "Sector": sector, "Appilcation": "Raffia", "Currency": currency,
            "UnitPrice": value, "Basic": value, "Total": value, "GrandTotal": value,
            "CashDis": None, "LocDis": "0", "Trade": "0", "Special": None, "QD": "0", "AQD": None,
            "MOU": None, "Frieght": "0", "GSTAMT": "0", "QtySlab": "",
        }
        row.update(overrides)
        return row

    def import_row(self, sr_no: int, value: str, **overrides) -> dict:
        return self.row(sr_no, value, sector="Import", currency="USD", location=self.import_market_text, **overrides)

    def manual(self, actor: str, series: str = "inr", value: str = "100.00", as_of: date | None = None, **kwargs):
        target = self.series[series]
        return service.create_manual_benchmark(
            self.session, self.actors[actor], series_id=target.id, value=value,
            currency=kwargs.pop("currency", target.currency), unit=kwargs.pop("unit", target.unit),
            source_as_of_date=as_of or date(2026, 9, 1), reason=kwargs.pop("reason", "Producer circular"),
            source_code=self.manual_source.code, **kwargs,
        )


def build_world(session: Session, *, import_eligible: bool = True) -> World:
    sfx = uuid.uuid4().hex[:8].upper()
    world = World(session=session, suffix=sfx)
    roles = {r.code: r for r in session.scalars(select(Role))}

    org = Organisation(code=f"ORG-{sfx}", name=f"Test org {sfx}", org_type="platform")
    session.add(org)
    session.flush()
    for key, role, is_system in (
        ("system", None, True), ("alice", "pricing_admin", False), ("bob", "pricing_admin", False),
        ("platform", "platform_admin", False), ("buyer", "buyer", False), ("supplier", "supplier", False),
    ):
        user = User(email=f"{key}-{sfx.lower()}@test.local", full_name=key.title(), organisation_id=org.id,
                    is_system=is_system)
        session.add(user)
        session.flush()
        if role:
            session.add(UserRole(user_id=user.id, role_id=roles[role].id))
        world.users[key] = user
    session.flush()
    world.actors = {k: actor_for(session, u) for k, u in world.users.items() if k != "system"}

    grade = Grade(code=f"G-{sfx}", name="Test raffia", polymer="PP", application="Raffia", category=f"cat-{sfx}")
    market = Market(code=f"M-{sfx}", name="Test city", market_type="domestic")
    import_market = Market(code=f"MI-{sfx}", name="Test origin", market_type="import_origin")
    world.producers = {
        "A": Producer(code=f"PA-{sfx}", name=f"Producer A {sfx}"),
        "B": Producer(code=f"PB-{sfx}", name=f"Producer B {sfx}"),
    }
    session.add_all([grade, market, import_market, *world.producers.values()])
    session.flush()

    world.market_text = f"City {sfx}"
    world.import_market_text = f"Origin {sfx}"
    session.add_all([
        MarketAlias(alias=world.market_text, alias_normalized=normalize_text(world.market_text), market_id=market.id),
        MarketAlias(alias=world.import_market_text, alias_normalized=normalize_text(world.import_market_text),
                    market_id=import_market.id),
    ])
    for key, producer in world.producers.items():
        code = f"{key}-RAF-{sfx}"
        session.add(ProducerGradeAlias(producer_id=producer.id, alias="RAF-1", alias_normalized="RAF-1",
                                       producer_grade_code=code))
        session.add(GradeEquivalence(producer_id=producer.id, producer_grade_code=code, grade_id=grade.id))

    profile = copy.deepcopy(ERP_PROFILE)
    profile["sectors"]["IMPORT"]["benchmark_eligible"] = import_eligible
    world.erp_source = RateSource(
        code=f"ERP-{sfx}", name="Test ERP", source_type=SourceType.ERP_FEED, priority=10, staleness_days=14,
        publishing_policy=PublishingPolicy.REVIEW_REQUIRED, normalization_profile=profile, profile_version=1,
    )
    world.manual_source = RateSource(
        code=f"MAN-{sfx}", name="Test manual", source_type=SourceType.MANUAL, priority=20, staleness_days=7,
        publishing_policy=PublishingPolicy.REVIEW_REQUIRED,
    )
    world.series = {
        "inr": RateSeries(code=f"S-INR-{sfx}", display_name="Test INR", grade_id=grade.id, market_id=market.id,
                          price_basis="DELIVERED", tax_basis="GST_EXCLUDED", currency="INR", unit="KG",
                          visibility=SeriesVisibility.SIGNED_IN_PLATFORM),
        "usd": RateSeries(code=f"S-USD-{sfx}", display_name="Test USD", grade_id=grade.id,
                          market_id=import_market.id, price_basis="IMPORT_ORIGIN", tax_basis="GST_EXCLUDED",
                          currency="USD", unit="KG", visibility=SeriesVisibility.SIGNED_IN_PLATFORM),
    }
    session.add_all([world.erp_source, world.manual_source, *world.series.values()])
    session.flush()
    return world
