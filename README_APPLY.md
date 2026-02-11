Patch: fix /latest (no params) returning {status:not_found} even when Redis contains latest keys.

Root cause:
- api.py was filtering keys using str(k).startswith('meteovoid:latest:') BEFORE decoding bytes keys.
  redis-py typically returns bytes unless decode_responses=True, so the filter dropped all keys.

Fix:
- Decode keys first, then apply startswith filter.
- Keep black/ruff-format stable formatting.
- Update live_smoke.yml to clean _ci_out/live_smoke and try /stations even when /latest 200 but invalid.

Files:
- src/meteovoid/api.py
- .github/workflows/live_smoke.yml
