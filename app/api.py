"""The JSON API over the same two files the admin UI edits.

So a script can add a user without driving a form, and so a service can read
the list rather than duplicating it.
"""

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.clients import Client, ClientStore
from app.keys import Keyring
from app.store import User, UserStore


class UserPayload(BaseModel):
    """A user as the API accepts it."""

    key: str
    subject: str
    name: str = ""
    email: str = ""
    purpose: str = ""
    roles: list[str] = []
    permissions: list[str] = []


class UserPatch(BaseModel):
    """The fields a PATCH may change. Anything omitted is left alone."""

    key: str | None = None
    subject: str | None = None
    name: str | None = None
    email: str | None = None
    purpose: str | None = None
    roles: list[str] | None = None
    permissions: list[str] | None = None


class KeyRequest(BaseModel):
    """A request to add a key."""

    algorithm: str = "ES256"
    # False adds the key without signing with it, so a client's cache can be
    # warmed before the cutover. That is the half of a rotation that is easy to
    # get wrong and hard to reproduce against a real provider.
    make_active: bool = True


class ClientPayload(BaseModel):
    """A client as the API accepts it."""

    client_id: str
    client_secret: str = ""
    name: str = ""
    redirect_uris: list[str] = []
    enforce_secret: bool = True


def create_api_router(users: UserStore, clients: ClientStore, keyring: Keyring) -> APIRouter:
    """Return the router serving the JSON API."""
    router = APIRouter(prefix="/api")

    @router.get("/users")
    async def list_users() -> list[dict[str, Any]]:
        """Return every stored user."""
        return [asdict(user) for user in users.load()]

    @router.get("/users/{key}")
    async def get_user(key: str) -> dict[str, Any]:
        """Return one user."""
        user = users.get(key)
        if user is None:
            raise HTTPException(404, f"No user with the key {key!r}")
        return asdict(user)

    @router.post("/users", status_code=201)
    async def add_user(payload: UserPayload) -> dict[str, Any]:
        """Store a new user."""
        try:
            return asdict(users.add(User(**payload.model_dump())))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.patch("/users/{key}")
    async def patch_user(key: str, payload: UserPatch) -> dict[str, Any]:
        """Change some fields of a user."""
        changes = payload.model_dump(exclude_none=True)
        try:
            return asdict(users.patch(key, **changes))
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.delete("/users/{key}", status_code=204)
    async def remove_user(key: str) -> None:
        """Remove a user."""
        try:
            users.delete(key)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/clients")
    async def list_clients() -> list[dict[str, Any]]:
        """Return every registered client, secrets included.

        The secrets are returned because this is a fixture and somebody reading
        the list is trying to configure a service against it. A real provider
        would never do this.
        """
        return [asdict(client) for client in clients.load()]

    @router.post("/clients", status_code=201)
    async def add_client(payload: ClientPayload) -> dict[str, Any]:
        """Register a new client."""
        try:
            return asdict(clients.add(Client(**payload.model_dump())))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.delete("/clients/{client_id}", status_code=204)
    async def remove_client(client_id: str) -> None:
        """Remove a client."""
        try:
            clients.delete(client_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/keys")
    async def list_keys() -> dict[str, Any]:
        """Return the published keys and which one is signing.

        Public halves only. The private half is on disk and stays there.
        """
        return {
            "active": keyring.active_kid,
            "keys": keyring.public_jwks()["keys"],
        }

    @router.post("/keys", status_code=201)
    async def add_key(payload: KeyRequest) -> dict[str, Any]:
        """Add a key, optionally rotating onto it."""
        if payload.algorithm not in ("ES256", "ES384", "ES512", "RS256"):
            raise HTTPException(400, f"Unsupported algorithm: {payload.algorithm}")
        kid = keyring.generate(algorithm=payload.algorithm, make_active=payload.make_active)
        return {"kid": kid, "active": keyring.active_kid}

    @router.post("/keys/{kid}/activate")
    async def activate_key(kid: str) -> dict[str, Any]:
        """Sign with ``kid`` from now on, leaving the others published."""
        try:
            keyring.activate(kid)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"active": keyring.active_kid}

    @router.delete("/keys/{kid}", status_code=204)
    async def remove_key(kid: str) -> None:
        """Retire a key, so tokens it signed stop verifying."""
        try:
            keyring.retire(kid)
        except ValueError as exc:
            status = 409 if "active" in str(exc) else 404
            raise HTTPException(status, str(exc)) from exc

    return router
