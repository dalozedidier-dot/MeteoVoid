from __future__ import annotations

from redis.client import Redis


def make_redis(url: str) -> Redis:
    # decode_responses=True => str au lieu de bytes pour get/xread fields
    return Redis.from_url(url, decode_responses=True)
