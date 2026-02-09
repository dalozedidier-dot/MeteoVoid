# MeteoVoid Live Pipeline

MeteoVoid can run in streaming mode, consuming observations from Redis Streams and emitting live "instability" reports.

## Components

- **Redis** stores:
  - `meteovoid:observations` stream: incoming measurements
  - `meteovoid:reports` stream: computed live reports
  - `meteovoid:latest:<station_id>:<variable>` keys: latest report snapshot per station/variable

- **meteovoid live** reads observations and writes reports.
- **meteovoid serve** exposes an HTTP API for the latest reports.

## Quick start (Docker Compose)

From the repository root:

```bash
docker compose up --build
```

In another terminal, publish a synthetic stream:

```bash
docker compose run --rm meteovoid-live meteovoid simulate --redis-url redis://redis:6379/0 --sleep 0.01
```

Then query the API:

```bash
curl "http://localhost:8000/latest?station_id=DEMO_BE_0001&variable=wind_gust_ms"
```

## CLI usage (local)

Install with live extras:

```bash
python -m pip install -e ".[live]"
```

Run Redis locally, then:

```bash
meteovoid live --redis-url redis://localhost:6379/0
meteovoid simulate --redis-url redis://localhost:6379/0
meteovoid serve --host 0.0.0.0 --port 8000
```

## Observation input format

Each observation is a JSON-like dict stored as fields in Redis Streams:

- `ts`: ISO 8601 timestamp (UTC recommended)
- `station_id`: station identifier
- `variable`: variable name
- `value`: numeric value
- optional: `lat`, `lon`, `quality`

Example:

```json
{
  "ts": "2026-02-09T12:34:00Z",
  "station_id": "BE_1234",
  "variable": "wind_gust_ms",
  "value": 18.2,
  "lat": 50.85,
  "lon": 4.35,
  "quality": 0.98
}
```

## Live report output

Each computed report includes:

- `score`: 0 to 1
- `state`: stable, transition, unstable
- `explain`: component scores (variance jump, slope change, outlier fraction)
- `missing_frac`: missing data estimate inside the rolling window

These are lightweight diagnostics intended to feed a larger alerting system.
