"""Vercel entry point for the four RideFlow APIs."""

from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from services.driver_service.main import app as driver_app
from services.fare_service.main import app as fare_app
from services.ride_service.main import app as ride_app
from services.user_service.main import app as user_app

SERVICES = {
    "user": user_app,
    "driver": driver_app,
    "ride": ride_app,
    "fare": fare_app,
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with AsyncExitStack() as stack:
        for service in SERVICES.values():
            await stack.enter_async_context(service.router.lifespan_context(service))
        yield


app = FastAPI(title="RideFlow", lifespan=lifespan)

for name, service in SERVICES.items():
    app.mount(f"/{name}", service)


@app.get("/")
def service_directory() -> dict[str, dict[str, str]]:
    return {"services": {name: f"/{name}/docs" for name in SERVICES}}
