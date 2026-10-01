from pathlib import Path

from tests.test_api import as_user
from tests.test_negotiations import _start
from tests.test_orders import product  # noqa: F401

ITEMS = "/api/v1/admin/products"
PRODUCTS = "/api/v1/products"
PAGE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "ProductDetailPage.tsx"


def _create(client, world, code, **specs):
    body = {
        "productCode": f"{code}-{world.suffix}", "name": code, "category": "Polymers",
        "subcategory": "Polypropylene", "description": f"{code} description", "uom": "KG",
        "specifications": specs or None,
    }
    response = client.post(ITEMS, json=body, headers=as_user(world, "alice"))
    assert response.status_code == 201, response.text
    return response.json()["productCode"]


def _values(client, world, code):
    detail = client.get(f"{PRODUCTS}/{code}", headers=as_user(world, "buyer"))
    assert detail.status_code == 200, detail.text
    return {row["key"]: row["value"] for row in detail.json()["specifications"]}


def test_specifications_are_returned_from_the_product(client, world):
    code = _create(client, world, "RAF", grade="PP Raffia", mfi="3.0 g/10 min", application="Raffia", quality="Prime")
    values = _values(client, world, code)
    assert values["grade"] == "PP Raffia"
    assert values["mfi"] == "3.0 g/10 min"
    assert values["application"] == "Raffia"
    assert values["quality"] == "Prime"
    assert values["uom"] == "KG"
    assert values["description"] == "RAF description"
    assert "producer" not in values and values["density"] is None


def test_missing_specifications_are_empty(client, world):
    code = _create(client, world, "BARE")
    values = _values(client, world, code)
    assert values["grade"] is None and "producer" not in values
    assert values["mfi"] is None and values["density"] is None
    assert "AISI" not in str(values) and "ASTM" not in str(values)
    edited = client.patch(f"{ITEMS}/{code}", json={
        "name": "BARE", "category": "Polymers", "subcategory": "Polypropylene", "description": "BARE description",
        "specifications": {"density": "0.905 g/cm3", "melt_index": ""},
    }, headers=as_user(world, "alice"))
    assert edited.status_code == 200, edited.text
    updated = _values(client, world, code)
    assert updated["density"] == "0.905 g/cm3"
    assert "melt_index" not in updated


def test_products_keep_their_own_specifications(client, world):
    raffia = _create(client, world, "ONE", grade="PP Raffia", mfi="3.0 g/10 min")
    film = _create(client, world, "TWO", grade="LLDPE Liner", mfi="1.0 g/10 min", producer="Borouge")
    assert _values(client, world, raffia)["mfi"] == "3.0 g/10 min"
    assert _values(client, world, film)["mfi"] == "1.0 g/10 min"
    assert "producer" not in _values(client, world, film)
    assert "Borouge" not in _values(client, world, film).values()


def test_inactive_product_stays_hidden(client, world, product):
    hidden = client.post(f"{ITEMS}/{product.product_code}/active", json={"isActive": False}, headers=as_user(world, "alice"))
    assert hidden.status_code == 200
    assert client.get(f"{PRODUCTS}/{product.product_code}", headers=as_user(world, "buyer")).status_code == 404
    assert _start(client, world, product).status_code == 404


def test_product_page_has_no_sample_steel_specifications():
    text = PAGE.read_text(encoding="utf-8")
    for sample in (
        "AISI", "ASTM A240", "ASTM A480", "0.8–3.0", "Surface finish", "Coil ID",
        "4.8 (126)", "MTC available", "Dispatch in 48 hrs", "45 days", "Quality assured",
    ):
        assert sample not in text
    assert "listProducts" in text and "listingCount" in text and "No related products" in text
