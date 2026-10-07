from fastapi import APIRouter

from app.web.views import router as views_router

web_router = APIRouter(include_in_schema=False)
web_router.include_router(views_router)
