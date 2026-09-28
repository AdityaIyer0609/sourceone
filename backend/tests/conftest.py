"""Tests run against the configured PostgreSQL database inside a transaction that is always rolled back."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import engine, get_db
from app.main import app
from tests.factories import World, build_world


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def world(db) -> World:
    return build_world(db)


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_auth_enabled", True)
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
