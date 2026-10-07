"""
Fare Service entry point.

Run:  uvicorn services.fare_service.main:app --port 8004 --reload
Docs: http://127.0.0.1:8004/docs
"""

from fastapi import FastAPI

from services.fare_service.routes import router
from shared.config import get_settings

get_settings()  # fail at startup (not on the first request) if config is broken

app = FastAPI(
    title="RideFlow - Fare Service",
    version="1.0.0",
    description="Stateless fare estimation: base fare + distance x per-km rate, with a minimum fare.",
)
app.include_router(router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"service": "fare-service", "status": "ok"}
