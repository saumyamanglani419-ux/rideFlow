"""Pydantic models that more than one service needs."""

from pydantic import BaseModel, Field


class Location(BaseModel):
    latitude: float = Field(ge=-90, le=90, examples=[12.9758])
    longitude: float = Field(ge=-180, le=180, examples=[77.6050])
