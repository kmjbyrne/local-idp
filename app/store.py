"""The user list, held as JSON on disk.

This is the whole reason the service exists. ``oidcutils.dev`` mints tokens for
a ``DevPersona`` tuple compiled into the application, so adding somebody to test
against means editing Python and restarting. Here the same records live in a
file that a web form writes, and every request reads them back.

JSON rather than a database on purpose. The file is meant to be opened, read and
edited by hand when the UI is not the quickest route, and a fixture that needed
migrations to add a test user would defeat its own point.
"""

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from oidcutils.dev import DevPersona


class StoreError(Exception):
    """The file on disk cannot be read back.

    Its own type because a hand-edited fixture file is expected to be wrong
    sometimes, and the service should say which file and why rather than
    failing as an unhandled decode error.
    """


def atomic_write(path: Path, payload: str) -> None:
    """Write ``payload`` to ``path``, replacing it in one step.

    Written to a temporary file and renamed, because a crash partway through a
    plain write leaves truncated JSON that the next read cannot parse. The
    rename is atomic within a directory, so a reader sees either the old file or
    the new one and never half of either. The temporary file is made in the same
    directory for that reason: a rename across filesystems is a copy, which is
    precisely what this avoids.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(payload)
            # Flushed to the platter before the rename. Without it the rename
            # can land while the contents are still buffered, which loses the
            # write on power failure rather than on a crash.
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class User:
    """Somebody the sign-in page offers, and the claims their token carries.

    ``subject`` is the load-bearing field. It becomes the token's ``sub`` claim,
    which is the only thing a service consuming these tokens knows a person by,
    so it is the join between this file and any database seeded alongside it.
    ``key`` is merely the handle the URLs use and may be renamed freely.
    """

    key: str
    subject: str
    name: str = ""
    email: str = ""
    purpose: str = ""
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)

    def as_persona(self) -> DevPersona:
        """Return the ``oidcutils`` fixture this record stands for.

        The conversion exists so signing stays in the library. This module owns
        storage and nothing else: it never builds a claim set or touches a key.
        """
        return DevPersona(
            key=self.key,
            subject=self.subject,
            name=self.name,
            email=self.email,
            purpose=self.purpose,
            roles=tuple(self.roles),
            permissions=tuple(self.permissions),
        )


def parse_list(text: str) -> list[str]:
    """Split a comma or newline separated field into its entries.

    Both separators are accepted because the admin form offers a textarea and
    people use whichever they reach for first. Blank entries are dropped, so a
    trailing comma does not become a role named "".
    """
    parts = text.replace("\n", ",").split(",")
    return [stripped for part in parts if (stripped := part.strip())]


class UserStore:
    """Reads and writes the user list, keeping the file whole.

    Every read goes to disk rather than to a cached copy. The file is small, and
    a cache would mean an edit made by hand did not show up until a restart,
    which is the behaviour this service was built to remove.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[User]:
        """Return the stored users, or an empty list if there is no file yet.

        :raises StoreError: if the file exists but cannot be read as a user
            list. Hand-editing is the point of this file, so a typo in it is an
            expected failure and worth naming rather than letting a
            ``JSONDecodeError`` surface as a 500.
        """
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text())
            return [User(**record) for record in raw]
        except (ValueError, TypeError) as exc:
            raise StoreError(f"{self.path} is not a readable user list: {exc}") from exc

    def save(self, users: list[User]) -> None:
        """Write ``users`` to disk, replacing the file in one step."""
        atomic_write(self.path, json.dumps([asdict(user) for user in users], indent=2) + "\n")

    def get(self, key: str) -> User | None:
        """Return the user handled by ``key``, or ``None``."""
        return next((user for user in self.load() if user.key == key), None)

    def add(self, user: User) -> User:
        """Store ``user``, refusing a key that is already taken.

        :raises ValueError: if a user with the same key exists.
        """
        users = self.load()
        if any(existing.key == user.key for existing in users):
            raise ValueError(f"A user with the key {user.key!r} already exists")
        users.append(user)
        self.save(users)
        return user

    def update(self, key: str, user: User) -> User:
        """Replace the user handled by ``key`` with ``user``.

        :raises ValueError: if no such user exists, or the new key is taken.
        """
        users = self.load()
        index = next((i for i, existing in enumerate(users) if existing.key == key), None)
        if index is None:
            raise ValueError(f"No user with the key {key!r}")
        if user.key != key and any(existing.key == user.key for existing in users):
            raise ValueError(f"A user with the key {user.key!r} already exists")
        users[index] = user
        self.save(users)
        return user

    def patch(self, key: str, /, **changes: object) -> User:
        """Apply ``changes`` to the user handled by ``key``.

        ``key`` is positional-only because ``key`` is also a field: taking it
        normally makes ``patch("ada", key="ada-k")`` a duplicate argument rather
        than a rename, which is the one edit most likely to be asked for.

        :raises ValueError: if no such user exists.
        """
        current = self.get(key)
        if current is None:
            raise ValueError(f"No user with the key {key!r}")
        return self.update(key, replace(current, **changes))  # type: ignore[arg-type]

    def delete(self, key: str) -> None:
        """Remove the user handled by ``key``.

        :raises ValueError: if no such user exists.
        """
        users = self.load()
        remaining = [user for user in users if user.key != key]
        if len(remaining) == len(users):
            raise ValueError(f"No user with the key {key!r}")
        self.save(remaining)

    def seed(self, users: list[User]) -> bool:
        """Write ``users`` only if the file does not exist yet.

        Returns whether it wrote. Guarded rather than merged because the file is
        somebody's working state: a seed that added back a user they deleted, or
        reset one they edited, would be a fixture fighting its owner.
        """
        if self.path.exists():
            return False
        self.save(users)
        return True
