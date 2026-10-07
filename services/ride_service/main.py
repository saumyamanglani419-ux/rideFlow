"""
Ride Service entry point.

Run:  uvicorn services.ride_service.main:app --port 8003 --reload
Docs: http://127.0.0.1:8003/docs

Needs the Fare Service (8004) and Driver Service (8002) running.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from services.ride_service.database import get_db
from services.ride_service.repository import ensure_indexes
from services.ride_service.routes import router
from shared.config import get_settings
from shared.service_client import ServiceUnavailableError, UpstreamServiceError


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()
    ensure_indexes(get_db())
    yield


app = FastAPI(
    title="RideFlow - Ride Service",
    version="1.0.0",
    description=(
        "Ride requests, driver assignment, status transitions and trip history. "
        "Talks to the Fare and Driver services over HTTP."
    ),
    lifespan=lifespan,
)
app.include_router(router)


# Turn dependency failures into clear HTTP errors in ONE place,
# instead of try/except in every route.
@app.exception_handler(ServiceUnavailableError)
async def handle_service_unavailable(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": f"The {exc.service} is unavailable ({exc.reason}). Please try again later."},
    )


@app.exception_handler(UpstreamServiceError)
async def handle_upstream_error(request: Request, exc: UpstreamServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": f"The {exc.service} returned an unexpected error (HTTP {exc.status_code})."},
    )


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"service": "ride-service", "status": "ok"}
