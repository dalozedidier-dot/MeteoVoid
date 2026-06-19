from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def cache_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _read_cached(path: Path, ttl_seconds: int) -> dict[str, Any] | None:
    if ttl_seconds <= 0 or not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > float(ttl_seconds):
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def fetch_json_with_file_cache(
    url: str,
    *,
    cache_dir: str | Path,
    ttl_seconds: int = 300,
    timeout_s: float = 5.0,
    user_agent: str = "MeteoVoid/1.0",
) -> dict[str, Any]:
    """Fetch JSON with a small file cache, intended for radar metadata."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
    file_path = cache_path / f"{cache_key(url)}.json"

    cached = _read_cached(file_path, ttl_seconds)
    if cached is not None:
        cached.setdefault("_cache", {})
        cached["_cache"].update({"status": "hit", "ttl_seconds": int(ttl_seconds)})
        return cached

    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HTTP JSON response must be an object")
    payload.setdefault("_cache", {})
    payload["_cache"].update({"status": "miss", "ttl_seconds": int(ttl_seconds)})
    file_path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return payload
