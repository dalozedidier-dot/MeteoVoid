# MeteoVoid hotfix: restore State + compatible live.py

Your Live Smoke compose logs show:
    ImportError: cannot import name 'State' from 'meteovoid.live'

Cause:
- live.py was replaced by a variant that removed the `State` alias.

Fix:
- Reintroduce `State = Literal["stable", "transition", "unstable"]`
- Keep LiveConfig + RollingWindow + analyze_window() compatible with stream.py imports
- Keep RollingWindow.values(now) for the unit tests.

Apply:
1) Unzip at repo root.
2) Commit + push.
3) Live Smoke should reach /health again (api container will start).
