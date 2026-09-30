"""Requirements stay frozen on the order, and fulfilment files are only for that order's parties."""

from app.catalogue import products as catalogue
from app.core.config import get_settings
from app.models.fulfilment import OrderDocument
from sqlalchemy import select

from tests.test_api import as_actor, as_user
from tests.test_negotiations import _other_buyer, _publish
from tests.test_orders import _negotiation, _place

import pytest


@pytest.fixture
def product(world):
    _publish(world, "99.40")
    item = catalogue.create_product(
        world.session, product_code=f"DOC-{world.suffix}", name="Documented PP",
        category=f"cat-{world.suffix}", uom="KG", specifications={"grade": "RAFFIA"},
    )
    catalogue.map_rate_series(world.session, item, world.series["inr"])
    return item


def test_requirements_stay_frozen_and_only_the_parties_can_open_a_file(client, world, product):
    negotiation = _negotiation(world, product, price="100", counter="100", quantity="10")
    answered = client.post(
        f"/api/v1/negotiations/{negotiation.id}/requirements/grade",
        json={"status": "met", "comment": "Lab checked"},
        headers=as_user(world, "supplier"),
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["requirementResponses"] == [{"key": "grade", "status": "met", "comment": "Lab checked"}]
    refused = client.post(
        f"/api/v1/negotiations/{negotiation.id}/requirements/grade",
        json={"status": "not_met"},
        headers=as_user(world, "buyer"),
    )
    assert refused.status_code == 403

    placed = _place(client, world, negotiation)
    assert placed.status_code == 201, placed.text
    order = placed.json()
    assert {"key": "grade", "label": "Grade", "value": "RAFFIA"} in order["requirements"]
    product.specifications = {"grade": "FILM"}
    world.session.flush()
    frozen = client.get(f"/api/v1/orders/{order['id']}", headers=as_user(world, "buyer")).json()
    assert {"key": "grade", "label": "Grade", "value": "RAFFIA"} in frozen["requirements"]
    assert all(row["value"] != "FILM" for row in frozen["requirements"])

    uploaded = client.post(
        f"/api/v1/orders/{order['id']}/documents",
        data={"documentType": "coa"},
        files={"file": ("coa.pdf", b"coa-bytes", "application/pdf")},
        headers=as_user(world, "supplier"),
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    opened = client.get(
        f"/api/v1/orders/{order['id']}/documents/{document_id}/file",
        headers=as_user(world, "buyer"),
    )
    assert opened.status_code == 200 and opened.content == b"coa-bytes"
    outsider = _other_buyer(world)
    assert client.get(
        f"/api/v1/orders/{order['id']}/documents/{document_id}/file",
        headers=as_actor(outsider),
    ).status_code == 403

    stored = world.session.scalar(select(OrderDocument).where(OrderDocument.id == document_id))
    (get_settings().document_dir.parent / "order_documents" / stored.stored_name).unlink()
    listed = client.get(f"/api/v1/orders/{order['id']}", headers=as_user(world, "buyer")).json()
    assert listed["documents"] == []
