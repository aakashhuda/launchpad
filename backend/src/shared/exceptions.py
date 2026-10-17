"""Global API exception handlers.

Server-side failures are logged (with the request correlation id) and returned
as a generic message — internal details are never leaked to clients. Client
errors (``HTTPException``, validation errors) keep their own semantics via
FastAPI's default handlers.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.context import get_correlation_id

logger = logging.getLogger("src.shared.exceptions")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        correlation_id = get_correlation_id()
        logger.exception(
            "Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc
        )
        headers = {"X-Request-Id": correlation_id} if correlation_id else None
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=headers,
        )
