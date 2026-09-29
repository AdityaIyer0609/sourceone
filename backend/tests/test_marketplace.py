"""Buyer marketplace reads the active SourceOne catalogue."""

from pathlib import Path

from app.catalogue import products as catalogue
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_products import PRODUCTS, _product, _publish

ROOT = Path(__file__).resolve().parents[2] / "frontend" / "src"
PAGE = ROOT / "pages" / "MarketplacePage.tsx"
CATALOGUE = ROOT / "pages" / "CataloguePage.tsx"
CARD = ROOT / "components" / "product" / "ProductCard.tsx"


def test_marketplace_shows_active_products_only(client, world):
    _publish(world)
    live = _product(world)
    catalogue.map_rate_series(world.session, live, world.series["inr"])
    hidden = catalogue.create_product(
        world.session, product_code=f"PRDX-{world.suffix}", name="Hidden grade",
        category=live.category, subcategory="Polypropylene", uom="KG", is_active=False,
    )
    buyer = as_user(world, "buyer")
    codes = {row["productCode"] for row in client.get(PRODUCTS, headers=buyer).json()}
    assert live.product_code in codes
    assert hidden.product_code not in codes
    listed = client.get(PRODUCTS, params={"category": live.category}, headers=buyer).json()
    assert [row["productCode"] for row in listed] == [live.product_code]
    assert client.get(PRODUCTS, params={"q": hidden.product_code}, headers=buyer).json() == []


def test_marketplace_category_filter_and_search(client, world):
    film = catalogue.create_product(
        world.session, product_code=f"PRDF-{world.suffix}", name=f"Zetaquill {world.suffix}",
        category=f"films-{world.suffix}", subcategory="Cast film", uom="KG",
    )
    buyer = as_user(world, "buyer")
    by_category = client.get(PRODUCTS, params={"category": film.category}, headers=buyer).json()
    assert [row["productCode"] for row in by_category] == [film.product_code]
    assert by_category[0]["subcategory"] == "Cast film"
    found = client.get(PRODUCTS, params={"q": f"Zetaquill {world.suffix}"}, headers=buyer).json()
    assert [row["productCode"] for row in found] == [film.product_code]
    assert client.get(PRODUCTS, params={"q": hidden_token(world)}, headers=buyer).json() == []


def hidden_token(world) -> str:
    return f"nomatch-{world.suffix}-zz"


def test_marketplace_benchmark_and_supplier_count(client, world):
    _publish(world)
    live = _product(world)
    catalogue.map_rate_series(world.session, live, world.series["inr"])
    plain = catalogue.create_product(
        world.session, product_code=f"PRDN-{world.suffix}", name="Unpriced grade",
        category=f"plain-{world.suffix}", uom="KG",
    )
    _create(client, world, live)
    buyer = as_user(world, "buyer")
    priced = client.get(f"{PRODUCTS}/{live.product_code}", headers=buyer).json()
    assert priced["availability"] == "available"
    assert priced["pricing"][0]["current"]["value"] == {"amount": "99.4000", "currency": "INR"}
    assert priced["listingCount"] == 1
    assert priced["uom"] == {"code": "KG", "label": "kg"}
    on_request = client.get(f"{PRODUCTS}/{plain.product_code}", headers=buyer).json()
    assert on_request["availability"] == "rate_on_request" and on_request["pricing"] == []
    assert on_request["listingCount"] == 0
    created = _create(client, world, plain).json()
    client.patch(f"/api/v1/listings/{created['id']}", json={"isActive": False}, headers=as_user(world, "supplier"))
    assert client.get(f"{PRODUCTS}/{plain.product_code}", headers=buyer).json()["listingCount"] == 0


def test_marketplace_page_uses_real_catalogue_navigation():
    page = PAGE.read_text(encoding="utf-8")
    catalogue = CATALOGUE.read_text(encoding="utf-8")
    card = CARD.read_text(encoding="utf-8")
    assert "listProducts" in page
    assert "paths.productDetail(product.productCode)" in page
    assert "useProducts" in catalogue
    assert "paths.productDetail(product.productCode)" in catalogue
    assert not (ROOT / "mocks" / "data.ts").exists()
    assert "badge: 3" not in (ROOT / "app" / "navigation.ts").read_text(encoding="utf-8")
    assert "390020" not in (ROOT / "components" / "layout" / "Topbar.tsx").read_text(encoding="utf-8")
    assert "15 minutes" not in (ROOT / "components" / "layout" / "Sidebar.tsx").read_text(encoding="utf-8")
    for sample in ("Stainless steel", "Carbon steel", "1,284", "4,862", "Sheets & plates", "Non-ferrous", "Ready stock", "marketplaceCategories"):
        assert sample not in page
        assert sample not in catalogue
    assert "Rate on request" in card
    assert "listingCount" in card
