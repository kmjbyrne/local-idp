from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import KeySet

from app.clients import Client, ClientStore
from app.store import User, UserStore

REDIRECT = "http://localhost:3000/auth/callback"


def _authorize(client: TestClient, persona: str, **extra: str) -> str:
    """Pick ``persona`` and return the code the redirect carries."""
    response = client.get(
        "/dev/authorize",
        params={"redirect_uri": REDIRECT, "persona": persona, **extra},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    location = urlparse(response.headers["location"])
    return parse_qs(location.query)["code"][0]


def _claims(token: str) -> dict:
    """Verify ``token`` against the published keys and return its claims."""
    return jwt.decode(token, KeySet.import_key_set(_JWKS)).claims


_JWKS: dict = {}


def _publish_keys(client: TestClient) -> None:
    _JWKS.clear()
    _JWKS.update(client.get("/.well-known/jwks.json").json())


def test_discovery_points_at_this_provider(client: TestClient):
    document = client.get("/.well-known/openid-configuration").json()

    assert document["issuer"] == "http://testserver"
    assert document["authorization_endpoint"] == "http://testserver/dev/authorize"
    assert document["token_endpoint"] == "http://testserver/dev/token"
    assert document["userinfo_endpoint"] == "http://testserver/dev/userinfo"
    assert "openid" in document["scopes_supported"]


def test_the_public_key_is_published(client: TestClient):
    jwks = client.get("/.well-known/jwks.json").json()

    assert jwks["keys"]
    assert "d" not in jwks["keys"][0]


def test_the_authorize_page_lists_the_stored_users(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada", name="Ada Lovelace"))

    page = client.get("/dev/authorize", params={"redirect_uri": REDIRECT})

    assert page.status_code == 200
    assert "Ada Lovelace" in page.text


def test_the_authorize_page_shows_a_user_added_after_startup(client: TestClient, users: UserStore):
    before = client.get("/dev/authorize", params={"redirect_uri": REDIRECT}).text
    assert "Grace Hopper" not in before

    users.add(User(key="grace", subject="s-grace", name="Grace Hopper"))

    after = client.get("/dev/authorize", params={"redirect_uri": REDIRECT}).text
    assert "Grace Hopper" in after


def test_picking_a_user_redirects_back_with_a_code(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))

    code = _authorize(client, "ada")

    assert code


def test_the_state_is_handed_back_unchanged(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))

    response = client.get(
        "/dev/authorize",
        params={"redirect_uri": REDIRECT, "persona": "ada", "state": "xyz-123"},
        follow_redirects=False,
    )

    assert parse_qs(urlparse(response.headers["location"]).query)["state"] == ["xyz-123"]


def test_an_unknown_user_is_refused(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))

    response = client.get(
        "/dev/authorize",
        params={"redirect_uri": REDIRECT, "persona": "nobody"},
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_the_token_carries_the_users_claims(client: TestClient, users: UserStore):
    users.add(
        User(
            key="ada",
            subject="s-ada",
            name="Ada Lovelace",
            email="ada@example.test",
            roles=["admin"],
            permissions=["boards.write"],
        )
    )
    _publish_keys(client)
    code = _authorize(client, "ada")

    response = client.post(
        "/dev/token",
        data={"grant_type": "authorization_code", "code": code},
    )

    assert response.status_code == 200
    claims = _claims(response.json()["access_token"])
    assert claims["sub"] == "s-ada"
    assert claims["name"] == "Ada Lovelace"
    assert claims["email"] == "ada@example.test"
    assert claims["roles"] == ["admin"]
    assert claims["permissions"] == ["boards.write"]
    assert claims["iss"] == "http://testserver"
    assert claims["aud"] == "test-audience"


def test_a_code_may_only_be_used_once(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))
    code = _authorize(client, "ada")
    form = {"grant_type": "authorization_code", "code": code}

    assert client.post("/dev/token", data=form).status_code == 200
    assert client.post("/dev/token", data=form).status_code == 400


def test_an_unknown_code_is_refused(client: TestClient):
    response = client.post(
        "/dev/token",
        data={"grant_type": "authorization_code", "code": "never-issued"},
    )

    assert response.status_code == 400


def test_a_refresh_grant_is_refused(client: TestClient):
    response = client.post("/dev/token", data={"grant_type": "refresh_token"})

    assert response.status_code == 400


def test_a_json_body_mints_without_a_browser(client: TestClient, users: UserStore):
    _publish_keys(client)

    response = client.post("/dev/token", json={"subject": "direct", "roles": ["admin"]})

    assert response.status_code == 200
    assert _claims(response.json()["access_token"])["sub"] == "direct"


def test_a_json_body_fills_the_claims_of_a_stored_user(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada", name="Ada Lovelace", roles=["admin"]))
    _publish_keys(client)

    response = client.post("/dev/token", json={"subject": "s-ada"})

    claims = _claims(response.json()["access_token"])
    assert claims["name"] == "Ada Lovelace"
    assert claims["roles"] == ["admin"]


class TestClientCredentials:
    def test_the_right_secret_is_accepted(
        self, client: TestClient, users: UserStore, clients: ClientStore, a_client: Client
    ):
        users.add(User(key="ada", subject="s-ada"))
        clients.add(a_client)
        code = _authorize(client, "ada")

        response = client.post(
            "/dev/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": "test-client",
                "client_secret": "test-secret",
            },
        )

        assert response.status_code == 200

    def test_a_wrong_secret_is_rejected(
        self, client: TestClient, users: UserStore, clients: ClientStore, a_client: Client
    ):
        users.add(User(key="ada", subject="s-ada"))
        clients.add(a_client)
        code = _authorize(client, "ada")

        response = client.post(
            "/dev/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": "test-client",
                "client_secret": "wrong",
            },
        )

        assert response.status_code == 401
        assert "client_secret" in response.json()["detail"]

    def test_an_unknown_client_is_rejected(
        self, client: TestClient, users: UserStore, clients: ClientStore, a_client: Client
    ):
        users.add(User(key="ada", subject="s-ada"))
        clients.add(a_client)
        code = _authorize(client, "ada")

        response = client.post(
            "/dev/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": "somebody-else",
                "client_secret": "test-secret",
            },
        )

        assert response.status_code == 401

    def test_credentials_are_accepted_in_a_basic_auth_header(
        self, client: TestClient, users: UserStore, clients: ClientStore, a_client: Client
    ):
        users.add(User(key="ada", subject="s-ada"))
        clients.add(a_client)
        code = _authorize(client, "ada")

        response = client.post(
            "/dev/token",
            data={"grant_type": "authorization_code", "code": code},
            auth=("test-client", "test-secret"),
        )

        assert response.status_code == 200

    def test_a_client_may_opt_out_of_the_check(
        self, client: TestClient, users: UserStore, clients: ClientStore
    ):
        users.add(User(key="ada", subject="s-ada"))
        clients.add(Client(client_id="lax", client_secret="real", enforce_secret=False))
        code = _authorize(client, "ada")

        response = client.post(
            "/dev/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": "lax",
                "client_secret": "anything",
            },
        )

        assert response.status_code == 200

    def test_an_empty_registry_accepts_anything(self, client: TestClient, users: UserStore):
        users.add(User(key="ada", subject="s-ada"))
        code = _authorize(client, "ada")

        response = client.post(
            "/dev/token",
            data={"grant_type": "authorization_code", "code": code},
        )

        assert response.status_code == 200

    def test_an_unregistered_redirect_uri_is_refused(
        self, client: TestClient, users: UserStore, clients: ClientStore
    ):
        users.add(User(key="ada", subject="s-ada"))
        clients.add(Client(client_id="strict", client_secret="s", redirect_uris=[REDIRECT]))

        response = client.get(
            "/dev/authorize",
            params={
                "redirect_uri": "http://evil.test/steal",
                "persona": "ada",
                "client_id": "strict",
            },
            follow_redirects=False,
        )

        assert response.status_code == 400


class TestOidcIdToken:
    """Tests for OIDC id_token behavior."""

    def test_openid_scope_returns_id_token(self, client: TestClient, users: UserStore):
        users.add(User(key="ada", subject="s-ada", name="Ada Lovelace", email="ada@example.test"))
        _publish_keys(client)
        code = _authorize(client, "ada", scope="openid profile email")

        response = client.post(
            "/dev/token",
            data={"grant_type": "authorization_code", "code": code},
        )

        assert response.status_code == 200
        body = response.json()
        assert "id_token" in body
        assert "access_token" in body
        id_claims = _claims(body["id_token"])
        assert id_claims["sub"] == "s-ada"
        assert id_claims["name"] == "Ada Lovelace"
        assert id_claims["email"] == "ada@example.test"
        assert "at_hash" in id_claims
        assert "auth_time" in id_claims

    def test_no_openid_scope_omits_id_token(self, client: TestClient, users: UserStore):
        users.add(User(key="ada", subject="s-ada"))
        code = _authorize(client, "ada")

        response = client.post(
            "/dev/token",
            data={"grant_type": "authorization_code", "code": code},
        )

        assert response.status_code == 200
        assert "id_token" not in response.json()

    def test_nonce_is_echoed_in_id_token(self, client: TestClient, users: UserStore):
        users.add(User(key="ada", subject="s-ada"))
        _publish_keys(client)
        code = _authorize(client, "ada", scope="openid", nonce="test-nonce-123")

        response = client.post(
            "/dev/token",
            data={"grant_type": "authorization_code", "code": code},
        )

        id_claims = _claims(response.json()["id_token"])
        assert id_claims["nonce"] == "test-nonce-123"

    def test_profile_scope_includes_name(self, client: TestClient, users: UserStore):
        users.add(User(key="ada", subject="s-ada", name="Ada Lovelace"))
        _publish_keys(client)
        code = _authorize(client, "ada", scope="openid profile")

        id_claims = _claims(
            client.post("/dev/token", data={"grant_type": "authorization_code", "code": code})
            .json()["id_token"]
        )
        assert id_claims["name"] == "Ada Lovelace"

    def test_openid_only_omits_profile_and_email(self, client: TestClient, users: UserStore):
        users.add(User(key="ada", subject="s-ada", name="Ada Lovelace", email="ada@example.test"))
        _publish_keys(client)
        code = _authorize(client, "ada", scope="openid")

        id_claims = _claims(
            client.post("/dev/token", data={"grant_type": "authorization_code", "code": code})
            .json()["id_token"]
        )
        assert id_claims["sub"] == "s-ada"
        assert "name" not in id_claims
        assert "email" not in id_claims


class TestUserinfo:
    """Tests for the /dev/userinfo endpoint."""

    def test_userinfo_returns_claims(self, client: TestClient, users: UserStore):
        users.add(User(key="ada", subject="s-ada", name="Ada Lovelace", email="ada@example.test"))
        _publish_keys(client)
        code = _authorize(client, "ada")
        token = client.post(
            "/dev/token",
            data={"grant_type": "authorization_code", "code": code},
        ).json()["access_token"]

        response = client.get("/dev/userinfo", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        body = response.json()
        assert body["sub"] == "s-ada"
        assert body["name"] == "Ada Lovelace"
        assert body["email"] == "ada@example.test"

    def test_userinfo_rejects_missing_token(self, client: TestClient):
        response = client.get("/dev/userinfo")

        assert response.status_code == 401

    def test_userinfo_rejects_invalid_token(self, client: TestClient):
        response = client.get("/dev/userinfo", headers={"Authorization": "Bearer garbage"})

        assert response.status_code == 401
