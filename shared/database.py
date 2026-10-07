"""
MongoDB connection.

One MongoClient per process is the recommended pattern: the client keeps an
internal connection pool and is thread-safe, so we create it once (lru_cache)
and reuse it. Each service then picks its *own* database from this client
("database per service"), so no service reads another service's data directly.
"""

from functools import lru_cache

from pymongo import MongoClient

from shared.config import get_settings


@lru_cache
def get_mongo_client() -> MongoClient:
    settings = get_settings()
    return MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,  # fail fast with a clear error if MongoDB isn't running
        tz_aware=True,  # return timezone-aware UTC datetimes
    )
