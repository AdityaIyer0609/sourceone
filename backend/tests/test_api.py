from datetime import date, timedelta

from app.core.clock import business_today, utcnow

PRICING = "/api/v1/admin/pricing"


def _flatten(payload, keys=None, values=None):
    keys, values = (keys if keys is not None else []), (values if values is not None else [])
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.append(key)
            _flatten(value, keys, values)
    elif isinstance(payload, list):
        for item in payload:
            _flatten(item, keys, values)
    elif payload is not None:
        values.append(str(payload))
    return keys, values


def as_user(world, key):
    return {"X-Demo-User": world.users[key].email}


def _ingest_recent(world, value="99.40", days_ago=3):
    as_of = business_today(utcnow()) - timedelta(days=days_ago)
    return world.ingest(as_of, [world.row(1, value), world.row(2, "90.45", sector="Deemed"),
                                world.row(3, "99.00", producer="B")])


def test_requires_sign_in(client):
    response = client.get("/api/v1/benchmarks")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_buyer_cannot_read_admin_endpoints(client, world):
    for path in ("/source-rates", "/series", "/benchmarks", "/sources", "/audit"):
        response = client.get(PRICING + path, headers=as_user(world, "buyer"))
        assert response.status_code == 403, path
    assert client.get(PRICING + "/series", headers=as_user(world, "supplier")).status_code == 403


def test_admin_select_submit_publish_then_buyer_sees_benchmark(client, world):
    rates = _ingest_recent(world).source_rates
    alice = as_user(world, "alice")

    listed = client.get(PRICING + "/source-rates", params={"batchId": str(rates[0].import_batch_id)}, headers=alice)
    assert listed.status_code == 200
    by_sector = {r["sector"]: r for r in listed.json()}
    assert by_sector["DEEMED"]["isBenchmarkEligible"] is False
    assert by_sector["DOMESTIC"]["sourceRowRef"].startswith("DomesticPrice1:SrNo=")

    created = client.post(PRICING + "/benchmarks", json={"mode": "select_source_rate", "sourceRateId": str(rates[0].id)},
                          headers=alice)
    assert created.status_code == 201, created.text
    benchmark_id = created.json()["id"]
    assert created.json()["status"] == "draft" and created.json()["fourEyesRequired"] is False
    assert client.post(f"{PRICING}/benchmarks/{benchmark_id}/submit", headers=alice).status_code == 200
    published = client.post(f"{PRICING}/benchmarks/{benchmark_id}/publish", headers=alice)
    assert published.status_code == 200 and published.json()["status"] == "published"

    series_code = world.series["inr"].code
    buyer = as_user(world, "buyer")
    summary = client.get(f"/api/v1/benchmarks/{series_code}", headers=buyer).json()
    assert summary["availability"] == "available"
    assert summary["priceLabel"] == "SourceOne benchmark"
    assert summary["current"]["value"] == {"amount": "99.4000", "currency": "INR"}
    assert summary["current"]["freshness"]["state"] == "fresh"
    keys, values = _flatten(summary)
    assert not [k for k in keys if "producer" in k.lower() or "source" in k.lower()]
    forbidden = {p.code for p in world.producers.values()} | {p.name for p in world.producers.values()}
    forbidden |= {world.erp_source.code, "RAF-1", "Plant"}
    assert not [v for v in values if any(f in v for f in forbidden)]

    history = client.get(f"/api/v1/benchmarks/{series_code}/history", params={"range": "1M"}, headers=buyer).json()
    assert len(history["points"]) == 1 and history["stats"]["state"] == "insufficient_data"

    estimate = client.get(f"/api/v1/benchmarks/{series_code}/estimate", params={"quantity": "1000"}, headers=buyer)
    assert estimate.json()["amount"] == {"amount": "99400.00", "currency": "INR"}
    assert estimate.json()["priceKind"] == "estimated_material_value"
    mismatch = client.get(f"/api/v1/benchmarks/{series_code}/estimate", params={"quantity": "1", "unit": "MT"},
                          headers=buyer)
    assert mismatch.status_code == 422 and mismatch.json()["error"]["code"] == "CURRENCY_OR_UNIT_MISMATCH"

    listing = client.get("/api/v1/benchmarks", params={"market": world.series["inr"].market.code}, headers=buyer)
    assert [b["seriesCode"] for b in listing.json()] == [series_code]

    withdrawn = client.post(f"{PRICING}/benchmarks/{benchmark_id}/withdraw", json={"reason": "Circular revised"},
                            headers=as_user(world, "bob"))
    assert withdrawn.status_code == 200
    after = client.get(f"/api/v1/benchmarks/{series_code}", headers=buyer).json()
    assert after["availability"] == "rate_on_request" and after["current"] is None


def test_api_errors_for_four_eyes_transition_and_validation(client, world):
    alice, bob = as_user(world, "alice"), as_user(world, "bob")
    as_of = (business_today(utcnow()) - timedelta(days=1)).isoformat()
    manual = client.post(PRICING + "/benchmarks", headers=alice, json={
        "mode": "manual", "seriesId": str(world.series["inr"].id), "value": "101.25", "currency": "INR",
        "unit": "KG", "sourceAsOfDate": as_of, "reason": "Circular received",
    })
    assert manual.status_code == 201, manual.text
    benchmark_id = manual.json()["id"]

    early = client.post(f"{PRICING}/benchmarks/{benchmark_id}/publish", headers=bob)
    assert early.status_code == 409 and early.json()["error"]["code"] == "INVALID_STATE_TRANSITION"

    client.post(f"{PRICING}/benchmarks/{benchmark_id}/submit", headers=alice)
    own = client.post(f"{PRICING}/benchmarks/{benchmark_id}/publish", headers=alice)
    assert own.status_code == 403 and own.json()["error"]["code"] == "FOUR_EYES_REQUIRED"
    assert client.post(f"{PRICING}/benchmarks/{benchmark_id}/publish", headers=bob).status_code == 200

    duplicate = client.post(PRICING + "/benchmarks", headers=alice, json={
        "mode": "manual", "seriesId": str(world.series["inr"].id), "value": "101.50", "currency": "INR",
        "unit": "KG", "sourceAsOfDate": as_of, "reason": "Second attempt",
    })
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "DUPLICATE_EFFECTIVE_FROM"

    wrong_currency = client.post(PRICING + "/benchmarks", headers=alice, json={
        "mode": "manual", "seriesId": str(world.series["inr"].id), "value": "1.1", "currency": "USD",
        "unit": "KG", "sourceAsOfDate": date.today().isoformat(), "reason": "Wrong currency",
    })
    assert wrong_currency.status_code == 422
    assert wrong_currency.json()["error"]["code"] == "CURRENCY_OR_UNIT_MISMATCH"

    patched = client.patch(f"{PRICING}/benchmarks/{benchmark_id}", headers=alice,
                           json={"rowVersion": 1, "value": "1.00", "reason": "Tamper"})
    assert patched.status_code == 409 and patched.json()["error"]["code"] == "PUBLISHED_BENCHMARK_IMMUTABLE"

    audit = client.get(PRICING + "/audit", params={"entityId": benchmark_id}, headers=alice).json()
    assert {e["action"] for e in audit} == {"created", "submitted", "published"}


def test_unresolved_source_rate_cannot_be_selected(client, world):
    as_of = business_today(utcnow()) - timedelta(days=2)
    rate = world.ingest(as_of, [world.row(1, "97.5", Grade="UNKNOWN")]).source_rates[0]
    response = client.post(PRICING + "/benchmarks", headers=as_user(world, "alice"),
                           json={"mode": "select_source_rate", "sourceRateId": str(rate.id)})
    assert response.status_code == 422 and response.json()["error"]["code"] == "SOURCE_RATE_UNRESOLVED"
