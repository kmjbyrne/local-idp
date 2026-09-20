"""The admin UI: server-rendered forms over the two JSON files.

Jinja templates in ``templates/`` and stylesheets in ``static/``. No JavaScript,
no build step, no framework. Forms post and the page reloads, which is enough
for a fixture somebody visits to add a test user.

No authentication either, deliberately. Putting a login in front of a service
whose whole purpose is handing out tokens for people who do not exist would
protect nothing and would be one more thing to get past. It is bound to a
development machine instead, which is the only place it belongs.
"""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.clients import Client, ClientStore
from app.store import User, UserStore, parse_list
from app.templating import templates


def create_admin_router(users: UserStore, clients: ClientStore) -> APIRouter:
    """Return the router serving the admin pages."""
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        """List the users and clients, with a form to add one of each."""
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "users": users.load(),
                "clients": clients.load(),
                "stylesheet": "/static/admin.css",
            },
        )

    @router.post("/users")
    async def create_user(
        key: Annotated[str, Form()],
        subject: Annotated[str, Form()],
        name: Annotated[str, Form()] = "",
        email: Annotated[str, Form()] = "",
        purpose: Annotated[str, Form()] = "",
        roles: Annotated[str, Form()] = "",
        permissions: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Add a user from the form on the index page."""
        if not key.strip() or not subject.strip():
            raise HTTPException(400, "A user needs a key and a subject")
        try:
            users.add(
                User(
                    key=key.strip(),
                    subject=subject.strip(),
                    name=name.strip(),
                    email=email.strip(),
                    purpose=purpose.strip(),
                    roles=parse_list(roles),
                    permissions=parse_list(permissions),
                )
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse("/", status_code=303)

    @router.get("/users/{key}", response_class=HTMLResponse)
    async def edit_user(request: Request, key: str) -> HTMLResponse:
        """Show the form for one user."""
        user = users.get(key)
        if user is None:
            raise HTTPException(404, f"No user with the key {key!r}")
        return templates.TemplateResponse(
            request,
            "edit_user.html",
            {"user": user, "stylesheet": "/static/admin.css"},
        )

    @router.post("/users/{key}")
    async def save_user(
        key: str,
        subject: Annotated[str, Form()],
        new_key: Annotated[str, Form(alias="key")],
        name: Annotated[str, Form()] = "",
        email: Annotated[str, Form()] = "",
        purpose: Annotated[str, Form()] = "",
        roles: Annotated[str, Form()] = "",
        permissions: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Save the edited user."""
        try:
            users.update(
                key,
                User(
                    key=(new_key or key).strip(),
                    subject=subject.strip(),
                    name=name.strip(),
                    email=email.strip(),
                    purpose=purpose.strip(),
                    roles=parse_list(roles),
                    permissions=parse_list(permissions),
                ),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse("/", status_code=303)

    @router.post("/users/{key}/delete")
    async def delete_user(key: str) -> RedirectResponse:
        """Remove a user."""
        try:
            users.delete(key)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return RedirectResponse("/", status_code=303)

    @router.post("/clients")
    async def create_client(
        client_id: Annotated[str, Form()],
        client_secret: Annotated[str, Form()] = "",
        name: Annotated[str, Form()] = "",
        redirect_uris: Annotated[str, Form()] = "",
        enforce_secret: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Register a client from the form on the index page."""
        if not client_id.strip():
            raise HTTPException(400, "A client needs an id")
        try:
            clients.add(
                Client(
                    client_id=client_id.strip(),
                    client_secret=client_secret.strip(),
                    name=name.strip(),
                    redirect_uris=parse_list(redirect_uris),
                    enforce_secret=enforce_secret == "true",
                )
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse("/", status_code=303)

    @router.post("/clients/{client_id}/delete")
    async def delete_client(client_id: str) -> RedirectResponse:
        """Remove a client."""
        try:
            clients.delete(client_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return RedirectResponse("/", status_code=303)

    return router
