"""Builds the application."""

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.admin import create_admin_router
from app.api import create_api_router
from app.clients import ClientStore
from app.config import Settings
from app.keys import Keyring
from app.log import configure_logging
from app.middleware import RequestIdMiddleware
from app.oidc import create_oidc_router
from app.seed import CLIENTS, USERS
from app.store import StoreError, UserStore
from app.templating import STATIC_DIR


def create_app(settings: Settings) -> FastAPI:
    """Create the provider, seeding it on a first run.

    Seeding is guarded on the file not existing rather than merged into it. The
    file is somebody's working state, and a seed that added back a user they
    deleted would be a fixture fighting its owner.
    """
    configure_logging(settings)

    users = UserStore(settings.users_path)
    clients = ClientStore(settings.clients_path)
    users.seed(list(USERS))
    clients.seed(list(CLIENTS))

    # Loaded, not generated. A key that changed on every restart would break a
    # client holding a cached JWKS, and the failure reads as a signature error
    # rather than as a restart.
    keyring = Keyring(settings.keys_path)
    keyring.load()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
    )
    app.state.users = users
    app.state.clients = clients
    app.state.keyring = keyring

    @app.exception_handler(StoreError)
    async def store_corrupt(request: Request, exc: StoreError) -> JSONResponse:  # noqa: ARG001
        """Answer 503 when a file on disk cannot be read.

        Not a 500. The service is working; the file it was pointed at is not,
        and the caller can fix that once it is told which file and why.
        """
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health")
    def health_check(response: Response) -> dict:
        """Report liveness, and whether the stored files can be read.

        The files are the service's only state, so a read that raises is the
        one failure worth reporting: unreadable JSON means every sign-in fails,
        and it is better said here than discovered mid-flow.
        """
        try:
            counts = {
                "users": len(users.load()),
                "clients": len(clients.load()),
                "keys": len(keyring.keys),
            }
        except (OSError, ValueError, StoreError) as exc:
            response.status_code = 503
            return {"status": False, "error": str(exc)}
        return {"status": True, **counts}

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(create_oidc_router(settings, users, clients, keyring))
    app.include_router(create_api_router(users, clients, keyring))
    app.include_router(create_admin_router(users, clients))

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return app
