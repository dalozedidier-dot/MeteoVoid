from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from meteovoid.belgium import radar_stack as module
from meteovoid.belgium.radar_stack import (
    analyze_radar_files,
    build_opera_ord_query_url,
    build_radar_stack,
    build_rainviewer_status,
    compute_pysteps_from_paths,
    compute_pysteps_motion,
    inspect_opera_ord,
    write_radar_stack_outputs,
)


def test_rainviewer_status_offline_and_map(tmp_path: Path) -> None:
    status = build_rainviewer_status(fetch_live=False)
    assert status["contract"] == "rainviewer_radar_overlay_v1"
    assert status["status"] == "client_side_overlay_ready"
    assert status["api_url"].endswith("weather-maps.json")

    module.write_rainviewer_map(tmp_path / "rainviewer.html")
    html = (tmp_path / "rainviewer.html").read_text(encoding="utf-8")
    assert "api.rainviewer.com/public/weather-maps.json" in html
    assert "tileLayer" in html


def test_rainviewer_status_live_success_and_error(monkeypatch) -> None:
    def fake_json(url: str, *, timeout_s: float) -> dict[str, object]:
        assert "rainviewer" in url
        assert timeout_s == 1.0
        return {
            "version": "2.0.1",
            "generated": 123,
            "host": "https://tiles.example",
            "radar": {"past": [{"time": 100, "path": "/v2/radar/100"}], "nowcast": []},
        }

    monkeypatch.setattr(module, "_http_json", fake_json)
    ok = build_rainviewer_status(fetch_live=True, timeout_s=1.0)
    assert ok["status"] == "ok"
    assert ok["past_frame_count"] == 1
    assert ok["last_frame_time_unix"] == 100

    monkeypatch.setattr(
        module, "_http_json", lambda url, *, timeout_s: (_ for _ in ()).throw(ValueError("bad"))
    )
    err = build_rainviewer_status(fetch_live=True, timeout_s=1.0)
    assert err["status"] == "error"


def test_opera_ord_query_url_and_disabled_config(tmp_path: Path) -> None:
    url = build_opera_ord_query_url(
        location_id="0-578-0-nohur",
        datetime_range="2026-06-04T06:10Z/2026-06-04T06:40Z",
    )
    assert "api.meteogate.eu" in url
    assert "collections/observations/locations/0-578-0-nohur" in url
    assert "standard_name=DBZH" in url
    assert "format=ODIM" in url

    cfg = tmp_path / "opera.yaml"
    cfg.write_text(
        """
contract: opera_ord_connector_config_v1
base_url: https://example.invalid/ord
queries:
  - id: q1
    collection: observations
    location_id: LOC1
    standard_name: DBZH
""".lstrip(),
        encoding="utf-8",
    )
    status = inspect_opera_ord(cfg, enabled=False)
    assert status["status"] == "disabled"
    assert status["inventory"]["queries"][0]["status"] == "not_fetched"


def test_opera_ord_enabled_success_and_query_error(tmp_path: Path, monkeypatch) -> None:
    from meteovoid.belgium import opera_ord as opera_module

    cfg = tmp_path / "opera.yaml"
    cfg.write_text(
        """
contract: opera_ord_connector_config_v2
api:
  base_url: https://example.invalid/ord
  timeout_seconds: 2
products:
  composites:
    location_id: "0-20010-0-OPERA"
    method: comp
    format_priority: [GEOTIFF]
    standard_names: [DBZH]
""".lstrip(),
        encoding="utf-8",
    )

    class FakeResponse:
        def __init__(self, payload: dict[str, object]):
            self.payload = payload

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        url = request.full_url  # type: ignore[attr-defined]
        assert timeout == 2.0
        if url.endswith("/collections"):
            return FakeResponse({"collections": [{"id": "observations"}]})
        return FakeResponse({"type": "CoverageJSON", "links": [{"rel": "data", "href": "https://example.test/file.tif"}]})

    monkeypatch.setattr(opera_module, "urlopen", fake_urlopen)
    status = inspect_opera_ord(cfg, enabled=True, timeout_s=2.0)
    assert status["status"] == "data_links_available"
    assert status["inventory"]["data_links"] == ["https://example.test/file.tif"]


def test_radar_file_numeric_processing_and_stack_outputs(tmp_path: Path) -> None:
    arr = np.array([[0.0, 2.0], [5.0, np.nan]])
    frame = tmp_path / "frame.npy"
    np.save(frame, arr)
    processing = analyze_radar_files([frame, tmp_path / "missing.npy"])
    assert processing["status"] == "ok"
    assert processing["readable_frame_count"] == 1
    assert processing["max_value_over_frames"] == 5.0

    stack = write_radar_stack_outputs(tmp_path, radar_frame_paths=[frame])
    assert stack["honest_state"] == "local_radar_frames_readable"
    assert (tmp_path / "radar_stack.json").exists()
    assert (tmp_path / "rainviewer_radar_map.html").exists()
    assert (tmp_path / "opera_ord_status.json").exists()


def test_pysteps_disabled_and_insufficient_frames(tmp_path: Path) -> None:
    disabled = compute_pysteps_from_paths([], enabled=False)
    assert disabled["status"] == "disabled"

    frame = tmp_path / "frame.npy"
    np.save(frame, np.ones((2, 2)))
    insufficient = compute_pysteps_from_paths([frame], enabled=True)
    assert insufficient["status"] == "insufficient_readable_frames"

    direct = compute_pysteps_motion(np.ones((2, 2)))
    assert direct["status"] == "insufficient_frames"


def test_build_radar_stack_no_machine_data() -> None:
    stack = build_radar_stack(enable_rainviewer_live=False, enable_opera_ord=False)
    assert stack["contract"] == "meteovoid_european_radar_stack_v2"
    assert stack["honest_state"] == "no_machine_radar_data"
    assert stack["summary"]["machine_radar_confirmation"] is False
