from pymongo.database import Database

from shared.config import get_settings
from shared.database import get_mongo_client


def get_db() -> Database:
    """FastAPI dependency. Tests replace it with an in-memory mongomock database."""
    return get_mongo_client()[get_settings().ride_db_name]
