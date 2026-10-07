"""
User Service entry point.

Run:  uvicorn services.user_service.main:app --port 8001 --reload
Docs: http://127.0.0.1:8001/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.user_service.database import get_db
from services.user_service.repository import ensure_indexes
from services.user_service.routes import router
from shared.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # validate configuration at startup
    ensure_indexes(get_db())  # also proves MongoDB is reachable
    yield


app = FastAPI(
    title="RideFlow - User Service",
    version="1.0.0",
    description="Registration, login (JWT) and user profiles for riders and drivers.",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"service": "user-service", "status": "ok"}
