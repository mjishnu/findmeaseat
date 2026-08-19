"""Centralized application settings.

All environment variables are validated here at import time via Pydantic
BaseSettings. If a required variable is missing, the app fails fast at
startup rather than at the first Redis call or request.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Cache TTLs (seconds)
    route_cache_ttl: int = 24 * 3600       # 24 hours
    segment_cache_ttl: int = 3 * 3600      # 3 hours
    full_search_cache_ttl: int = 3 * 3600  # 3 hours
    dead_pair_cache_ttl: int = 24 * 3600   # 24 hours
    manifest_ttl: float = 300.0            # 5 minutes

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
