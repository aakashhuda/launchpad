"""Request-scoped context propagated via context variables.

The correlation-id middleware populates these once per request; services read
them (e.g. ``AuditLogService.record``) so audit rows and log lines can be tied
back to the originating request without threading a ``Request`` through every
service signature. Outside a request (background jobs) the values are ``None``.
"""

from __future__ import annotations

from contextvars import ContextVar

correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)
client_ip_ctx: ContextVar[str | None] = ContextVar("client_ip", default=None)
user_agent_ctx: ContextVar[str | None] = ContextVar("user_agent", default=None)


def get_correlation_id() -> str | None:
    return correlation_id_ctx.get()


def get_client_ip() -> str | None:
    return client_ip_ctx.get()


def get_user_agent() -> str | None:
    return user_agent_ctx.get()
