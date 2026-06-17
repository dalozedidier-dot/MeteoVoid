from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from meteovoid.belgium import opera_ord as module
from meteovoid.belgium.opera_ord import (
    analyse_radar_file,
    build_items_query_url,
    build_location_query_url,
    build_opera_inventory,
    build_opera_metrics,
    extract_data_links,
    inspect_opera_ord,
    write_opera_ord_outputs,
)


def test_build_opera_urls_and_extract_links() -> None:
    location_url = build_location_query_url(
        location_id="0-20010-0-OPERA",
        datetime_range="2026-06-17T00:00Z/2026-06-17T01:00Z",
        standard_name="RATE",
        data_format="GEOTIFF",
        method="comp",
    )
    assert "collections/observations/locations/0-20010-0-OPERA" in location_url
    assert "standard_name=RATE" in location_url
    assert "format=GEOTIFF" in location_url

    items_url = build_items_query_url(bbox=(1.0, 48.5, 7.5, 52.0), standard_name="DBZH")
    assert "collections/observations/items" in items_url
    assert "bbox=1.0%2C48.5%2C7.5%2C52.0" in items_url

    links = extract_data_links(
        {
            "links": [
                {"rel": "data", "href": "https://example.test/radar.tif"},
                {"rel": "self", "href": "https://example.test/metadata.json"},
            ],
            "nested": {"href": "https://example.test/file.h5", "type": "application/x-hdf5"},
        }
    )
    assert links == ["https://example.test/file.h5", "https://example.test/radar.tif"]


def test_opera_inventory_disabled_builds_composite_queries(tmp_path: Path) -> None:
    cfg = tmp_path / "opera.yaml"
    cfg.write_text(
        """
contract: opera_ord_connector_config_v2
api:
  base_url: https://example.invalid/ord
products:
  composites:
    location_id: "0-20010-0-OPERA"
    method: comp
    format_priority: [GEOTIFF]
    standard_names: [DBZH, RATE]
""".lstrip(),
        encoding="utf-8",
    )
    inventory = build_opera_inventory(cfg, enabled=False)
    assert inventory["status"] == "disabled"
    assert len(inventory["queries"]) == 2
    assert inventory["queries"][0]["status"] == "not_fetched"


def test_opera_inventory_live_with_links(monkeypatch, tmp_path: Path) -> None:
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
        def __init__(self, payload: dict[str, Any]):
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
        return FakeResponse({"links": [{"rel": "data", "href": "https://example.test/dbzh.tif"}]})

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    inventory = build_opera_inventory(cfg, enabled=True)
    assert inventory["status"] == "data_links_available"
    assert inventory["data_links"] == ["https://example.test/dbzh.tif"]


def test_inspect_and_write_opera_outputs_without_network(tmp_path: Path) -> None:
    cfg = tmp_path / "opera.yaml"
    cfg.write_text("contract: opera_ord_connector_config_v2\n", encoding="utf-8")
    status = inspect_opera_ord(cfg, enabled=False, cache_dir=tmp_path / "cache")
    assert status["status"] == "disabled"
    assert status["machine_radar_confirmation"] is False

    written = write_opera_ord_outputs(tmp_path, config_path=cfg, enabled=False)
    assert written["status"] == "disabled"
    assert (tmp_path / "opera_ord_status.json").exists()
    assert (tmp_path / "opera_ord_inventory.json").exists()
    assert (tmp_path / "opera_radar_metrics.json").exists()
    assert (tmp_path / "opera_ord_files_manifest.json").exists()


def test_local_numeric_radar_metrics(tmp_path: Path) -> None:
    frame = tmp_path / "frame.npy"
    np.save(frame, np.array([[0.0, 12.0], [24.0, np.nan]]))
    metric = analyse_radar_file(frame)
    assert metric["status"] == "analysed_numeric"
    assert metric["max"] == 24.0

    metrics = build_opera_metrics(
        [
            {
                "status": "downloaded",
                "path": str(frame),
                "sha256": "abc",
            }
        ]
    )
    assert metrics["status"] == "metrics_available"
    assert metrics["machine_radar_available"] is True
    assert metrics["radar_activity_score"] is not None


def test_opera_private_helpers_and_env(monkeypatch, tmp_path: Path) -> None:
    assert module._load_yaml_mapping(None) == {}
    assert module._load_yaml_mapping(tmp_path / "missing.yml") == {}
    scalar = tmp_path / "scalar.yml"
    scalar.write_text("42\n", encoding="utf-8")
    assert module._load_yaml_mapping(scalar) == {}

    assert module._as_bool(True) is True
    assert module._as_bool(1) is True
    assert module._as_bool("YES") is True
    assert module._as_bool("nope") is False
    assert module._as_bool(None, default=True) is True
    assert module._as_int("7", 3) == 7
    assert module._as_int("bad", 3) == 3
    assert module._safe_float("2.5") == 2.5
    assert module._safe_float("nan", 9.0) == 9.0
    assert module._safe_float("bad", 9.0) == 9.0

    legacy_config = {"base_url": "https://legacy.example", "timeout_seconds": 9}
    assert module._config_api(legacy_config)["base_url"] == "https://legacy.example"
    assert module._bbox_from_config({}, "bbox") == (-2.5, 47.0, 9.5, 53.5)
    assert module._bbox_from_config(
        {"bbox": {"west": "1", "south": "48", "east": "7", "north": "52"}}, "bbox"
    ) == (1.0, 48.0, 7.0, 52.0)

    monkeypatch.setenv("METEOGATE_API_KEY", "secret")
    headers = module._request_headers({"api": {"api_key_env": "METEOGATE_API_KEY"}})
    assert headers["Authorization"] == "Bearer secret"
    monkeypatch.setenv("METEOVOID_OPERA_ORD_BASE_URL", "https://override.example/")
    assert module._base_url_from_config({}) == "https://override.example"


def test_opera_query_error_branches(monkeypatch) -> None:
    class FakeHTTPError(module.HTTPError):
        def __init__(self, code: int):
            super().__init__("https://example.test", code, "boom", hdrs=None, fp=None)

    def raise_204(*args: object, **kwargs: object) -> None:
        raise FakeHTTPError(204)

    monkeypatch.setattr(module, "urlopen", raise_204)
    assert (
        module._query_json_safe("https://example.test", headers={}, timeout_s=1)["status"]
        == "no_content"
    )

    def raise_429(*args: object, **kwargs: object) -> None:
        raise FakeHTTPError(429)

    monkeypatch.setattr(module, "urlopen", raise_429)
    assert (
        module._query_json_safe("https://example.test", headers={}, timeout_s=1)["status"]
        == "rate_limited"
    )

    def raise_500(*args: object, **kwargs: object) -> None:
        raise FakeHTTPError(500)

    monkeypatch.setattr(module, "urlopen", raise_500)
    assert (
        module._query_json_safe("https://example.test", headers={}, timeout_s=1)["status"]
        == "http_error"
    )

    def raise_url_error(*args: object, **kwargs: object) -> None:
        raise module.URLError("offline")

    monkeypatch.setattr(module, "urlopen", raise_url_error)
    assert (
        module._query_json_safe("https://example.test", headers={}, timeout_s=1)["status"]
        == "query_error"
    )


def test_opera_download_success_and_failure(monkeypatch, tmp_path: Path) -> None:
    assert module._safe_download_name("https://example.test/a/b/radar file?.tif", 1).startswith(
        "radar_file"
    )
    assert module._safe_download_name("https://example.test/", 2) == "opera_ord_2.bin"

    class FakeDownloadResponse:
        def __init__(self) -> None:
            self.calls = 0

        def __enter__(self) -> FakeDownloadResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            self.calls += 1
            return b"abc" if self.calls == 1 else b""

    def fake_urlopen_success(request: object, timeout: float) -> FakeDownloadResponse:
        return FakeDownloadResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen_success)
    downloaded = module.download_data_links(["https://example.test/radar.bin"], tmp_path)
    assert downloaded[0]["status"] == "downloaded"
    assert downloaded[0]["size_bytes"] == 3
    assert module.sha256_file(downloaded[0]["path"])

    def fake_urlopen_error(request: object, timeout: float) -> None:
        raise module.URLError("offline")

    monkeypatch.setattr(module, "urlopen", fake_urlopen_error)
    failed = module.download_data_links(["https://example.test/radar.bin"], tmp_path / "fail")
    assert failed[0]["status"] == "download_error"


def test_opera_file_analysis_edge_cases(tmp_path: Path) -> None:
    assert analyse_radar_file(tmp_path / "missing.npy")["status"] == "missing"

    empty = tmp_path / "empty.npy"
    np.save(empty, np.array([np.nan]))
    assert analyse_radar_file(empty)["status"] == "empty_numeric_array"

    csv_path = tmp_path / "frame.csv"
    csv_path.write_text("1,2\n3,4\n", encoding="utf-8")
    assert analyse_radar_file(csv_path)["max"] == 4.0

    json_path = tmp_path / "frame.json"
    json_path.write_text(json.dumps({"data": [[5, 6], [7, 8]]}), encoding="utf-8")
    assert analyse_radar_file(json_path)["p95"] > 7.0

    bad = tmp_path / "frame.bin"
    bad.write_bytes(b"not numeric")
    assert analyse_radar_file(bad)["status"] == "unreadable"

    h5 = tmp_path / "frame.h5"
    h5.write_bytes(b"not hdf")
    assert analyse_radar_file(h5)["status"] in {
        "wradlib_missing",
        "odim_read_error",
        "wradlib_available_reader_not_exposed",
    }

    tif = tmp_path / "frame.tif"
    tif.write_bytes(b"not tif")
    assert analyse_radar_file(tif)["status"] in {"rasterio_missing", "geotiff_read_error"}


def test_opera_metrics_and_inventory_more_branches(monkeypatch, tmp_path: Path) -> None:
    assert module._activity_score_from_metrics([]) is None
    assert module._activity_score_from_metrics([{"ok": False, "p95": 100}]) is None
    assert module._activity_score_from_metrics([{"ok": True, "p95": 120}]) == 1.0

    cfg = tmp_path / "opera.yaml"
    cfg.write_text(
        """
api:
  base_url: https://example.invalid/ord
products:
  composites:
    location_id: "0-20010-0-OPERA"
    method: comp
    format_priority: [ODIM]
    standard_names: [ACRR]
queries:
  - id: legacy
    location_id: "0-20010-0-OPERA"
    standard_name: RATE
    format: GEOTIFF
outputs:
  status_json: custom_status.json
  inventory_json: custom_inventory.json
  metrics_json: custom_metrics.json
  files_manifest: custom_files.json
cache:
  root_dir: relative_cache
upstream_bbox:
  west: 1
  south: 48
  east: 7
  north: 52
""".lstrip(),
        encoding="utf-8",
    )
    inventory = build_opera_inventory(cfg, enabled=False, products=["DBZH"])
    assert inventory["status"] == "disabled"
    assert len(inventory["queries"]) == 2

    frame = tmp_path / "frame.npy"
    np.save(frame, np.array([[60.0]]))

    def fake_download_data_links(
        links: list[str],
        out_dir: str | Path,
        *,
        headers: dict[str, str] | None = None,
        timeout_s: float = 60.0,
        max_files: int = 8,
    ) -> list[dict[str, Any]]:
        return [{"status": "downloaded", "path": str(frame), "sha256": "abc"}]

    monkeypatch.setattr(module, "download_data_links", fake_download_data_links)

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"links": [{"rel": "data", "href": "https://example.test/frame.npy"}]}
            ).encode("utf-8")

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    status = inspect_opera_ord(cfg, enabled=True, download=True, cache_dir=tmp_path / "cache")
    assert status["status"] == "metrics_available"
    assert status["machine_radar_confirmation"] is True

    written = write_opera_ord_outputs(
        tmp_path / "out", config_path=cfg, enabled=True, download=True
    )
    assert written["status"] == "metrics_available"
    assert (tmp_path / "out" / "custom_status.json").exists()
    assert (tmp_path / "out" / "custom_inventory.json").exists()
    assert (tmp_path / "out" / "custom_metrics.json").exists()
    assert (tmp_path / "out" / "custom_files.json").exists()
