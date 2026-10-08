from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.files import router as files_router

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Geospatial File Measurement API",
    version="1.0.0",
    description=(
        "Upload KML or ZIP Shapefiles, extract geospatial features, "
        "and calculate CRS-safe area and length measurements."
    ),
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.include_router(files_router)


@app.get("/", include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={},
    )


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
