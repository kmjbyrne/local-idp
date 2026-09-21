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

Authorization codes are managed here rather than in ``oidcutils.dev``, because
the library's ``issue_code``/``redeem_code`` do not carry ``scope`` or
``nonce``, both of which OIDC requires for the ``id_token``.

See ``app.keys`` for signing.
"""

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from joserfc import jwt
from joserfc.jwk import KeySet

from app.clients import ClientStore
from app.config import Settings
from app.keys import Keyring
from app.store import User, UserStore
from app.templating import templates

CODE_LIFETIME = 300
_codes: dict[str, dict[str, Any]] = {}


def _issue_code(
    user: User,
    redirect_uri: str,
    *,
    scope: str = "",
    nonce: str = "",
) -> str:
    """Issue an authorization code carrying the user's claims and OIDC params."""
    code = secrets.token_urlsafe(24)
    _codes[code] = {
        "subject": user.subject,
        "name": user.name,
        "email": user.email,
        "roles": list(user.roles),
        "permissions": list(user.permissions),
        "redirect_uri": redirect_uri,
        "scope": scope,
        "nonce": nonce,
        "expires_at": time.time() + CODE_LIFETIME,
    }
    return code


def _redeem_code(code: str) -> dict[str, Any] | None:
    """Return the claims a code stands for, or None. Single use."""
    claims = _codes.pop(code, None)
    if claims is None:
        return None
    if claims["expires_at"] < time.time():
        return None
    return claims


def _at_hash(access_token: str, alg: str) -> str:
    """Compute the at_hash claim per OIDC Core 3.1.3.6."""
    if alg.endswith("384"):
        digest = hashlib.sha384(access_token.encode()).digest()
    elif alg.endswith("512"):
        digest = hashlib.sha512(access_token.encode()).digest()
    else:
        digest = hashlib.sha256(access_token.encode()).digest()
    half = digest[: len(digest) // 2]
    return base64.urlsafe_b64encode(half).rstrip(b"=").decode()


def _parse_scopes(scope: str) -> set[str]:
    return set(scope.split()) if scope else set()


def create_oidc_router(
    settings: Settings, users: UserStore, clients: ClientStore, keyring: Keyring
) -> APIRouter:
    """Return the router serving the provider endpoints."""
    router = APIRouter()

    @router.get("/.well-known/openid-configuration")
    async def discovery() -> dict[str, Any]:
        """Return the OIDC discovery document."""
        issuer = settings.ISSUER
        return {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/dev/authorize",
            "token_endpoint": f"{issuer}/dev/token",
            "userinfo_endpoint": f"{issuer}/dev/userinfo",
            "jwks_uri": f"{issuer}/.well-known/jwks.json",
            "scopes_supported": ["openid", "profile", "email"],
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["ES256", "ES384", "RS256"],
            "claims_supported": [
                "sub", "iss", "aud", "exp", "iat", "name", "email",
                "nonce", "at_hash", "auth_time",
            ],
        }

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
        scope: str = "",
        nonce: str = "",
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
            code = _issue_code(chosen, redirect_uri, scope=scope, nonce=nonce)
            separator = "&" if "?" in redirect_uri else "?"
            location = f"{redirect_uri}{separator}code={code}"
            if state:
                location = f"{location}&state={state}"
            return RedirectResponse(location, status_code=303)

        return templates.TemplateResponse(
            request,
            "signin.html",
            {
                "users": [_offer(u, redirect_uri, state, client_id, scope, nonce) for u in offered],
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
            body = (await request.body()).decode()
            form = {key: value[0] for key, value in parse_qs(body).items()}
            grant = form.get("grant_type", "")

            if grant != "authorization_code":
                raise HTTPException(400, f"Unsupported grant_type: {grant}")

            _check_credentials(clients, form, request)

            claims = _redeem_code(form.get("code", ""))
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
                scope=claims.get("scope", ""),
                nonce=claims.get("nonce", ""),
            )

        payload = await request.json() if await request.body() else {}

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

    @router.get("/dev/userinfo")
    async def userinfo(request: Request) -> JSONResponse:
        """Return claims for the bearer token.

        OIDC Core 5.3. The access token arrives as a Bearer header. Claims are
        read from the token itself, since this provider mints self-contained
        JWTs.
        """
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise HTTPException(401, "Bearer token required")

        token_str = auth[7:]
        try:
            key_set = KeySet.import_key_set(keyring.public_jwks())
            decoded = jwt.decode(token_str, key_set)
            claims = decoded.claims
        except Exception:
            raise HTTPException(401, "Invalid or expired token")

        return JSONResponse({
            "sub": claims.get("sub"),
            "name": claims.get("name"),
            "email": claims.get("email"),
            "roles": claims.get("roles", []),
            "permissions": claims.get("permissions", []),
        })

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
    scope: str = "",
    nonce: str = "",
) -> dict[str, Any]:
    """Return the token response.

    When scope includes ``openid``, an ``id_token`` is included per OIDC Core
    3.1.3.3. The access token is always a signed JWT with the same claims,
    which is what most real providers do and what lets ``/dev/userinfo`` work
    without a database lookup.
    """
    access_claims: dict[str, Any] = {
        "iss": settings.ISSUER,
        "aud": settings.AUDIENCE,
        "sub": subject,
        "email": email,
        "name": name,
        "roles": roles or [],
        "permissions": permissions or [],
    }
    if extra_claims:
        access_claims.update(extra_claims)

    seconds = lifetime if lifetime is not None else settings.TOKEN_LIFETIME
    access_token = keyring.mint(access_claims, lifetime=seconds)

    response: dict[str, Any] = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": seconds,
        "refresh_token": secrets.token_urlsafe(32),
    }

    scopes = _parse_scopes(scope)
    if "openid" in scopes:
        id_claims: dict[str, Any] = {
            "iss": settings.ISSUER,
            "aud": settings.AUDIENCE,
            "sub": subject,
            "auth_time": int(time.time()),
            "at_hash": _at_hash(access_token, "ES256"),
        }
        if nonce:
            id_claims["nonce"] = nonce
        if "profile" in scopes:
            id_claims["name"] = name
        if "email" in scopes:
            id_claims["email"] = email
        response["id_token"] = keyring.mint(id_claims, lifetime=seconds)

    return response


def _offer(
    user: User, redirect_uri: str, state: str, client_id: str,
    scope: str, nonce: str,
) -> dict[str, Any]:
    """Return what the sign-in template needs to render one choice."""
    params: dict[str, str] = {"redirect_uri": redirect_uri, "persona": user.key}
    if state:
        params["state"] = state
    if client_id:
        params["client_id"] = client_id
    if scope:
        params["scope"] = scope
    if nonce:
        params["nonce"] = nonce
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
