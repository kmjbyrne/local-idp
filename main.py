"""Entry point for the mock identity provider."""

import uvicorn

from app.config import settings
from app.factory import create_app

app = create_app(settings)

if __name__ == "__main__":
    # ruff: noqa: S104
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=True)
