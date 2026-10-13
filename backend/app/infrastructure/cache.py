"""Cache singleton instances.

Separated from redis.py so that cache definitions (the classes) don't
get tangled with cache wiring (the singletons that depend on domain schemas).
"""

from app.config import get_settings
from app.infrastructure.redis import HashRedisCache, StringRedisCache
from app.schemas import TrainRoute

settings = get_settings()

RouteCache = StringRedisCache[TrainRoute](
    prefix="route",
    ttl=settings.route_cache_ttl,
    serializer=lambda r: r.model_dump_json(),
    deserializer=TrainRoute.model_validate_json,
)

TrainSearchCache = HashRedisCache[dict](
    prefix="search_seg",
    ttl=settings.segment_cache_ttl,
)

SeatFinderSegmentCache = HashRedisCache[dict](
    prefix="sf_seg",
    ttl=settings.segment_cache_ttl,
)

# Days a train departs `board` before the user's `source` (train:board:source -> int),
# measured from confirmtkt timings where the route's day offsets were wrong.
BoardDayCache = StringRedisCache[int](
    prefix="board_days",
    ttl=settings.route_cache_ttl,
)
