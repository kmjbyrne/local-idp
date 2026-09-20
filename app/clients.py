"""Registered OAuth2 clients, held as JSON on disk.

The reason this service exists rather than ``oidcutils.dev`` alone. That
provider mints a token for anybody who posts a code: its token endpoint reads
``grant_type`` and ``code`` and nothing else, and ``mount_dev`` generates a
random secret when none is passed because nothing ever compares one. A wrong
``OIDC_CLIENT_SECRET`` therefore cannot fail locally, and first fails against
the real identity server.

A client registered here is checked. Posting the wrong secret is rejected the
way a real provider rejects it, so the backend's credential configuration is
exercised before it reaches somewhere that matters.
"""

import hmac
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.store import StoreError, atomic_write


@dataclass(frozen=True)
class Client:
    """An application allowed to exchange codes for tokens.

    ``enforce_secret`` exists because the flow this service replaces did not
    check secrets at all. Left on, a client behaves as a real provider's would.
    Turned off, it accepts any secret, which is how an existing caller that was
    never sending a correct one keeps working while it is being fixed.

    ``redirect_uris`` empty means any redirect is accepted. A real provider
    compares the value as a string against a registered list, and getting that
    wrong is a common misconfiguration, so it is worth being able to reproduce.
    """

    client_id: str
    client_secret: str = ""
    name: str = ""
    redirect_uris: list[str] = field(default_factory=list)
    enforce_secret: bool = True

    def secret_matches(self, presented: str) -> bool:
        """Report whether ``presented`` is this client's secret.

        Compared with :func:`hmac.compare_digest` rather than ``==``. The
        comparison is not guarding anything here, since the service hands out
        tokens for people who do not exist, but a credential check copied out
        of a fixture and into something real is a way a timing leak travels.
        """
        if not self.enforce_secret:
            return True
        return hmac.compare_digest(self.client_secret, presented)

    def redirect_allowed(self, redirect_uri: str) -> bool:
        """Report whether ``redirect_uri`` is one this client registered."""
        if not self.redirect_uris:
            return True
        return redirect_uri in self.redirect_uris


class ClientStore:
    """Reads and writes the client registry.

    Read from disk per call, like the user store, so an edit made by hand takes
    effect without a restart.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[Client]:
        """Return the registered clients, or an empty list if there is no file.

        :raises StoreError: if the file exists but cannot be read.
        """
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text())
            return [Client(**record) for record in raw]
        except (ValueError, TypeError) as exc:
            raise StoreError(f"{self.path} is not a readable client list: {exc}") from exc

    def save(self, clients: list[Client]) -> None:
        """Write ``clients`` to disk, replacing the file in one step."""
        atomic_write(self.path, json.dumps([asdict(c) for c in clients], indent=2) + "\n")

    def get(self, client_id: str) -> Client | None:
        """Return the client registered as ``client_id``, or ``None``."""
        return next((c for c in self.load() if c.client_id == client_id), None)

    def add(self, client: Client) -> Client:
        """Register ``client``.

        :raises ValueError: if the client id is already registered.
        """
        clients = self.load()
        if any(c.client_id == client.client_id for c in clients):
            raise ValueError(f"A client with the id {client.client_id!r} already exists")
        clients.append(client)
        self.save(clients)
        return client

    def update(self, client_id: str, client: Client) -> Client:
        """Replace the client registered as ``client_id``.

        :raises ValueError: if no such client exists, or the new id is taken.
        """
        clients = self.load()
        index = next((i for i, c in enumerate(clients) if c.client_id == client_id), None)
        if index is None:
            raise ValueError(f"No client with the id {client_id!r}")
        if client.client_id != client_id and any(c.client_id == client.client_id for c in clients):
            raise ValueError(f"A client with the id {client.client_id!r} already exists")
        clients[index] = client
        self.save(clients)
        return client

    def delete(self, client_id: str) -> None:
        """Remove the client registered as ``client_id``.

        :raises ValueError: if no such client exists.
        """
        clients = self.load()
        remaining = [c for c in clients if c.client_id != client_id]
        if len(remaining) == len(clients):
            raise ValueError(f"No client with the id {client_id!r}")
        self.save(remaining)

    def seed(self, clients: list[Client]) -> bool:
        """Write ``clients`` only if the file does not exist yet."""
        if self.path.exists():
            return False
        self.save(clients)
        return True
