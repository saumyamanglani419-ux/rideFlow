"""
Driver Service entry point.

Run:  uvicorn services.driver_service.main:app --port 8002 --reload
Docs: http://127.0.0.1:8002/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.driver_service.database import get_db
from services.driver_service.repository import ensure_indexes
from services.driver_service.routes import internal_router, router
from shared.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
    ensure_indexes(get_db())
    yield


app = FastAPI(
    title="RideFlow - Driver Service",
    version="1.0.0",
    description="Driver profiles, availability and nearest-driver selection.",
    lifespan=lifespan,
)
app.include_router(router)
app.include_router(internal_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"service": "driver-service", "status": "ok"}
