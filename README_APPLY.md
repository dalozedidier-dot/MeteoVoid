Patch: Coverage hotfix (raise total coverage above 85%)

Your CI logs show:
- TOTAL coverage 84.12% (fail-under=85)

Main gap was still in src/meteovoid/ingest_europe.py (58% covered).
This patch adds a small, network-free unit test file to cover:
- _http_json success + non-object rejection
- main(... --once) happy path (with monkeypatched ingest_once)
- main(... --once) error path (ingest_once raises URLError)

Files added:
- tests/test_ingest_europe_more.py
