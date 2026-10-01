"""A supplier submits a fully specified product. A pricing admin accepts it into the catalogue."""

from app.models.catalogue import Product
from app.models.listing import SupplierListing
from sqlalchemy import select
from tests.test_api import as_user

SUBMISSIONS = "/api/v1/product-submissions"
ADMIN = "/api/v1/admin/product-submissions"

SPECS = {
    "grade": "Raffia",
    "mfi": "3.5",
    "density": "0.905",
    "application": "Woven sacks",
    "quality": "Prime",
}


def _body(world, **overrides):
    body = {
        "proposedCode": f"SUB-{world.suffix}",
        "name": "Submitted PP",
        "category": "Polypropylene",
        "subcategory": "Raffia",
        "description": "Prime raffia grade",
        "uom": "KG",
        "specifications": SPECS,
        "askingPrice": "92.5000",
        "currency": "INR",
        "minimumQuantity": "500",
        "availability": "in_stock",
    }
    body.update(overrides)
    return body


def test_supplier_submits_and_admin_accepts_into_catalogue(client, world):
    created = client.post(SUBMISSIONS, json=_body(world), headers=as_user(world, "supplier"))
    assert created.status_code == 201, created.text
    submission = created.json()
    assert submission["status"] == "pending"
    assert submission["specifications"]["quality"] == "Prime"
    assert submission["productCode"] is None

    hidden = client.get(ADMIN, headers=as_user(world, "supplier"))
    assert hidden.status_code == 403

    queued = client.get(ADMIN, headers=as_user(world, "alice"))
    assert queued.status_code == 200
    assert [row["id"] for row in queued.json()] == [submission["id"]]

    accepted = client.post(
        f"{ADMIN}/{submission['id']}/accept",
        json={"productCode": f"ACC-{world.suffix}"},
        headers=as_user(world, "alice"),
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["productCode"] == f"ACC-{world.suffix}"

    product = world.session.scalar(select(Product).where(Product.product_code == f"ACC-{world.suffix}"))
    assert product is not None
    assert product.specifications["grade"] == "Raffia"
    assert product.specifications["quality"] == "Prime"
    assert product.uom == "KG"
    listing = world.session.scalar(select(SupplierListing).where(SupplierListing.product_id == product.id))
    assert listing is not None
    assert listing.supplier_user_id == world.users["supplier"].id
    assert str(listing.asking_price) == "92.5000"


def test_missing_specification_is_rejected(client, world):
    specs = dict(SPECS)
    del specs["quality"]
    response = client.post(SUBMISSIONS, json=_body(world, specifications=specs), headers=as_user(world, "supplier"))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert "Quality" in response.json()["error"]["details"]["fields"]


def test_buyer_cannot_submit(client, world):
    response = client.post(SUBMISSIONS, json=_body(world), headers=as_user(world, "buyer"))
    assert response.status_code == 403


def test_reject_keeps_the_product_out_of_the_catalogue(client, world):
    created = client.post(SUBMISSIONS, json=_body(world), headers=as_user(world, "supplier"))
    submission_id = created.json()["id"]
    rejected = client.post(
        f"{ADMIN}/{submission_id}/reject",
        json={"note": "This grade is already listed under another code."},
        headers=as_user(world, "bob"),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reviewNote"] == "This grade is already listed under another code."
    own = client.get(SUBMISSIONS, headers=as_user(world, "supplier"))
    assert own.json()[0]["status"] == "rejected"
    assert world.session.scalar(select(Product).where(Product.product_code == f"SUB-{world.suffix}")) is None


def test_second_pending_code_is_refused(client, world):
    headers = as_user(world, "supplier")
    assert client.post(SUBMISSIONS, json=_body(world), headers=headers).status_code == 201
    again = client.post(SUBMISSIONS, json=_body(world), headers=headers)
    assert again.status_code == 422
