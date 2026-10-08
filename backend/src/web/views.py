from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/", name="home")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"page_title": "Launchpad Backend"},
    )
