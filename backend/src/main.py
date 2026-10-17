from pathlib import Path

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.auth.router import router as auth_router
from src.community.router import router as community_router
from src.core.config import settings
from src.core.constants import API_V1_PREFIX
from src.core.database import get_db
from src.core.logging import configure_logging
from src.core.middleware import CorrelationIdMiddleware
from src.discovery import jobs as discovery_jobs  # noqa: F401  (register discovery jobs)
from src.discovery.router import router as discovery_router
from src.integrations.redis import get_redis_client
from src.notifications import jobs as notifications_jobs  # noqa: F401  (register notification jobs)
from src.notifications.router import router as notifications_router
from src.products import jobs as products_jobs  # noqa: F401  (register product jobs)
from src.products.router import router as products_router
from src.shared import registry  # noqa: F401  (load all mappers)
from src.shared.exceptions import register_exception_handlers
from src.staff import jobs as staff_jobs  # noqa: F401  (register staff jobs)
from src.staff.router import router as staff_router
from src.topics.router import router as topics_router
from src.users.router import router as users_router
from src.web.router import web_router


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.add_middleware(CorrelationIdMiddleware)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
        name="static",
    )
    register_exception_handlers(app)

    prefix = API_V1_PREFIX
    app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["auth"])
    app.include_router(users_router, prefix=f"{prefix}/users", tags=["users"])
    app.include_router(products_router, prefix=f"{prefix}/products", tags=["products"])
    app.include_router(community_router, prefix=f"{prefix}/community", tags=["community"])
    app.include_router(topics_router, prefix=f"{prefix}/topics", tags=["topics"])
    app.include_router(discovery_router, prefix=f"{prefix}/discovery", tags=["discovery"])
    app.include_router(
        notifications_router, prefix=f"{prefix}/notifications", tags=["notifications"]
    )
    app.include_router(staff_router, prefix=f"{prefix}/staff", tags=["staff"])

    @app.get(f"{prefix}/health", tags=["health"])
    def health_check():
        return {"status": "ok"}

    @app.get(f"{prefix}/health/ready", tags=["health"])
    def readiness_check(db: Session = Depends(get_db)) -> JSONResponse:
        """Readiness probe: report DB + Redis connectivity.

        The database is authoritative, so an unreachable DB is a hard 503.
        Redis backs cache/queue/rate-limit only, so an unreachable Redis
        degrades readiness without failing it.
        """
        components: dict[str, str] = {}
        try:
            db.execute(text("SELECT 1"))
            components["database"] = "ok"
        except Exception:
            components["database"] = "unavailable"
        try:
            get_redis_client().ping()
            components["redis"] = "ok"
        except Exception:
            components["redis"] = "unavailable"

        if components["database"] != "ok":
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable", **components},
            )
        overall = "ok" if components["redis"] == "ok" else "degraded"
        return JSONResponse(
            status_code=status.HTTP_200_OK, content={"status": overall, **components}
        )

    app.include_router(web_router)
    return app


app = create_app()
