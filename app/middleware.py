"""ASGI middleware."""

from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.log import request_id_var

REQUEST_ID_HEADER = b"x-request-id"


class RequestIdMiddleware:
    """Give every request an id, echo it in the response, and expose it to logging.

    An incoming ``X-Request-ID`` header is reused so ids stay stable across
    services; otherwise one is generated.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Wrap one request, tagging it with a request id."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope["headers"]).get(REQUEST_ID_HEADER)
        request_id = incoming.decode() if incoming else uuid4().hex
        token = request_id_var.set(request_id)

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"].append((REQUEST_ID_HEADER, request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id_var.reset(token)
