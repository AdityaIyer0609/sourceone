from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

register_error_handlers(app)
app.include_router(api_router)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "sourceone-backend",
    }
