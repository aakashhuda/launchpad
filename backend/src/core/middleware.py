"""Pure ASGI middleware that assigns and propagates a request correlation id.

A correlation id (incoming ``X-Request-Id`` or a generated one) is stored in
request-scoped context variables so it reaches every log line and audit row for
the request, and is echoed back on the response as ``X-Request-Id``. Implemented
as pure ASGI (not ``BaseHTTPMiddleware``) so the context variables set here are
visible to the endpoint and service layer.
"""

from __future__ import annotations

import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core import context
from src.core.config import settings


class CorrelationIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        correlation_id = headers.get(settings.correlation_id_header) or uuid.uuid4().hex
        tokens = (
            context.correlation_id_ctx.set(correlation_id),
            context.client_ip_ctx.set(self._client_ip(scope, headers)),
            context.user_agent_ctx.set(headers.get("user-agent")),
        )

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[settings.correlation_id_header] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            context.correlation_id_ctx.reset(tokens[0])
            context.client_ip_ctx.reset(tokens[1])
            context.user_agent_ctx.reset(tokens[2])

    @staticmethod
    def _client_ip(scope: Scope, headers: Headers) -> str | None:
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = scope.get("client")
        if client:
            return client[0]
        return None
