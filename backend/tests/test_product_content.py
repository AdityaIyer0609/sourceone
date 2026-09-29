"""Product documents and questions stay in SourceOne. Nothing is read from the ERP."""

from app.core.config import get_settings
from tests.test_api import as_user
from tests.test_listings import _create
from tests.test_negotiations import product  # noqa: F401


def test_active_documents_can_be_downloaded_and_inactive_ones_stay_hidden(client, world, product, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "document_dir", tmp_path)
    admin = as_user(world, "alice")
    uploaded = client.post(
        f"/api/v1/admin/products/{product.product_code}/documents",
        data={"name": "Grade note", "documentType": "note"},
        files={"file": ("grade-note.txt", b"grade note", "text/plain")},
        headers=admin,
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uploaded.json()["id"]
    buyer = as_user(world, "buyer")
    listed = client.get(f"/api/v1/products/{product.product_code}/documents", headers=buyer)
    assert listed.status_code == 200 and [row["name"] for row in listed.json()] == ["Grade note"]
    downloaded = client.get(f"/api/v1/products/{product.product_code}/documents/{document_id}/file", headers=buyer)
    assert downloaded.status_code == 200 and downloaded.content == b"grade note"
    hidden = client.post(
        f"/api/v1/admin/products/{product.product_code}/documents/{document_id}/active",
        json={"isActive": False},
        headers=admin,
    )
    assert hidden.status_code == 200 and hidden.json()["isActive"] is False
    assert client.get(f"/api/v1/products/{product.product_code}/documents", headers=buyer).json() == []
    assert client.get(f"/api/v1/products/{product.product_code}/documents/{document_id}/file", headers=buyer).status_code == 404
    admin_list = client.get(f"/api/v1/admin/products/{product.product_code}/documents", headers=admin).json()
    assert admin_list[0]["isActive"] is False


def test_supplier_listing_the_product_can_answer(client, world, product):
    buyer = as_user(world, "buyer")
    empty = client.get(f"/api/v1/products/{product.product_code}/questions", headers=buyer).json()
    assert empty["questions"] == [] and empty["canAsk"] is True and empty["canAnswer"] is False
    asked = client.post(
        f"/api/v1/products/{product.product_code}/questions",
        json={"body": "What is the packing?"},
        headers=buyer,
    )
    assert asked.status_code == 201, asked.text
    assert asked.json()["status"] == "open"
    assert asked.json()["askedBy"]
    question_id = asked.json()["id"]
    refused = client.post(
        f"/api/v1/products/{product.product_code}/questions/{question_id}/answers",
        json={"body": "25 kg bags"},
        headers=as_user(world, "supplier"),
    )
    assert refused.status_code == 403
    _create(client, world, product)
    answered = client.post(
        f"/api/v1/products/{product.product_code}/questions/{question_id}/answers",
        json={"body": "25 kg bags"},
        headers=as_user(world, "supplier"),
    )
    assert answered.status_code == 201, answered.text
    assert answered.json()["status"] == "answered"
    assert answered.json()["answers"][0]["body"] == "25 kg bags"
    assert client.post(
        f"/api/v1/products/{product.product_code}/questions/{question_id}/answers",
        json={"body": "no"},
        headers=buyer,
    ).status_code == 403
