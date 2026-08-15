import json
import os
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis

from app.schemas import TrainRoute

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


# ── Base Redis cache ─────────────────────────────────────────────


class BaseRedisCache[T]:
    """Base Redis cache with key prefixing, TTLs, and pluggable serialization."""

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
        return f"{self.prefix}:" + ":".join(str(p) for p in parts if p is not None)

    async def delete(self, *parts: Any) -> None:
        await get_redis().delete(self._key(*parts))

    async def exists(self, *parts: Any) -> bool:
        return await get_redis().exists(self._key(*parts)) > 0


# ── Generic typed string cache ───────────────────────────────────


class StringRedisCache[T](BaseRedisCache[T]):
    """Redis String cache for single typed values (GET / SET)."""

    async def get(self, *parts: Any) -> T | None:
        raw = await get_redis().get(self._key(*parts))
        return self.deserializer(raw) if raw is not None else None

    async def put(self, *parts_and_value: Any) -> None:
        """Last positional arg is the value; the rest form the cache key."""
        *parts, value = parts_and_value
        await get_redis().set(self._key(*parts), self.serializer(value), ex=self.ttl)


# ── Boolean flag cache ───────────────────────────────────────────


class FlagRedisCache(BaseRedisCache[str]):
    """Presence-only cache: exists → True, missing → False."""

    async def get(self, *parts: Any) -> bool:  # type: ignore[override]
        return await self.exists(*parts)

    async def put(self, *parts: Any) -> None:
        await get_redis().set(self._key(*parts), "1", ex=self.ttl)


# ── Hash redis cache ─────────────────────────────────────────────


class HashRedisCache[T](BaseRedisCache[T]):
    """Redis Hash cache mapping sub-keys (e.g. train_number) to typed values."""

    async def get_all(self, *parts: Any) -> list[T]:
        """Fetch all fields from the hash as a list of deserialized values."""
        raw_map = await get_redis().hgetall(self._key(*parts))
        if not raw_map:
            return []
        return [self.deserializer(v) for v in raw_map.values()]

    async def get_field(self, *parts_and_field: Any) -> T | None:
        """Fetch a single field from the hash."""
        *parts, field = parts_and_field
        raw = await get_redis().hget(self._key(*parts), str(field))
        return self.deserializer(raw) if raw is not None else None

    async def put_field(self, *parts_field_value: Any) -> None:
        """Set a single field in the hash and refresh key TTL."""
        *parts, field, value = parts_field_value
        key = self._key(*parts)
        pipe = get_redis().pipeline()
        pipe.hset(key, str(field), self.serializer(value))
        pipe.expire(key, self.ttl)
        await pipe.execute()

    async def put_many(self, *parts_and_mapping: Any) -> None:
        """Set multiple fields in the hash at once and refresh key TTL."""
        *parts, mapping = parts_and_mapping
        if not mapping:
            return
        key = self._key(*parts)
        serialized_map = {str(k): self.serializer(v) for k, v in mapping.items()}
        pipe = get_redis().pipeline()
        pipe.hset(key, mapping=serialized_map)
        pipe.expire(key, self.ttl)
        await pipe.execute()


# ── Cache instances ──────────────────────────────────────────────

RouteCache = StringRedisCache[TrainRoute](
    prefix="route",
    ttl=24 * 3600,  # 24hrs
    serializer=lambda r: r.model_dump_json(),
    deserializer=TrainRoute.model_validate_json,
)

SegmentCache = HashRedisCache[dict](
    prefix="seg",
    ttl=3 * 3600,
)

FullSearchCache = FlagRedisCache(
    prefix="full_search",
    ttl=3 * 3600,
)

DeadPairCache = FlagRedisCache(
    prefix="dead",
    ttl=24 * 3600,
)
