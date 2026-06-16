from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:  # pragma: no cover
    from redis.client import Redis


def make_redis(url: str) -> Redis:
    # decode_responses=True => str au lieu de bytes pour get/xread fields
    try:
        from redis.client import Redis
    except ModuleNotFoundError as exc:  # pragma: no cover - live extra missing
        raise RuntimeError(
            "Redis support requires the live extra: install with `pip install meteo-void[live]`."
        ) from exc

    client: Any = Redis.from_url(url, decode_responses=True)
    return cast("Redis", client)
