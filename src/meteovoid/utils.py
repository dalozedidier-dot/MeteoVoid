from redis import Redis

def make_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)
