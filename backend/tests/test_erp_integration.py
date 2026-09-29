import inspect
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import get_settings
from app.core.errors import ErpUnavailable
from app.integrations.erp import mock, reader, sqlserver
from app.integrations.erp.factory import get_erp_reader
from app.integrations.erp.mock import MockErpReader
from app.integrations.erp.sqlserver import STATEMENTS, SqlServerErpReader, assert_read_only
from app.main import app
from app.models.erp import ErpCustomer, ErpGrade, ErpPriceRowImport, ErpSyncRun
from app.models.pricing import BenchmarkRate, ImportBatch, SourceRate
from app.pricing.constants import BenchmarkStatus
from tests.test_api import as_user

SYNC = "/api/v1/admin/integrations/erp/sync"
SNAPSHOT = datetime(2026, 9, 28, 10, 30)
READ_METHODS = {"latest_price_snapshot", "domestic_grades", "customers"}
ERP_PACKAGE = Path(sqlserver.__file__).parent


@pytest.fixture
def erp(client, world, monkeypatch):
    monkeypatch.setattr(get_settings(), "erp_rate_source_code", world.erp_source.code)
    fake = MockErpReader()
    app.dependency_overrides[get_erp_reader] = lambda: fake
    return fake


def _price(world, sr_no, value, *, at=SNAPSHOT, **overrides):
    return {**world.row(sr_no, value, **overrides), "SysDate": at}


def _snapshot(world):
    sfx = world.suffix
    return [
        _price(world, 1, "99.40"),
        {**world.import_row(2, "1.1350"), "SysDate": SNAPSHOT},
        _price(world, 3, "98.00", grade="RAF-9"),
        _price(world, 4, "0"),
        _price(world, 5, "97.00", currency="EUR"),
        _price(world, 7, "90.10", sector="Deemed"),
        {**_price(world, 8, "96.00"), "Company": f"Mystery {sfx}"},
        {**_price(world, 9, "95.00"), "SrNo": None},
        _price(world, 10, "94.00", at=datetime(2026, 9, 21, 10, 30)),
    ]


def _grades(world):
    code = world.producers["A"].code
    return [
        {"SrNo": 1, "Company": code, "Quality": "PP", "Grade": "RAF-1", "MFI": Decimal("3.4"),
         "Density": Decimal("0.9"), "ItemCode": "RM-100"},
        {"SrNo": 3, "Company": code, "Quality": "PP", "Grade": "RAF-9", "MFI": None, "Density": None,
         "ItemCode": "RM-900"},
        {"SrNo": 8, "Company": f"Unlisted {world.suffix}", "Quality": "PP", "Grade": "Z1", "MFI": "bad",
         "Density": None, "ItemCode": None},
        {"SrNo": 11, "Company": code, "Quality": "PP", "Grade": None},
    ]


def _customers(world):
    sfx = world.suffix
    sensitive = {"PANNo": "ABCDE1234F", "BankAccount": "000111222333", "CreditLimit": Decimal("500000")}
    return [
        {"CompanyName": f"Ardent {sfx}", "GSTIN": "24abcde1234f1z5", "PINCode": Decimal("380015"), **sensitive},
        {"CompanyName": f"Bravo {sfx}", "GSTIN": "NOT-A-GSTIN", "PINCode": "12345", **sensitive},
        {"CompanyName": f"Charlie {sfx}", "GSTIN": "", "PINCode": None},
        {"CompanyName": f"Ardent {sfx}", "GSTIN": "24ABCDE1234F1Z5", "PINCode": "380015"},
        {"CompanyName": "  ", "GSTIN": "24ABCDE1234F1Z5", "PINCode": "380015"},
    ]


def _sync(client, world, key="alice"):
    return client.post(SYNC, headers=as_user(world, key))


def _count(world, model):
    return world.session.scalar(select(func.count()).select_from(model))


def test_sync_imports_latest_snapshot_and_reports_statistics(client, world, erp):
    erp.prices, erp.grades, erp.customer_rows = _snapshot(world), _grades(world), _customers(world)
    response = _sync(client, world)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["adapter"] == "mock" and body["status"] == "succeeded"
    assert body["snapshotSysDate"] == "2026-09-28T10:30:00" and body["snapshotAsOfDate"] == "2026-09-28"
    prices = body["prices"]
    assert {k: prices[k] for k in ("rowsRead", "rejected", "alreadyImported", "imported", "resolved", "unresolved",
                                   "ineligible", "suggestionsSubmittedForReview", "benchmarksPublished")} == {
        "rowsRead": 9, "rejected": 2, "alreadyImported": 0, "imported": 7, "resolved": 3, "unresolved": 4,
        "ineligible": 1, "suggestionsSubmittedForReview": 2, "benchmarksPublished": 0,
    }
    assert prices["flaggedByReason"] == {"invalid_value": 1, "unknown_grade": 1, "unknown_producer": 1,
                                         "unsupported_currency": 1}
    assert sorted(r["reason"] for r in prices["rejectedRows"]) == ["missing_sr_no", "outside_latest_snapshot"]

    batch = body["importBatch"]
    assert batch["rowCount"] == 7 and batch["resolvedCount"] == 3 and batch["unresolvedCount"] == 4
    assert batch["sourceAsOfDate"] == "2026-09-28" and batch["status"] == "succeeded"
    assert world.session.get(ImportBatch, batch["id"]).source_id == world.erp_source.id

    assert body["grades"] == {"rowsRead": 4, "rejected": 1, "created": 3, "updated": 0, "unchanged": 0, "mapped": 1,
                              "unmappedProducer": 1, "unmappedGrade": 1}
    unresolved = {(g["grade"], g["reason"]): g for g in body["unresolvedGrades"]}
    assert set(unresolved) == {("RAF-9", "unknown_grade"), ("RAF-1", "unknown_producer")}
    assert unresolved[("RAF-9", "unknown_grade")]["erpGradeMaster"] == {
        "found": True, "mappingStatus": "unmapped_grade", "erpItemCode": "RM-900"}
    assert unresolved[("RAF-9", "unknown_grade")]["srNos"] == [3]
    assert unresolved[("RAF-1", "unknown_producer")]["erpGradeMaster"]["found"] is False


def test_imported_rows_preserve_erp_identity(client, world, erp):
    erp.prices = _snapshot(world)
    _sync(client, world)
    rates = {r.source_identity_key: r for r in world.session.scalars(
        select(SourceRate).where(SourceRate.source_id == world.erp_source.id))}
    assert set(rates) == {"1", "2", "3", "4", "5", "7", "8"}
    domestic = rates["1"]
    assert domestic.value == Decimal("99.4000") and domestic.currency == "INR" and domestic.unit == "KG"
    assert domestic.raw_payload["row"]["SysDate"] == "2026-09-28T10:30" and domestic.raw_payload["row"]["SrNo"] == 1
    assert domestic.source_row_ref == "DomesticPrice1:SrNo=1" and domestic.series_id == world.series["inr"].id
    assert rates["2"].currency == "USD" and rates["2"].series_id == world.series["usd"].id
    ledger = world.session.scalars(select(ErpPriceRowImport).where(ErpPriceRowImport.source_id == world.erp_source.id)).all()
    assert {(row.erp_sys_date, row.erp_sr_no) for row in ledger} == {(SNAPSHOT, n) for n in (1, 2, 3, 4, 5, 7, 8)}


def test_sync_is_idempotent_on_sysdate_and_srno(client, world, erp):
    erp.prices = _snapshot(world)
    first = _sync(client, world).json()
    again = _sync(client, world).json()
    assert again["rowsRead"] == 9 and again["imported"] == 0 and again["skipped"] == 7 and again["rejected"] == 2
    assert again["prices"]["imported"] == 0 and again["prices"]["alreadyImported"] == 7
    assert again["unresolvedGrades"]
    assert any(warning["code"] == "invalid_value" for warning in again["warnings"])
    assert again["importBatch"] is None and again["prices"]["suggestionsSubmittedForReview"] == 0

    erp.prices = [*_snapshot(world), _price(world, 12, "93.00", at=datetime(2026, 9, 28, 10, 45))]
    third = _sync(client, world).json()
    assert third["prices"]["imported"] == 1 and third["prices"]["alreadyImported"] == 7
    assert third["importBatch"]["id"] != first["importBatch"]["id"]
    assert _count(world, ErpPriceRowImport) >= 8
    assert world.session.scalar(select(func.count()).select_from(SourceRate).where(
        SourceRate.source_id == world.erp_source.id)) == 8

    rate_id = world.session.scalar(select(SourceRate.id).where(
        SourceRate.source_id == world.erp_source.id, SourceRate.source_identity_key == "12"))
    run_id = world.session.scalar(select(ErpSyncRun.id).where(ErpSyncRun.id == third["runId"]))
    with pytest.raises(IntegrityError), world.session.begin_nested():
        world.session.add(ErpPriceRowImport(source_id=world.erp_source.id, erp_sys_date=SNAPSHOT, erp_sr_no=1,
                                            source_rate_id=rate_id, sync_run_id=run_id))
        world.session.flush()
    with pytest.raises(DBAPIError, match="immutable"), world.session.begin_nested():
        world.session.execute(text("DELETE FROM erp_price_row_imports WHERE source_id = :s"), {"s": world.erp_source.id})


def test_duplicate_and_superseded_rows_in_snapshot_are_rejected(client, world, erp):
    erp.prices = [
        _price(world, 1, "99.40"),
        _price(world, 1, "99.40"),
        _price(world, 1, "99.10", at=datetime(2026, 9, 28, 9, 0)),
        {**_price(world, 2, "99.00"), "SysDate": "not a date"},
        {**_price(world, 3, "99.00"), "SrNo": "3.5"},
    ]
    body = _sync(client, world).json()
    assert body["prices"]["imported"] == 1
    assert sorted(r["reason"] for r in body["prices"]["rejectedRows"]) == [
        "duplicate_row", "invalid_sr_no", "invalid_sys_date", "superseded_in_snapshot"]
    rate = world.session.scalar(select(SourceRate).where(SourceRate.source_id == world.erp_source.id))
    assert rate.value == Decimal("99.4000")


def test_price_fields_are_validated_by_the_existing_pipeline(client, world, erp):
    erp.prices = [
        _price(world, 1, "99.40", Total="101.00"),
        _price(world, 2, "99.40", Frieght="2.50"),
        _price(world, 3, "99.40", Sector="Export"),
        _price(world, 4, "abc"),
    ]
    body = _sync(client, world).json()
    assert body["prices"]["resolved"] == 0 and body["prices"]["unresolved"] == 4
    assert body["prices"]["flaggedByReason"] == {"invalid_value": 1, "price_fields_diverged": 1,
                                                 "unexpected_components": 1, "unknown_sector": 1}
    assert body["prices"]["suggestionsSubmittedForReview"] == 0


def test_sync_never_publishes_a_benchmark(client, world, erp):
    erp.prices = _snapshot(world)
    body = _sync(client, world).json()
    assert body["prices"]["benchmarksPublished"] == 0
    statuses = world.session.scalars(select(BenchmarkRate.status).where(
        BenchmarkRate.series_id.in_([s.id for s in world.series.values()]))).all()
    assert sorted(statuses) == [BenchmarkStatus.SUBMITTED, BenchmarkStatus.SUBMITTED]
    suggestion = world.session.scalar(select(BenchmarkRate).where(BenchmarkRate.series_id == world.series["inr"].id))
    assert suggestion.published_at is None and suggestion.submitted_by_id == world.session.scalar(
        select(ImportBatch.triggered_by_id).where(ImportBatch.id == body["importBatch"]["id"]))
    assert suggestion.submitted_by_id != world.users["alice"].id


def test_grade_identity_is_company_quality_and_grade(client, world, erp):
    code = world.producers["A"].code
    erp.grades = [
        {"Company": code, "Quality": "PP", "Grade": "RAF-1", "ItemCode": "PP-1"},
        {"Company": code, "Quality": "HDPE", "Grade": "RAF-1", "ItemCode": "HD-1"},
    ]
    erp.prices = [_price(world, 1, "99.40"), _price(world, 2, "98.00", Quality="HDPE")]
    body = _sync(client, world).json()
    assert body["grades"]["created"] == 2 and body["grades"]["mapped"] == 2
    stored = {
        grade.quality: grade.erp_item_code
        for grade in world.session.scalars(select(ErpGrade).where(ErpGrade.company == code))
    }
    assert stored == {"PP": "PP-1", "HDPE": "HD-1"}
    assert body["unresolvedGrades"] == []
    assert all(warning["code"] != "unknown_grade" for warning in body["warnings"])


def test_grades_and_customers_are_upserted(client, world, erp):
    erp.grades, erp.customer_rows = _grades(world), _customers(world)
    first = _sync(client, world).json()
    assert first["customers"] == {"rowsRead": 5, "rejected": 2, "created": 3, "updated": 0, "unchanged": 0,
                                  "missingGstin": 1, "invalidGstin": 1, "missingPin": 1, "invalidPin": 1}
    second = _sync(client, world).json()
    assert second["grades"]["unchanged"] == 3 and second["grades"]["created"] == 0
    assert second["customers"]["unchanged"] == 3 and second["customers"]["created"] == 0

    grade = world.session.scalar(select(ErpGrade).where(ErpGrade.company == world.producers["A"].code,
                                                        ErpGrade.grade == "RAF-1"))
    assert grade.mapping_status == "mapped" and grade.producer_id == world.producers["A"].id
    assert grade.mfi == Decimal("3.4") and grade.erp_item_code == "RM-100"
    unlisted = world.session.scalar(select(ErpGrade).where(ErpGrade.company == f"Unlisted {world.suffix}"))
    assert unlisted.mapping_status == "unmapped_producer" and unlisted.mfi is None

    erp.grades = [{**_grades(world)[1], "ItemCode": "RM-901"}]
    assert _sync(client, world).json()["grades"]["updated"] == 1


def test_customer_import_keeps_identity_only(client, world, erp):
    erp.customer_rows = _customers(world)
    response = _sync(client, world)
    assert set(ErpCustomer.__table__.columns.keys()) == {
        "id", "erp_name", "gstin", "pin_code", "first_seen_at", "last_synced_at", "last_sync_run_id"}
    stored = {c.erp_name: c for c in world.session.scalars(
        select(ErpCustomer).where(ErpCustomer.erp_name.like(f"% {world.suffix}")))}
    assert (stored[f"Ardent {world.suffix}"].gstin, stored[f"Ardent {world.suffix}"].pin_code) == (
        "24ABCDE1234F1Z5", "380015")
    assert (stored[f"Bravo {world.suffix}"].gstin, stored[f"Bravo {world.suffix}"].pin_code) == (None, None)
    for secret in ("ABCDE1234F", "000111222333", "500000", "Ardent", "Bravo", "380015"):
        assert secret not in response.text
    run = world.session.get(ErpSyncRun, response.json()["runId"])
    assert "000111222333" not in str(run.stats) and "Ardent" not in str(run.stats)


def test_sync_is_admin_only(client, world, erp):
    for key in ("buyer", "supplier"):
        denied = _sync(client, world, key)
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "PERMISSION_DENIED"
    assert client.post(SYNC).status_code == 401
    assert erp.calls == []
    assert _sync(client, world, "platform").status_code == 200
    assert _sync(client, world, "alice").status_code == 200
    assert world.session.get(ErpSyncRun, _sync(client, world, "bob").json()["runId"]).triggered_by_user_id == \
        world.users["bob"].id


def test_erp_disabled_by_default(client, world, monkeypatch):
    settings = get_settings()
    assert type(settings).model_fields["erp_enabled"].default is False
    before = _count(world, ErpSyncRun)
    monkeypatch.setattr(settings, "erp_enabled", False)
    response = _sync(client, world)
    assert response.status_code == 503 and response.json()["error"]["code"] == "ERP_DISABLED"

    monkeypatch.setattr(settings, "erp_enabled", True)
    monkeypatch.setattr(settings, "erp_host", None)
    unconfigured = _sync(client, world)
    assert unconfigured.status_code == 503 and unconfigured.json()["error"]["code"] == "ERP_NOT_CONFIGURED"
    assert "ERP_HOST" in unconfigured.json()["error"]["details"]["missing"]
    assert _count(world, ErpSyncRun) == before


def test_missing_rate_source_is_reported(client, world, erp, monkeypatch):
    monkeypatch.setattr(get_settings(), "erp_rate_source_code", f"NOPE-{world.suffix}")
    response = _sync(client, world)
    assert response.status_code == 503 and response.json()["error"]["code"] == "ERP_NOT_CONFIGURED"
    assert erp.calls == []


def test_erp_failure_stores_nothing(client, world, erp):
    before = (_count(world, ErpSyncRun), _count(world, ErpGrade))
    erp.grades = _grades(world)

    def fail():
        raise ErpUnavailable("ERP read failed")

    erp.customers = fail
    response = _sync(client, world)
    assert response.status_code == 502 and response.json()["error"]["code"] == "ERP_UNAVAILABLE"
    assert (_count(world, ErpSyncRun), _count(world, ErpGrade)) == before


def test_sync_only_calls_read_methods(client, world, erp):
    erp.prices = _snapshot(world)
    _sync(client, world)
    assert set(erp.calls) == READ_METHODS


# ---------------------------------------------------------------------------------------------- read-only


def test_readers_expose_only_read_methods():
    for cls in (reader.ErpReader, MockErpReader, SqlServerErpReader):
        public = {name for name, _ in inspect.getmembers(cls, inspect.isfunction) if not name.startswith("_")}
        assert public == READ_METHODS, cls


def test_no_erp_write_code_in_the_erp_package():
    write_sql = re.compile(r"(?i)\bINSERT\s+INTO\b|\bUPDATE\s+[\w.\[\]]+\s+SET\b|\bDELETE\s+FROM\b|\bMERGE\s+INTO\b|"
                           r"\bEXEC(UTE)?\s+[\w.\[]|\bTRUNCATE\s+TABLE\b|\.commit\(")
    for path in ERP_PACKAGE.glob("*.py"):
        if path.name == "sync.py":
            continue  # writes only to SourceOne through the SQLAlchemy session, never to an ERP connection
        assert not write_sql.search(path.read_text(encoding="utf-8")), path.name
    app_dir = ERP_PACKAGE.parents[1]
    drivers = [p for p in app_dir.rglob("*.py") if re.search(r"\bimport pyodbc\b|\bpymssql\b", p.read_text(encoding="utf-8"))]
    assert drivers == [Path(sqlserver.__file__)]
    assert "session" not in Path(mock.__file__).read_text(encoding="utf-8")


def test_only_plain_selects_pass_the_guard():
    for statement in STATEMENTS:
        assert assert_read_only(statement)
    for statement in (
        "INSERT INTO dbo.DomesticPrice1 (SrNo) VALUES (1)",
        "UPDATE dbo.DomesticPrice1 SET UnitPrice = 1",
        "DELETE FROM dbo.CompanyMaster",
        "SELECT * FROM dbo.DomesticPrice1; DROP TABLE dbo.DomesticPrice1",
        "SELECT * INTO dbo.Copy FROM dbo.DomesticPrice1",
        "EXEC sp_Automail_DomesticPrice",
        "SELECT 1 -- comment",
        "WITH x AS (SELECT 1 AS a) UPDATE dbo.T SET a = 1",
        "SELECT * FROM OPENQUERY(srv, 'DELETE FROM t')",
        "MERGE dbo.T USING dbo.S ON 1 = 1 WHEN MATCHED THEN DELETE",
    ):
        with pytest.raises(ValueError):
            assert_read_only(statement)


class _FakeCursor:
    def __init__(self, log, columns, records):
        self.log, self.description, self._records = log, [(c,) for c in columns], records

    def execute(self, sql):
        self.log.append(("execute", sql))

    def fetchall(self):
        return self._records


class _FakeConnection:
    def __init__(self, log, columns, records):
        self.log, self.columns, self.records, self.timeout = log, columns, records, None

    def cursor(self):
        return _FakeCursor(self.log, self.columns, self.records)

    def rollback(self):
        self.log.append(("rollback",))

    def commit(self):
        self.log.append(("commit",))

    def close(self):
        self.log.append(("close",))


class _FakeDriver:
    class Error(Exception):
        pass

    def __init__(self, columns=(), records=(), fail=False):
        self.log, self.columns, self.records, self.fail = [], columns, list(records), fail

    def connect(self, connection_string, **kwargs):
        self.log.append(("connect", connection_string, kwargs))
        if self.fail:
            raise self.Error(f"Login failed: {connection_string}")
        return _FakeConnection(self.log, self.columns, self.records)


def _erp_settings():
    return get_settings().model_copy(update={
        "erp_enabled": True, "erp_host": "erp.test", "erp_username": "reader", "erp_password": SecretStr("s3cret-value"),
    })


def test_sqlserver_reader_connects_read_only_and_never_commits():
    columns = ("CompanyName", "GSTIN", "PINCode")
    driver = _FakeDriver(columns, [(" Ardent ", "24ABCDE1234F1Z5", 380015.0)])
    rows = SqlServerErpReader(_erp_settings(), driver=driver).customers()
    assert rows == [{"CompanyName": "Ardent", "GSTIN": "24ABCDE1234F1Z5", "PINCode": Decimal("380015.0")}]
    (_, connection_string, kwargs), *rest = driver.log
    assert kwargs["readonly"] is True and kwargs["autocommit"] is False
    assert "ApplicationIntent=ReadOnly" in connection_string and "DATABASE={Despatch}" in connection_string
    executed = [entry[1] for entry in rest if entry[0] == "execute"]
    assert executed == [sqlserver.CUSTOMERS_SQL]
    assert [entry[0] for entry in rest] == ["execute", "rollback", "close"]
    assert ("commit",) not in driver.log


def test_sqlserver_reader_rejects_unexpected_columns_and_hides_driver_errors():
    settings = _erp_settings()
    extra = _FakeDriver(("CompanyName", "GSTIN", "PINCode", "BankAccount"), [])
    with pytest.raises(ErpUnavailable):
        SqlServerErpReader(settings, driver=extra).customers()
    assert ("rollback",) in extra.log and ("close",) in extra.log

    with pytest.raises(ErpUnavailable) as failure:
        SqlServerErpReader(settings, driver=_FakeDriver(fail=True)).latest_price_snapshot()
    assert "s3cret" not in str(failure.value) and "erp.test" not in str(failure.value)
    assert failure.value.__suppress_context__ is True
