import json
import os
from collections.abc import Callable
from typing import Any, Generic, TypeVar

import redis.asyncio as aioredis

from app.schemas import TrainRoute

T = TypeVar("T")

# ── Shared connection pool ───────────────────────────────────────

_pool: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared Redis connection, creating it lazily."""
    global _pool
    if _pool is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _pool = aioredis.from_url(url, decode_responses=True)
    return _pool


async def close_redis() -> None:
    """Shut down the shared Redis connection."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


# ── Generic typed cache ──────────────────────────────────────────


class TypedRedisCache(Generic[T]):
    """Redis cache with key prefixing, TTLs, and pluggable serialization."""

    def __init__(
        self,
        prefix: str,
        ttl: int,
        serializer: Callable[[T], str] = json.dumps,
        deserializer: Callable[[str], T] = json.loads,
    ):
        self.prefix = prefix
        self.ttl = ttl
        self.serializer = serializer
        self.deserializer = deserializer

    def _key(self, *parts: Any) -> str:
        # e.g. ("NDLS", "BCT", None) -> "seg:NDLS:BCT:_"
        return f"{self.prefix}:" + ":".join(str(p) if p else "_" for p in parts)

    async def get(self, *parts: Any) -> T | None:
        raw = await get_redis().get(self._key(*parts))
        return self.deserializer(raw) if raw is not None else None

    async def put(self, *parts_and_value: Any) -> None:
        """Last positional arg is the value; the rest form the cache key."""
        *parts, value = parts_and_value
        await get_redis().set(self._key(*parts), self.serializer(value), ex=self.ttl)

    async def delete(self, *parts: Any) -> None:
        await get_redis().delete(self._key(*parts))

    async def exists(self, *parts: Any) -> bool:
        return await get_redis().exists(self._key(*parts)) > 0


# ── Boolean flag cache ───────────────────────────────────────────


class FlagCache(TypedRedisCache[str]):
    """Presence-only cache: exists → True, missing → False."""

    async def get(self, *parts: Any) -> bool:  # type: ignore[override]
        return await self.exists(*parts)

    async def put(self, *parts: Any) -> None:
        await get_redis().set(self._key(*parts), "1", ex=self.ttl)


# ── Cache instances ──────────────────────────────────────────────

RouteCache = TypedRedisCache[TrainRoute](
    prefix="route",
    ttl=24 * 3600,  # 24hrs
    serializer=lambda r: r.model_dump_json(),
    deserializer=TrainRoute.model_validate_json,
)

SegmentCache = TypedRedisCache[list[dict]](
    prefix="seg",
    ttl=3 * 3600,
)

DeadPairCache = FlagCache(
    prefix="dead",
    ttl=12 * 3600,
)
