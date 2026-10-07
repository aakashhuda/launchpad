from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.web.router import web_router


def create_app() -> FastAPI:
    app = FastAPI(title="Launchpad Backend")
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(web_router)
    return app


app = create_app()
