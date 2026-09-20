"""The OIDC surface: discovery, keys, the sign-in page and the token endpoint.

Shaped to match ``oidcutils.contrib.fastapi.create_dev_router`` so a service
already pointing at that provider reaches this one without a code change. The
paths, the form fields and the JSON body are the same.

Three things are deliberately different, and each is a reason the service exists.
The sign-in page lists whoever is in ``users.json`` rather than a tuple compiled
into the application. The token endpoint checks the client credentials it is
given, which the library's provider does not do at all. And tokens are signed
from a keyring on disk, so a restart does not invalidate every token and several
keys can be published at once.

The code exchange and the discovery document are still ``oidcutils.dev``.
Signing is not: ``mint_token`` writes a fixed ``kid`` and ``public_jwks``
publishes one key, and neither can express a rotation. See ``app.keys``.
"""

import base64
import secrets
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from oidcutils.dev import discovery_document, issue_code, redeem_code

from app.clients import ClientStore
from app.config import Settings
from app.keys import Keyring
from app.store import User, UserStore
from app.templating import templates


def create_oidc_router(
    settings: Settings, users: UserStore, clients: ClientStore, keyring: Keyring
) -> APIRouter:
    """Return the router serving the provider endpoints."""
    router = APIRouter()

    @router.get("/.well-known/openid-configuration")
    async def discovery() -> dict[str, Any]:
        """Return the discovery document clients read to find the endpoints."""
        return discovery_document(settings.ISSUER)

    @router.get("/.well-known/jwks.json")
    async def jwks() -> dict[str, Any]:
        """Return every published key, so a rotated-away token still verifies."""
        return keyring.public_jwks()

    @router.get("/dev/authorize", response_class=HTMLResponse)
    async def authorize(
        request: Request,
        redirect_uri: str,
        state: str = "",
        persona: str = "",
        client_id: str = "",
    ) -> Any:
        """Offer the stored users, or redirect back with a code for the one picked.

        ``client_id`` is checked here as well as at the token endpoint, because
        a real provider refuses an unknown client before showing a sign-in page
        rather than after collecting a credential. It stays optional so a caller
        that sends none behaves as the library's provider did.
        """
        if client_id:
            registered = clients.get(client_id)
            if registered is None:
                raise HTTPException(400, f"Unknown client_id: {client_id}")
            if not registered.redirect_allowed(redirect_uri):
                raise HTTPException(400, f"redirect_uri is not registered: {redirect_uri}")

        offered = users.load()
        if not offered:
            raise HTTPException(
                404,
                "No users stored. Add one at / before signing in.",
            )

        if persona:
            chosen = users.get(persona)
            if chosen is None:
                raise HTTPException(400, f"Unknown persona: {persona}")
            code = issue_code(chosen.as_persona(), redirect_uri)
            separator = "&" if "?" in redirect_uri else "?"
            location = f"{redirect_uri}{separator}code={code}"
            if state:
                location = f"{location}&state={state}"
            return RedirectResponse(location, status_code=303)

        return templates.TemplateResponse(
            request,
            "signin.html",
            {
                "users": [_offer(u, redirect_uri, state, client_id) for u in offered],
                "stylesheet": "/static/signin.css",
            },
        )

    @router.post("/dev/token")
    async def token(request: Request) -> dict[str, Any]:
        """Mint a token, from a code or from claims given directly.

        Two shapes, because two callers. An OAuth2 client posts a form carrying
        a code and its credentials, which is the path a browser login takes. A
        test posts JSON saying who to be, which needs no browser and no code.
        """
        content_type = request.headers.get("content-type", "")

        if "application/x-www-form-urlencoded" in content_type:
            # Parsed by hand rather than with request.form(), which needs
            # python-multipart. That dependency exists for file uploads, and
            # pulling it in to read five fields is not worth it.
            body = (await request.body()).decode()
            form = {key: value[0] for key, value in parse_qs(body).items()}
            grant = form.get("grant_type", "")

            if grant != "authorization_code":
                raise HTTPException(400, f"Unsupported grant_type: {grant}")

            _check_credentials(clients, form, request)

            claims = redeem_code(form.get("code", ""))
            if claims is None:
                raise HTTPException(400, "Invalid or expired authorization code")

            return _token_response(
                keyring,
                settings,
                subject=claims["subject"],
                name=claims["name"],
                email=claims["email"],
                roles=claims["roles"],
                permissions=claims["permissions"],
            )

        payload = await request.json() if await request.body() else {}

        # A subject names a stored user, so a test gets that user's roles
        # without repeating them. Anything else is passed through as the
        # library's provider does, which is what a test wanting a claim nobody
        # is stored with relies on.
        subject = payload.get("subject")
        if subject and not payload.get("roles") and not payload.get("permissions"):
            stored = next((u for u in users.load() if u.subject == subject), None)
            if stored is not None:
                payload = {
                    "subject": stored.subject,
                    "name": stored.name,
                    "email": stored.email,
                    "roles": list(stored.roles),
                    "permissions": list(stored.permissions),
                    **{k: v for k, v in payload.items() if k != "subject"},
                }

        return _token_response(keyring, settings, **payload)

    return router


def _check_credentials(clients: ClientStore, form: dict[str, str], request: Request) -> None:
    """Reject the exchange unless it carries a registered client's credentials.

    The check ``oidcutils`` does not do, and the reason a service configured
    with the wrong secret can fail here rather than in staging.

    Credentials may arrive in the form or in a Basic auth header, because
    RFC 6749 allows both and which one a client uses is not something this
    provider should dictate.

    An empty registry accepts anything. A first run has no clients, and
    refusing every exchange until somebody registers one would make the service
    look broken rather than unconfigured.
    """
    registered = clients.load()
    if not registered:
        return

    client_id = form.get("client_id", "")
    client_secret = form.get("client_secret", "")

    if not client_id:
        client_id, client_secret = _basic_auth(request) or ("", "")

    if not client_id:
        raise HTTPException(401, "invalid_client: no client_id presented")

    client = clients.get(client_id)
    if client is None:
        raise HTTPException(401, f"invalid_client: unknown client_id {client_id}")

    if not client.secret_matches(client_secret):
        raise HTTPException(401, "invalid_client: client_secret does not match")

    redirect_uri = form.get("redirect_uri", "")
    if redirect_uri and not client.redirect_allowed(redirect_uri):
        raise HTTPException(400, f"invalid_grant: redirect_uri is not registered: {redirect_uri}")


def _token_response(
    keyring: Keyring,
    settings: Settings,
    *,
    subject: str = "dev-user",
    name: str = "Dev User",
    email: str = "dev@localhost",
    roles: list[str] | None = None,
    permissions: list[str] | None = None,
    lifetime: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the token response an OAuth2 client expects.

    The same shape ``oidcutils.dev.mint_token`` returns, so a client cannot tell
    the two apart. It is built here rather than called there because that
    function writes a constant ``kid`` into the header, and a provider holding
    several keys has to say which one signed.
    """
    claims: dict[str, Any] = {
        "iss": settings.ISSUER,
        "aud": settings.AUDIENCE,
        "sub": subject,
        "email": email,
        "name": name,
        "roles": roles or [],
        "permissions": permissions or [],
    }
    if extra_claims:
        claims.update(extra_claims)

    seconds = lifetime if lifetime is not None else settings.TOKEN_LIFETIME
    return {
        "access_token": keyring.mint(claims, lifetime=seconds),
        "token_type": "Bearer",
        "expires_in": seconds,
        "refresh_token": secrets.token_urlsafe(32),
    }


def _offer(user: User, redirect_uri: str, state: str, client_id: str) -> dict[str, Any]:
    """Return what the sign-in template needs to render one choice.

    The query string is built here rather than in the template, because getting
    the encoding wrong is how a redirect_uri holding its own query ends up
    truncated, and urlencode is not something Jinja should be asked to do.
    """
    params = {"redirect_uri": redirect_uri, "persona": user.key}
    if state:
        params["state"] = state
    if client_id:
        params["client_id"] = client_id
    return {
        "key": user.key,
        "name": user.name,
        "email": user.email,
        "subject": user.subject,
        "purpose": user.purpose,
        "roles": user.roles,
        "query": urlencode(params),
    }


def _basic_auth(request: Request) -> tuple[str, str] | None:
    """Return the credentials from a Basic auth header, if there is one."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        return None
    try:
        decoded = base64.b64decode(header[6:]).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    client_id, _, client_secret = decoded.partition(":")
    return client_id, client_secret
