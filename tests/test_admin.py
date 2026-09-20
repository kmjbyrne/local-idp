from fastapi.testclient import TestClient

from app.clients import ClientStore
from app.store import User, UserStore


def test_the_index_lists_the_stored_users(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada", name="Ada Lovelace"))

    page = client.get("/")

    assert page.status_code == 200
    assert "Ada Lovelace" in page.text


def test_a_user_is_added_through_the_form(client: TestClient, users: UserStore):
    response = client.post(
        "/users",
        data={
            "key": "grace",
            "subject": "s-grace",
            "name": "Grace Hopper",
            "roles": "admin, editor",
            "permissions": "boards.write",
            "purpose": "Finds the bug.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    stored = users.get("grace")
    assert stored.name == "Grace Hopper"
    assert stored.roles == ["admin", "editor"]
    assert stored.permissions == ["boards.write"]


def test_a_user_without_a_subject_is_refused(client: TestClient):
    response = client.post("/users", data={"key": "k", "subject": "  "})

    assert response.status_code == 400


def test_the_edit_page_shows_the_current_values(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada", name="Ada Lovelace", roles=["admin"]))

    page = client.get("/users/ada")

    assert page.status_code == 200
    assert "s-ada" in page.text
    assert "admin" in page.text


def test_an_edit_is_saved(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada", name="Ada Lovelace"))

    client.post(
        "/users/ada",
        data={"key": "ada", "subject": "s-ada", "name": "Ada King", "roles": "admin"},
        follow_redirects=False,
    )

    assert users.get("ada").name == "Ada King"
    assert users.get("ada").roles == ["admin"]


def test_a_user_is_deleted_through_the_form(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))

    client.post("/users/ada/delete", follow_redirects=False)

    assert users.load() == []


def test_a_client_is_registered_through_the_form(client: TestClient, clients: ClientStore):
    client.post(
        "/clients",
        data={
            "client_id": "web",
            "client_secret": "shh",
            "name": "Web app",
            "enforce_secret": "true",
        },
        follow_redirects=False,
    )

    stored = clients.get("web")
    assert stored.client_secret == "shh"
    assert stored.enforce_secret is True


def test_an_unchecked_box_turns_the_secret_check_off(client: TestClient, clients: ClientStore):
    client.post(
        "/clients",
        data={"client_id": "lax", "client_secret": "shh"},
        follow_redirects=False,
    )

    assert clients.get("lax").enforce_secret is False


def test_a_name_with_markup_does_not_reach_the_page_raw(client: TestClient, users: UserStore):
    users.add(User(key="x", subject="s-x", name="<script>alert(1)</script>"))

    page = client.get("/")

    assert "<script>alert(1)</script>" not in page.text
    assert "&lt;script&gt;" in page.text
