"""Service configuration."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


class Settings(BaseSettings):
    """Settings for the mock identity provider.

    Real environment variables always win. Below those, env files are read in
    increasing order of precedence: ``.env``, ``.env.local``, then
    ``.env.{ENVIRONMENT}``. Missing files are skipped.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", f".env.{_ENVIRONMENT}"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    PROJECT_NAME: str = "Mock IdP"
    VERSION: str = "26.9.0"
    DESCRIPTION: str = "An editable identity provider for local development"

    # The address this provider answers on, and the value it writes as the
    # token's `iss` claim. A client fetches discovery from here and compares the
    # issuer it gets back, so a mismatch between this and the URL actually used
    # fails validation in a way that reads like a key problem.
    ISSUER: str = "http://localhost:9000"
    AUDIENCE: str = "dev"

    # Where the editable state lives. A directory rather than two file paths,
    # because it is bind mounted as a unit and is the thing somebody inspects.
    INSTANCE_DIR: Path = Path("instance")

    # How long a minted token lasts. Short enough that an expiry can be watched
    # without waiting an hour, long enough not to expire mid-click.
    TOKEN_LIFETIME: int = 3600

    # Origins the admin API answers cross-origin. A UI reads the user list from
    # a browser, and it asks this service directly rather than through the
    # resource server: a resource server validates tokens and serves resources,
    # and never answers "here are my users", so a route through it would be a
    # development path with nothing behind it in production.
    #
    # Both dev origins by default: the UI's own port, and the proxy the stack
    # serves everything behind. Credentials are enabled, and browsers reject a
    # credentialed response carrying a wildcard, so these are listed explicitly.
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "https://127.0.0.1.nip.io",
    ]

    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    @property
    def users_path(self) -> Path:
        """Return the file holding the user list."""
        return self.INSTANCE_DIR / "users.json"

    @property
    def clients_path(self) -> Path:
        """Return the file holding the client registry."""
        return self.INSTANCE_DIR / "clients.json"

    @property
    def keys_path(self) -> Path:
        """Return the file holding the signing keys.

        Private halves live here, which is why instance/ is gitignored.
        """
        return self.INSTANCE_DIR / "keys.json"


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once."""
    return Settings()


settings = get_settings()
