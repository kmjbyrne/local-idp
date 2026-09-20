import base64
import json

import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from app.config import Settings
from app.factory import create_app
from app.keys import Keyring


def _kid(token: str) -> str:
    """Return the key id the token's header names."""
    header = token.split(".", maxsplit=1)[0]
    decoded = base64.urlsafe_b64decode(header + "=" * (-len(header) % 4))
    return json.loads(decoded)["kid"]


def _mint(client: TestClient, subject: str = "s-1") -> str:
    return client.post("/dev/token", json={"subject": subject}).json()["access_token"]


def _verify(token: str, jwks: dict) -> dict:
    return jwt.decode(token, KeySet.import_key_set(jwks)).claims


def test_a_key_is_generated_on_a_first_run(keyring: Keyring):
    keyring.load()

    assert keyring.active_kid
    assert len(keyring.keys) == 1


def test_the_key_survives_a_restart(settings: Settings):
    first = Keyring(settings.keys_path)
    first.load()

    second = Keyring(settings.keys_path)
    second.load()

    assert second.active_kid == first.active_kid
    assert second.active.as_dict() == first.active.as_dict()


def test_a_token_still_verifies_after_a_restart(settings: Settings):
    before = TestClient(create_app(settings))
    token = _mint(before)

    after = TestClient(create_app(settings))
    jwks = after.get("/.well-known/jwks.json").json()

    assert _verify(token, jwks)["sub"] == "s-1"


def test_the_private_half_is_never_published(client: TestClient):
    jwks = client.get("/.well-known/jwks.json").json()

    for key in jwks["keys"]:
        assert "d" not in key


def test_the_private_half_is_stored(keyring: Keyring):
    keyring.load()

    stored = json.loads(keyring.path.read_text())

    assert "d" in next(iter(stored["keys"].values()))["jwk"]


def test_the_token_header_names_the_key_that_signed_it(client: TestClient):
    token = _mint(client)

    published = {k["kid"] for k in client.get("/.well-known/jwks.json").json()["keys"]}

    assert _kid(token) in published


class TestRotation:
    def test_a_rotation_signs_with_the_new_key(self, client: TestClient):
        old_kid = _kid(_mint(client))

        client.post("/api/keys", json={"algorithm": "ES256", "make_active": True})

        assert _kid(_mint(client)) != old_kid

    def test_both_keys_stay_published(self, client: TestClient):
        client.post("/api/keys", json={"make_active": True})

        jwks = client.get("/.well-known/jwks.json").json()

        assert len(jwks["keys"]) == 2

    def test_a_token_from_before_the_rotation_still_verifies(self, client: TestClient):
        old_token = _mint(client, "before")

        client.post("/api/keys", json={"make_active": True})
        jwks = client.get("/.well-known/jwks.json").json()

        assert _verify(old_token, jwks)["sub"] == "before"

    def test_a_key_can_be_published_without_signing(self, client: TestClient):
        signing_before = _kid(_mint(client))

        client.post("/api/keys", json={"make_active": False})

        assert len(client.get("/.well-known/jwks.json").json()["keys"]) == 2
        assert _kid(_mint(client)) == signing_before

    def test_a_published_key_can_be_activated_later(self, client: TestClient):
        added = client.post("/api/keys", json={"make_active": False}).json()["kid"]

        client.post(f"/api/keys/{added}/activate")

        assert _kid(_mint(client)) == added

    def test_the_active_key_is_listed_first(self, client: TestClient):
        added = client.post("/api/keys", json={"make_active": True}).json()["kid"]

        jwks = client.get("/.well-known/jwks.json").json()

        assert jwks["keys"][0]["kid"] == added

    def test_retiring_a_key_stops_its_tokens_verifying(self, client: TestClient):
        old_token = _mint(client, "doomed")
        old_kid = _kid(old_token)
        client.post("/api/keys", json={"make_active": True})

        assert client.delete(f"/api/keys/{old_kid}").status_code == 204

        jwks = client.get("/.well-known/jwks.json").json()
        assert len(jwks["keys"]) == 1
        # joserfc refuses on the kid before it reaches a signature check, which
        # is what a client does too: the key it is told to use is not published.
        with pytest.raises(JoseError):
            _verify(old_token, jwks)

    def test_the_active_key_may_not_be_retired(self, client: TestClient):
        active = client.get("/api/keys").json()["active"]

        response = client.delete(f"/api/keys/{active}")

        assert response.status_code == 409

    def test_an_unknown_key_cannot_be_activated(self, client: TestClient):
        assert client.post("/api/keys/never-made/activate").status_code == 404

    def test_an_rsa_key_can_be_added_alongside_an_ec_one(self, client: TestClient):
        client.post("/api/keys", json={"algorithm": "RS256", "make_active": True})

        token = _mint(client)
        jwks = client.get("/.well-known/jwks.json").json()

        assert _verify(token, jwks)["sub"] == "s-1"
        assert {k["kty"] for k in jwks["keys"]} == {"RSA", "EC"}

    def test_an_unsupported_algorithm_is_refused(self, client: TestClient):
        assert client.post("/api/keys", json={"algorithm": "HS256"}).status_code == 400

    def test_a_rotation_survives_a_restart(self, settings: Settings):
        first = TestClient(create_app(settings))
        added = first.post("/api/keys", json={"make_active": True}).json()["kid"]

        second = TestClient(create_app(settings))

        assert second.get("/api/keys").json()["active"] == added
        assert len(second.get("/.well-known/jwks.json").json()["keys"]) == 2
