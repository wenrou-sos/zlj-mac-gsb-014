"""Application configuration.

The database URL is read from the environment so that:
- local development / CI can use SQLite (``DATABASE_URL=sqlite:///./ccsim.db``)
- docker-compose injects a PostgreSQL URL.
"""
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://ccsim:ccsim@db:5432/ccsim",
)

# Allow the test-suite (and local dev without Postgres) to fall back to SQLite.
if os.getenv("USE_SQLITE") == "1":
    DATABASE_URL = os.getenv("SQLITE_URL", "sqlite:///./ccsim.db")

# CORS origins allowed to talk to the API (the Vue dev server / nginx origin).
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
