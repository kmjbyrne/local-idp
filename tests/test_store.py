import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.store import User, UserStore, parse_list


def test_a_stored_user_survives_a_round_trip(users: UserStore, a_user: User):
    users.add(a_user)

    assert users.load() == [a_user]


def test_the_subject_is_preserved_exactly(users: UserStore):
    users.add(User(key="k", subject="019b76da-a800-741f-8a5b-bba72959884e"))

    assert users.get("k").subject == "019b76da-a800-741f-8a5b-bba72959884e"


def test_reading_a_missing_file_gives_no_users(users: UserStore):
    assert users.load() == []


def test_a_key_may_not_be_used_twice(users: UserStore, a_user: User):
    users.add(a_user)

    with pytest.raises(ValueError, match="already exists"):
        users.add(a_user)


def test_a_user_can_be_edited(users: UserStore, a_user: User):
    users.add(a_user)

    users.patch("ada", name="Ada King")

    assert users.get("ada").name == "Ada King"
    assert users.get("ada").subject == a_user.subject


def test_renaming_a_key_keeps_one_record(users: UserStore, a_user: User):
    users.add(a_user)

    users.patch("ada", key="ada-k")

    assert [u.key for u in users.load()] == ["ada-k"]


def test_a_user_can_be_deleted(users: UserStore, a_user: User):
    users.add(a_user)

    users.delete("ada")

    assert users.load() == []


def test_deleting_somebody_absent_is_an_error(users: UserStore):
    with pytest.raises(ValueError, match="No user"):
        users.delete("nobody")


def test_a_failed_write_leaves_the_previous_file_intact(users: UserStore, a_user: User):
    users.add(a_user)
    before = users.path.read_text()

    # Fail after the temporary file is opened but before the rename, which is
    # the window a plain write would have left truncated.
    with (
        patch("app.store.os.fsync", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        users.add(User(key="second", subject="s2"))

    assert users.path.read_text() == before
    assert users.load() == [a_user]


def test_a_failed_write_leaves_no_temporary_file_behind(users: UserStore, a_user: User):
    users.add(a_user)

    with patch("app.store.os.fsync", side_effect=OSError("disk full")), pytest.raises(OSError):
        users.add(User(key="second", subject="s2"))

    assert list(users.path.parent.glob("*.tmp")) == []


def test_the_file_is_json_a_person_can_read(users: UserStore, a_user: User):
    users.add(a_user)

    written = json.loads(users.path.read_text())

    assert written[0]["subject"] == "subject-ada"
    assert "\n" in users.path.read_text()


def test_seeding_writes_when_there_is_no_file(users: UserStore, a_user: User):
    assert users.seed([a_user]) is True
    assert users.load() == [a_user]


def test_seeding_never_overwrites_an_edit(users: UserStore, a_user: User):
    users.add(User(key="mine", subject="my-subject"))

    assert users.seed([a_user]) is False
    assert [u.key for u in users.load()] == ["mine"]


def test_roles_may_be_separated_by_commas_or_newlines():
    assert parse_list("admin, editor") == ["admin", "editor"]
    assert parse_list("admin\neditor") == ["admin", "editor"]
    assert parse_list("admin,\n editor,") == ["admin", "editor"]
    assert parse_list("  ") == []


def test_a_user_converts_to_the_library_fixture(a_user: User):
    persona = a_user.as_persona()

    assert persona.subject == a_user.subject
    assert persona.roles == ("admin",)
    assert persona.permissions == ("boards.write",)


def test_the_store_creates_its_directory(tmp_path: Path, a_user: User):
    store = UserStore(tmp_path / "missing" / "users.json")

    store.add(a_user)

    assert store.load() == [a_user]
