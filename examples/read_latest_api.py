from __future__ import annotations

import json
import urllib.request

with urllib.request.urlopen("http://localhost:8000/latest", timeout=5) as response:  # noqa: S310
    print(json.dumps(json.loads(response.read().decode()), indent=2, ensure_ascii=False))
