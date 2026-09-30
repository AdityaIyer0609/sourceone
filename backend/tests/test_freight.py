from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.core.clock import business_today
from app.models.freight import FreightRule
from app.models.listing import SupplierListing
from app.models.pricing import BenchmarkRate
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import _offer, _start, product  # noqa: F401

RULES = "/api/v1/admin/freight/rules"
ESTIMATES = "/api/v1/freight/estimates"


def _rule(client, world, **extra):
    body = {
        "originPin": "560001", "originLabel": "Bengaluru",
        "destinationPin": "390020", "destinationLabel": "Vadodara",
        "ratePerKg": "1.2500", "currency": "INR", "minimumFreight": "1500",
        "isActive": True, "effectiveFrom": "2026-01-01", **extra,
    }
    return client.post(RULES, json=body, headers=as_user(world, "platform"))


def _origin(world, pin="560001", label="Bengaluru"):
    org = world.users["supplier"].organisation
    org.dispatch_pin = pin
    org.dispatch_label = label
    world.session.flush()


def _estimate(client, world, product, listing, quantity="1000", pin="390020", include_distance=False):
    body = {
        "supplierUserId": listing["supplierUserId"], "productCode": product.product_code,
        "quantity": quantity, "destinationPin": pin,
    }
    if include_distance:
        body["includeDistance"] = True
    return client.post(ESTIMATES, json=body, headers=as_user(world, "buyer"))


def test_admin_creates_a_matching_freight_rule(client, world, product):
    assert client.post(RULES, json={
        "originPin": "560001", "originLabel": "Bengaluru", "destinationPin": "390020",
        "destinationLabel": "Vadodara", "ratePerKg": "1", "currency": "INR",
        "isActive": True, "effectiveFrom": "2026-01-01",
    }, headers=as_user(world, "buyer")).status_code == 403
    created = _rule(client, world)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["rateUnit"] == "KG" and body["ratePerKg"] == "1.2500"
    assert body["minimumFreight"] == "1500.0000" and body["isActive"] is True
    _origin(world)
    listing = _create(client, world, product, askingPrice="100.2500").json()
    estimate = _estimate(client, world, product, listing)
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["ruleId"] == body["id"]
    assert estimate.json()["freightStatus"] == "estimated"


def test_no_matching_rule_is_freight_on_request(client, world, product):
    _origin(world)
    listing = _create(client, world, product).json()
    _rule(client, world, destinationPin="380015", destinationLabel="Ahmedabad")
    estimate = _estimate(client, world, product, listing, pin="390020")
    assert estimate.status_code == 200, estimate.text
    body = estimate.json()
    assert body["freightStatus"] == "on_request"
    assert body["freight"] is None and body["landedValue"] is None and body["landedCostPerUnit"] is None
    assert body["supplierAskingPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert body["materialValue"] == {"amount": "100250.0000", "currency": "INR"}


def test_inactive_and_expired_rules_are_not_used(client, world, product):
    _origin(world)
    listing = _create(client, world, product).json()
    inactive = _rule(client, world, isActive=False)
    assert inactive.status_code == 201
    hidden = _estimate(client, world, product, listing)
    assert hidden.json()["freightStatus"] == "on_request" and hidden.json()["freight"] is None

    yesterday = (business_today() - timedelta(days=1)).isoformat()
    _rule(client, world, isActive=True, effectiveFrom="2020-01-01", effectiveTo=yesterday)
    future = (business_today() + timedelta(days=30)).isoformat()
    _rule(client, world, effectiveFrom=future, effectiveTo=None, minimumFreight=None)
    still = _estimate(client, world, product, listing)
    assert still.json()["freightStatus"] == "on_request"


def test_quantity_and_landed_cost(client, world, product):
    _origin(world)
    listing = _create(client, world, product, askingPrice="100.2500").json()
    _rule(client, world, ratePerKg="2.5000", minimumFreight="8000")
    small = _estimate(client, world, product, listing, quantity="1000").json()
    # 1,000 kg x 2.50 = 2,500, raised to the 8,000 minimum.
    assert small["freight"] == {"amount": "8000.0000", "currency": "INR"}
    assert small["minimumFreightApplied"] is True
    assert small["materialValue"] == {"amount": "100250.0000", "currency": "INR"}
    assert small["landedValue"] == {"amount": "108250.0000", "currency": "INR"}
    assert small["landedCostPerUnit"] == {"amount": "108.2500", "currency": "INR"}
    large = _estimate(client, world, product, listing, quantity="10000").json()
    # 10,000 kg x 2.50 = 25,000, above the minimum.
    assert large["freight"] == {"amount": "25000.0000", "currency": "INR"}
    assert large["minimumFreightApplied"] is False
    assert large["materialValue"] == {"amount": "1002500.0000", "currency": "INR"}
    assert large["landedValue"] == {"amount": "1027500.0000", "currency": "INR"}
    assert large["landedCostPerUnit"] == {"amount": "102.7500", "currency": "INR"}


def test_currency_mismatch_does_not_invent_a_rate(client, world, product):
    _origin(world)
    listing = _create(client, world, product, askingPrice="100.2500").json()
    usd = _rule(client, world, currency="USD", ratePerKg="0.0200", minimumFreight=None)
    assert usd.status_code == 201, usd.text
    estimate = _estimate(client, world, product, listing).json()
    assert estimate["freightStatus"] == "on_request"
    assert estimate["freight"] is None
    assert estimate["supplierAskingPrice"]["currency"] == "INR"


def test_pin_zone_covers_other_pins_and_exact_lane_wins(client, world, product):
    _origin(world, pin="560001")
    listing = _create(client, world, product, askingPrice="100.0000").json()
    zone = _rule(client, world, originPin="560", originLabel="Bengaluru zone", destinationPin="411", destinationLabel="Pune zone", ratePerKg="1.0000", minimumFreight=None)
    assert zone.status_code == 201, zone.text
    covered = _estimate(client, world, product, listing, quantity="1000", pin="411014").json()
    assert covered["freightStatus"] == "estimated"
    assert covered["match"] == "zone"
    assert covered["freight"] == {"amount": "1000.0000", "currency": "INR"}
    exact = _rule(client, world, destinationPin="411014", destinationLabel="Pune", ratePerKg="3.0000", minimumFreight=None)
    assert exact.status_code == 201, exact.text
    chosen = _estimate(client, world, product, listing, quantity="1000", pin="411014").json()
    assert chosen["match"] == "lane"
    assert chosen["freight"] == {"amount": "3000.0000", "currency": "INR"}
    assert chosen["ruleId"] == exact.json()["id"]


def test_default_rate_covers_an_unmatched_pin(client, world, product):
    _origin(world)
    listing = _create(client, world, product, askingPrice="100.0000").json()
    saved = client.put("/api/v1/admin/freight/defaults", json={
        "currency": "INR", "ratePerKg": "0.5000", "minimumFreight": "2000", "isActive": True,
    }, headers=as_user(world, "platform"))
    assert saved.status_code == 200, saved.text
    estimate = _estimate(client, world, product, listing, quantity="1000", pin="682001").json()
    assert estimate["match"] == "default"
    assert estimate["freight"] == {"amount": "2000.0000", "currency": "INR"}
    assert estimate["minimumFreightApplied"] is True
    assert "not a measured distance" in estimate["note"]
    _rule(client, world, destinationPin="682001", destinationLabel="Kochi", ratePerKg="4.0000", minimumFreight=None)
    lane = _estimate(client, world, product, listing, quantity="1000", pin="682001").json()
    assert lane["match"] == "lane"
    assert lane["freight"] == {"amount": "4000.0000", "currency": "INR"}


def test_supplier_price_and_negotiation_stay_separate_from_landed_cost(client, world, product):
    before = world.session.scalar(select(func.count()).select_from(BenchmarkRate))
    _origin(world)
    listing = _create(client, world, product, askingPrice="100.2500").json()
    _rule(client, world, ratePerKg="2.5000", minimumFreight="8000")
    estimate = _estimate(client, world, product, listing, quantity="12000").json()
    assert estimate["landedCostPerUnit"]["amount"] != "100.2500"
    started = _start(client, world, product, price="100.2500", supplierUserId=listing["supplierUserId"])
    assert started.status_code == 201, started.text
    negotiation = started.json()
    assert negotiation["versions"][0]["offeredPrice"] == {"amount": "100.2500", "currency": "INR"}
    assert negotiation["benchmark"]["value"] == {"amount": "100.2500", "currency": "INR"}
    countered = _offer(client, world, "supplier", negotiation["id"], "99.0000")
    assert countered.status_code == 201, countered.text
    accepted = client.post(f"/api/v1/negotiations/{negotiation['id']}/accept", headers=as_user(world, "buyer"))
    assert accepted.status_code == 200, accepted.text
    order = client.post(
        f"/api/v1/orders/from-negotiation/{negotiation['id']}",
        json={"destinationPin": "682001"},
        headers=as_user(world, "buyer"),
    )
    assert order.status_code == 201, order.text
    body = order.json()
    assert body["agreedPrice"]["unitPrice"] == {"amount": "99.0000", "currency": "INR"}
    assert body["agreedPrice"]["priceKind"] == "negotiated_price"
    assert body["totalValue"]["amount"] != estimate["landedValue"]["amount"]
    stored = world.session.get(SupplierListing, listing["id"])
    assert stored.asking_price == Decimal("100.2500")
    assert world.session.scalar(select(func.count()).select_from(FreightRule)) >= 1
    assert world.session.scalar(select(func.count()).select_from(BenchmarkRate)) == before
