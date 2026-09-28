from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.catalogue import products as catalogue
from app.core.clock import business_today, utcnow
from app.core.errors import CurrencyUnitMismatch, DuplicateProductCode, DuplicateProductMapping
from app.models.catalogue import Market, ProductRateSeries
from app.models.pricing import RateSeries
from app.pricing import service
from app.pricing.constants import SeriesVisibility
from tests.test_api import _flatten, as_user

PRODUCTS = "/api/v1/products"


def _publish(world, series="inr", value="99.40", days_ago=1):
    as_of = business_today(utcnow()) - timedelta(days=days_ago)
    draft = world.manual("alice", series, value, as_of=as_of)
    service.submit_benchmark(world.session, world.actors["alice"], draft.id)
    return service.publish_benchmark(world.session, world.actors["bob"], draft.id)


def _product(world, key="A", **kwargs):
    return catalogue.create_product(
        world.session, product_code=f"PRD{key}-{world.suffix}", name=kwargs.pop("name", f"Product {key}"),
        category=f"cat-{world.suffix}", subcategory="Polypropylene", description="Test product", uom="KG", **kwargs,
    )


def _second_market_series(world) -> RateSeries:
    inr = world.series["inr"]
    market = Market(code=f"M2-{world.suffix}", name="Second city", market_type="domestic")
    world.session.add(market)
    world.session.flush()
    series = RateSeries(
        code=f"S-INR2-{world.suffix}", display_name="Test INR second city", grade_id=inr.grade_id,
        market_id=market.id, price_basis="DELIVERED", tax_basis="GST_EXCLUDED", currency="INR", unit="KG",
        visibility=SeriesVisibility.SIGNED_IN_PLATFORM,
    )
    world.session.add(series)
    world.session.flush()
    return series


def test_create_product_and_reject_duplicate_code(world):
    product = _product(world)
    assert product.id is not None and product.is_active and product.uom == "KG"
    with pytest.raises(DuplicateProductCode):
        _product(world)


def test_map_series_and_reject_duplicate_mapping(world):
    product = _product(world)
    link = catalogue.map_rate_series(world.session, product, world.series["inr"], display_order=10)
    assert link.rate_series_id == world.series["inr"].id
    with pytest.raises(DuplicateProductMapping):
        catalogue.map_rate_series(world.session, product, world.series["inr"])


def test_database_rejects_duplicate_mapping(world):
    product = _product(world)
    catalogue.map_rate_series(world.session, product, world.series["inr"])
    with pytest.raises(IntegrityError), world.session.begin_nested():
        world.session.add(ProductRateSeries(product_id=product.id, rate_series_id=world.series["inr"].id))
        world.session.flush()


def test_mapping_requires_matching_unit(world):
    product = _product(world)
    product.uom = "MT"
    with pytest.raises(CurrencyUnitMismatch):
        catalogue.map_rate_series(world.session, product, world.series["inr"])


def test_list_and_detail_resolve_current_benchmark(client, world):
    _publish(world)
    product = _product(world)
    catalogue.map_rate_series(world.session, product, world.series["inr"])
    buyer = as_user(world, "buyer")

    listing = client.get(PRODUCTS, params={"category": product.category}, headers=buyer)
    assert listing.status_code == 200
    assert [p["productCode"] for p in listing.json()] == [product.product_code]

    detail = client.get(f"{PRODUCTS}/{product.product_code}", headers=buyer).json()
    assert detail["name"] == "Product A" and detail["subcategory"] == "Polypropylene"
    assert detail["uom"] == {"code": "KG", "label": "kg"}
    assert detail["priceLabel"] == "SourceOne benchmark" and detail["priceKind"] == "sourceone_benchmark"
    assert detail["availability"] == "available"
    assert detail["defaultSeriesCode"] == world.series["inr"].code
    [pricing] = detail["pricing"]
    assert pricing["market"]["code"] == world.series["inr"].market.code and pricing["currency"] == "INR"
    assert pricing["current"]["value"] == {"amount": "99.4000", "currency": "INR"}
    assert pricing["current"]["freshness"]["state"] == "fresh"
    assert pricing["current"]["freshness"]["asOfDate"]


def test_product_with_multiple_market_series(client, world):
    second = _second_market_series(world)
    _publish(world, "inr", "99.40")
    world.series["second"] = second
    _publish(world, "second", "98.10")
    product = _product(world)
    catalogue.map_rate_series(world.session, product, second, display_order=20)
    catalogue.map_rate_series(world.session, product, world.series["inr"], display_order=10)

    detail = client.get(f"{PRODUCTS}/{product.product_code}", headers=as_user(world, "buyer")).json()
    assert [p["seriesCode"] for p in detail["pricing"]] == [world.series["inr"].code, second.code]
    assert [p["current"]["value"]["amount"] for p in detail["pricing"]] == ["99.4000", "98.1000"]
    assert detail["defaultSeriesCode"] == world.series["inr"].code


def test_stale_benchmark_is_flagged(client, world):
    _publish(world, days_ago=10)
    product = _product(world)
    catalogue.map_rate_series(world.session, product, world.series["inr"])
    [pricing] = client.get(f"{PRODUCTS}/{product.product_code}", headers=as_user(world, "buyer")).json()["pricing"]
    assert pricing["availability"] == "available"
    assert pricing["current"]["freshness"]["state"] == "stale"


def test_withdrawn_benchmark_is_rate_on_request(client, world):
    benchmark = _publish(world)
    service.withdraw_benchmark(world.session, world.actors["bob"], benchmark.id, reason="Circular revised")
    product = _product(world)
    catalogue.map_rate_series(world.session, product, world.series["inr"])
    detail = client.get(f"{PRODUCTS}/{product.product_code}", headers=as_user(world, "buyer")).json()
    assert detail["availability"] == "rate_on_request"
    [pricing] = detail["pricing"]
    assert pricing["availability"] == "rate_on_request" and pricing["unavailableReason"] == "withdrawn"
    assert pricing["current"] is None


def test_unmapped_product_is_rate_on_request(client, world):
    product = _product(world)
    detail = client.get(f"{PRODUCTS}/{product.product_code}", headers=as_user(world, "buyer")).json()
    assert detail["availability"] == "rate_on_request"
    assert detail["pricing"] == [] and detail["defaultSeriesCode"] is None


def test_inactive_product_is_hidden(client, world):
    product = _product(world, is_active=False)
    buyer = as_user(world, "buyer")
    assert client.get(PRODUCTS, params={"category": product.category}, headers=buyer).json() == []
    missing = client.get(f"{PRODUCTS}/{product.product_code}", headers=buyer)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"


def test_inactive_mapping_and_inactive_series_are_excluded(client, world):
    second = _second_market_series(world)
    product = _product(world)
    catalogue.map_rate_series(world.session, product, world.series["inr"], is_active=False)
    catalogue.map_rate_series(world.session, product, world.series["usd"])
    catalogue.map_rate_series(world.session, product, second)
    second.is_active = False
    world.session.flush()
    detail = client.get(f"{PRODUCTS}/{product.product_code}", headers=as_user(world, "buyer")).json()
    assert [p["seriesCode"] for p in detail["pricing"]] == [world.series["usd"].code]


def test_buyer_product_response_has_no_producer_or_source_fields(client, world):
    _publish(world)
    as_of = business_today(utcnow()) - timedelta(days=2)
    world.ingest(as_of, [world.row(1, "99.40"), world.row(2, "99.00", producer="B")])
    product = _product(world)
    catalogue.map_rate_series(world.session, product, world.series["inr"])

    for payload in (
        client.get(PRODUCTS, params={"category": product.category}, headers=as_user(world, "buyer")).json(),
        client.get(f"{PRODUCTS}/{product.product_code}", headers=as_user(world, "supplier")).json(),
    ):
        keys, values = _flatten(payload)
        assert not [k for k in keys if "producer" in k.lower() or "source" in k.lower()]
        forbidden = {p.code for p in world.producers.values()} | {p.name for p in world.producers.values()}
        forbidden |= {world.erp_source.code, world.manual_source.code, "RAF-1", "Plant"}
        assert not [v for v in values if any(f in v for f in forbidden)]


def test_products_require_sign_in(client):
    assert client.get(PRODUCTS).status_code == 401
