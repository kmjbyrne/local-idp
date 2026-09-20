from fastapi.testclient import TestClient

from app.store import User, UserStore


def test_the_api_returns_the_stored_users(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada", name="Ada Lovelace"))

    response = client.get("/api/users")

    assert response.status_code == 200
    assert response.json()[0]["subject"] == "s-ada"


def test_a_user_is_created_through_the_api(client: TestClient, users: UserStore):
    response = client.post(
        "/api/users",
        json={"key": "grace", "subject": "s-grace", "roles": ["admin"]},
    )

    assert response.status_code == 201
    assert users.get("grace").roles == ["admin"]


def test_a_duplicate_key_is_a_conflict(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))

    response = client.post("/api/users", json={"key": "ada", "subject": "other"})

    assert response.status_code == 409


def test_a_user_is_patched_through_the_api(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada", name="Ada Lovelace", roles=["admin"]))

    response = client.patch("/api/users/ada", json={"roles": ["editor"]})

    assert response.status_code == 200
    assert users.get("ada").roles == ["editor"]
    assert users.get("ada").name == "Ada Lovelace"


def test_patching_somebody_absent_is_a_miss(client: TestClient):
    assert client.patch("/api/users/nobody", json={"name": "x"}).status_code == 404


def test_a_user_is_deleted_through_the_api(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))

    assert client.delete("/api/users/ada").status_code == 204
    assert users.load() == []


def test_the_health_check_counts_what_is_stored(client: TestClient, users: UserStore):
    users.add(User(key="ada", subject="s-ada"))

    body = client.get("/health").json()

    assert body["status"] is True
    assert body["users"] == 1


def test_the_health_check_fails_on_unreadable_json(client: TestClient, users: UserStore):
    users.path.parent.mkdir(parents=True, exist_ok=True)
    users.path.write_text("{ truncated")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] is False


def test_the_seeded_personas_are_written_on_a_first_run(
    seeded_client: TestClient, users: UserStore
):
    # Alice's subject is the one eagata-backend's fixtures give her. The two
    # must not drift: a token for a subject that service has never seen looks
    # like a new signup rather than an error.
    stored = {u.key: u.subject for u in users.load()}

    assert stored["alice"] == "019b76da-b3b8-741c-ada2-4c1da1ed4927"
    assert len(stored) == 9


def test_a_corrupt_user_file_is_reported_not_a_crash(client: TestClient, users: UserStore):
    users.path.write_text("Internal Server Error")

    response = client.get("/api/users")

    assert response.status_code == 503
    assert "users.json" in response.json()["detail"]
