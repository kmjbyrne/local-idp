from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clients import Client, ClientStore
from app.config import Settings
from app.factory import create_app
from app.keys import Keyring
from app.store import User, UserStore


@pytest.fixture
def instance_dir(tmp_path: Path) -> Path:
    """A fresh instance directory, so no test sees another's file."""
    return tmp_path


@pytest.fixture
def settings(instance_dir: Path) -> Settings:
    return Settings(
        INSTANCE_DIR=instance_dir,
        ISSUER="http://testserver",
        AUDIENCE="test-audience",
    )


@pytest.fixture
def users(settings: Settings) -> UserStore:
    return UserStore(settings.users_path)


@pytest.fixture
def clients(settings: Settings) -> ClientStore:
    return ClientStore(settings.clients_path)


@pytest.fixture
def keyring(settings: Settings) -> Keyring:
    return Keyring(settings.keys_path)


@pytest.fixture
def client(settings: Settings, instance_dir: Path) -> TestClient:
    """The app, with empty stores.

    Seeding is suppressed by writing both files first, since seed() is guarded
    on the file not existing. A test that wants the seeded personas uses
    `seeded_client` instead, so every other test starts from a store holding
    exactly what it put there.
    """
    (instance_dir / "users.json").write_text("[]")
    (instance_dir / "clients.json").write_text("[]")
    return TestClient(create_app(settings))


@pytest.fixture
def seeded_client(settings: Settings) -> TestClient:
    """The app as a first run builds it, personas and all."""
    return TestClient(create_app(settings))


@pytest.fixture
def a_user() -> User:
    return User(
        key="ada",
        subject="subject-ada",
        name="Ada Lovelace",
        email="ada@example.test",
        purpose="Writes the first program.",
        roles=["admin"],
        permissions=["boards.write"],
    )


@pytest.fixture
def a_client() -> Client:
    return Client(
        client_id="test-client",
        client_secret="test-secret",
        name="Test client",
    )
