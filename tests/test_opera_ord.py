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
