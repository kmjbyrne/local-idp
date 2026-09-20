"""Logging setup.

Everything goes to stdout. Containers and process supervisors collect it from
there; log files inside a container disappear with it.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from app.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"


class RequestIdFilter(logging.Filter):
    """Attach the current request id to every record so formatters can print it."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Annotate the record with the request id and pass it through."""
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for log collectors that parse structured output."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record as a JSON line."""
        payload = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(settings: Settings) -> None:
    """Route all loggers, uvicorn's included, through one stdout handler."""
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter() if settings.LOG_JSON else logging.Formatter(TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())

    # uvicorn installs its own handlers before the app is imported. Strip them so
    # access and error lines share the root format instead of printing twice.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True

    # Alembic announces each autogenerate plugin at INFO on every boot.
    logging.getLogger("alembic.runtime.plugins").setLevel(logging.WARNING)
