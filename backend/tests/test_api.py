"""API tests against a small synthetic snapshot written to a temp dir.

Synthetic data, delivery days 2026-01-15 and 2026-01-16 (GMT, so UK time = UTC):
- forecasts for every hourly slot T on day D, two publishes:
    D-1 07:30Z -> 1000 + hour(T) MW   (the one the 09:00 day-ahead gate selects)
    D-1 09:30Z -> 5000 MW              (after the gate; selected by horizon H <= ~14 h)
- actuals: 900 MW every half-hour, except 2026-01-16T05:00Z which is missing.
So day-ahead error = 100 + hour, over 47 paired slots.
"""

import hashlib
import importlib.util
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.observability import JsonFormatter
from app.snapshot import SnapshotError

REPO_ROOT = Path(__file__).resolve().parents[2]
FIRST, LAST = date(2026, 1, 15), date(2026, 1, 16)
MISSING_ACTUAL = "2026-01-16T05:00:00Z"
ORIGIN = "http://localhost:5173"


def write_snapshot(data_dir: Path) -> None:
    targets = pd.date_range("2026-01-15", "2026-01-17", freq="1h", inclusive="left", tz="UTC")
    rows = []
    for t in targets:
        d_minus_1 = t.normalize() - timedelta(days=1)
        rows.append((d_minus_1 + timedelta(hours=7, minutes=30), t, 1000 + t.hour))
        rows.append((d_minus_1 + timedelta(hours=9, minutes=30), t, 5000))
    forecasts = pd.DataFrame(rows, columns=["publish_time_utc", "start_time_utc", "generation_mw"])
    half_hours = pd.date_range("2026-01-15", "2026-01-17", freq="30min", inclusive="left", tz="UTC")
    half_hours = half_hours[half_hours != pd.Timestamp(MISSING_ACTUAL)]
    actuals = pd.DataFrame({"start_time_utc": half_hours, "generation_mw": 900})

    files = {}
    for name, frame in (("actuals.parquet", actuals), ("forecasts.parquet", forecasts)):
        frame.to_parquet(data_dir / name)
        files[name] = {"sha256": hashlib.sha256((data_dir / name).read_bytes()).hexdigest()}
    manifest = {
        "snapshot_id": "test-snapshot",
        "scope": {"first_delivery_day": FIRST.isoformat(), "last_delivery_day": LAST.isoformat()},
        "files": files,
    }
    (data_dir / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    write_snapshot(tmp_path)
    return tmp_path


@pytest.fixture
def app(data_dir: Path) -> FastAPI:
    return create_app(Settings(data_dir=data_dir, cors_origins=(ORIGIN,), cache_size=8))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# --- health / meta / docs ------------------------------------------------------------------


def test_health(client):
    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["snapshot_id"] == "test-snapshot"
    assert set(body["cache"]) == {"selection", "lead_time_curve"}


def test_meta(client):
    body = client.get("/api/meta").json()

    assert body["date_range"] == {
        "first_delivery_day": "2026-01-15",
        "last_delivery_day": "2026-01-16",
        "timezone": "Europe/London",
    }
    assert body["defaults"] == {
        "start": "2026-01-15",
        "end": "2026-01-16",
        "mode": "day_ahead",
        "gate_time": "09:00:00",
        "horizon_h": 24.0,
    }
    assert body["limits"] == {"horizon_h_min": 0.0, "horizon_h_max": 48.0}
    assert body["snapshot"]["snapshot_id"] == "test-snapshot"


def test_openapi_docs_are_served(client):
    assert client.get("/api/docs").status_code == 200
    paths = client.get("/api/openapi.json").json()["paths"]
    assert {
        "/api/health",
        "/api/meta",
        "/api/series",
        "/api/metrics",
        "/api/metrics/by-horizon",
        "/api/metrics/by-hour",
    } <= set(paths)


# --- series --------------------------------------------------------------------------------


def test_series_defaults_to_day_ahead_over_whole_snapshot(client):
    body = client.get("/api/series").json()

    assert body["query"] == {
        "start": "2026-01-15",
        "end": "2026-01-16",
        "mode": "day_ahead",
        "horizon_h": None,
        "gate_time": "09:00:00",
        "cutoff_rule": "Latest forecast published by 09:00 Europe/London on the day before "
        "delivery.",
    }
    assert len(body["points"]) == 48
    assert body["points"][0] == {
        "target_time_utc": "2026-01-15T00:00:00Z",
        "cutoff_utc": "2026-01-14T09:00:00Z",
        "actual_mw": 900,
        "forecast_mw": 1000,
        "publish_time_utc": "2026-01-14T07:30:00Z",
        "lead_time_hours": 16.5,
        "error_mw": 100,
    }
    assert body["coverage"]["paired"] == 47


def test_series_keeps_slots_with_missing_actual(client):
    points = client.get("/api/series").json()["points"]

    missing = next(p for p in points if p["target_time_utc"] == MISSING_ACTUAL)
    assert missing["actual_mw"] is None
    assert missing["error_mw"] is None
    assert missing["forecast_mw"] == 1005


def test_series_date_subset(client):
    points = client.get("/api/series", params={"start": "2026-01-16", "end": "2026-01-16"}).json()[
        "points"
    ]

    assert len(points) == 24
    assert points[0]["target_time_utc"] == "2026-01-16T00:00:00Z"


def test_series_gate_time_changes_selected_publish(client):
    points = client.get("/api/series", params={"gate_time": "10:00"}).json()["points"]

    assert {p["forecast_mw"] for p in points} == {5000}
    assert points[0]["publish_time_utc"] == "2026-01-14T09:30:00Z"


def test_series_horizon_mode(client):
    body = client.get("/api/series", params={"mode": "horizon", "horizon_h": 0}).json()

    assert body["query"]["mode"] == "horizon"
    assert body["query"]["gate_time"] is None
    assert body["query"]["cutoff_rule"] == (
        "Latest forecast published at least 0 h before each slot."
    )
    assert {p["forecast_mw"] for p in body["points"]} == {5000}


def test_series_horizon_too_long_for_data_returns_nulls_not_errors(client):
    body = client.get("/api/series", params={"mode": "horizon", "horizon_h": 48}).json()

    assert len(body["points"]) == 48
    assert body["coverage"]["with_forecast"] == 0
    assert all(p["forecast_mw"] is None for p in body["points"])


# --- validation ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("params", "field", "message"),
    [
        ({"mode": "horizon"}, "horizon_h", "horizon_h is required when mode=horizon"),
        ({"mode": "horizon", "horizon_h": 49}, "horizon_h", "less than or equal to 48"),
        ({"mode": "horizon", "horizon_h": -1}, "horizon_h", "greater than or equal to 0"),
        ({"mode": "intraday"}, "mode", "'horizon' or 'day_ahead'"),
        ({"start": "2026-01-14"}, "start", "within the snapshot range 2026-01-15 to 2026-01-16"),
        ({"end": "2026-02-01"}, "end", "within the snapshot range"),
        ({"start": "2026-01-16", "end": "2026-01-15"}, "end", "must not be before start"),
        ({"start": "16/01/2026"}, "start", "valid date"),
        ({"gate_time": "25:00"}, "gate_time", "valid time"),
        ({"gate_time": "09:00+01:00"}, "gate_time", "omit the offset"),
        ({"horizon": 6}, "horizon", "Extra inputs are not permitted"),
    ],
)
def test_invalid_parameters_return_422_with_located_message(client, params, field, message):
    response = client.get("/api/series", params=params)

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(e["loc"] == ["query", field] and message in e["msg"] for e in errors), errors


def test_multiple_problems_are_reported_together(client):
    response = client.get("/api/metrics", params={"mode": "horizon", "start": "2025-01-01"})

    fields = {e["loc"][-1] for e in response.json()["detail"]}
    assert fields == {"start", "horizon_h"}


def test_by_horizon_only_accepts_a_date_range(client):
    response = client.get("/api/metrics/by-horizon", params={"mode": "horizon"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["query", "mode"]


# --- metrics -------------------------------------------------------------------------------


def test_metrics_summary(client):
    body = client.get("/api/metrics").json()

    # errors = 100 + hour over both days, minus the missing 05:00 slot on the 16th:
    # (2 * (24 * 100 + 276) - 105) / 47
    assert body["overall"]["n"] == 47
    assert body["overall"]["mae_mw"] == pytest.approx(5247 / 47)
    assert body["overall"]["bias_mw"] == pytest.approx(5247 / 47)
    assert body["coverage"]["pct_with_actual"] == pytest.approx(100 * 47 / 48)
    buffer = body["buffer"]
    assert [lvl["coverage"] for lvl in buffer["levels"]] == [0.9, 0.95]
    assert buffer["levels"][0]["message"].startswith("Buy ")
    assert buffer["levels"][0]["message"].endswith("covered in 90% of hours.")
    assert [d["delivery_date"] for d in body["by_day"]] == ["2026-01-15", "2026-01-16"]
    worst = body["worst_slots"][0]
    assert (worst["target_time_utc"], worst["error_mw"]) == ("2026-01-15T23:00:00Z", 123)


def test_metrics_by_hour(client):
    hours = client.get("/api/metrics/by-hour").json()["hours"]

    assert [h["hour_local"] for h in hours] == list(range(24))
    assert hours[5]["stats"]["n"] == 1  # one 05:00 actual is missing
    assert hours[5]["stats"]["mae_mw"] == 105
    assert hours[23]["stats"]["mae_mw"] == 123


def test_metrics_by_horizon(client):
    body = client.get("/api/metrics/by-horizon").json()

    assert (body["start"], body["end"]) == ("2026-01-15", "2026-01-16")
    points = {p["horizon_hours"]: p for p in body["points"]}
    assert sorted(points) == list(range(1, 49))
    assert points[1]["n"] == 47
    assert points[1]["mae_mw"] == 4100  # 09:30 publish (5000) vs 900 actual
    assert points[48]["n"] == 0
    assert points[48]["mae_mw"] is None


# --- cache / CORS / logging ----------------------------------------------------------------


def test_results_are_cached_across_endpoints(client, app):
    service = app.state.service

    client.get("/api/metrics")
    client.get("/api/series")
    client.get("/api/metrics/by-hour")
    client.get("/api/metrics", params={"gate_time": "10:00"})

    info = service.selection.cache_info()
    assert (info.misses, info.hits) == (2, 2)


def test_cors_allows_configured_origin_only(client):
    allowed = client.get("/api/health", headers={"Origin": ORIGIN})
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-origin" not in other.headers


def test_cors_disabled_when_no_origins(data_dir):
    client = TestClient(create_app(Settings(data_dir=data_dir, cors_origins=())))

    response = client.get("/api/health", headers={"Origin": ORIGIN})

    assert "access-control-allow-origin" not in response.headers


def test_request_id_is_returned_and_access_log_is_structured(client):
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    logging.getLogger("app").addHandler(handler)
    try:
        response = client.get("/api/meta", headers={"X-Request-ID": "abc123"})
        client.get("/api/health")  # healthcheck traffic is logged at DEBUG, filtered at INFO
    finally:
        logging.getLogger("app").removeHandler(handler)

    assert response.headers["X-Request-ID"] == "abc123"
    (record,) = [r for r in records if r.getMessage() == "request"]
    line = json.loads(JsonFormatter().format(record))
    assert line["request_id"] == "abc123"
    assert (line["level"], line["method"], line["path"]) == ("INFO", "GET", "/api/meta")
    assert line["status"] == 200
    assert line["duration_ms"] >= 0


def test_generated_request_id_when_none_sent(client):
    assert len(client.get("/api/health").headers["X-Request-ID"]) == 32


# --- configuration / snapshot integrity ----------------------------------------------------


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CORS_ORIGINS", " https://a.example , https://b.example ,")
    monkeypatch.setenv("CACHE_SIZE", "16")
    monkeypatch.setenv("LOG_LEVEL", "debug")

    settings = Settings.from_env()

    assert settings.data_dir == tmp_path
    assert settings.cors_origins == ("https://a.example", "https://b.example")
    assert (settings.cache_size, settings.log_level) == (16, "DEBUG")


def test_tampered_snapshot_is_rejected(data_dir):
    (data_dir / "actuals.parquet").write_bytes(b"not the file the manifest describes")

    with pytest.raises(SnapshotError, match="sha256"):
        create_app(Settings(data_dir=data_dir))


def test_missing_snapshot_is_rejected(tmp_path):
    with pytest.raises(SnapshotError, match="run scripts/build_snapshot.py"):
        create_app(Settings(data_dir=tmp_path))


# --- real snapshot + Vercel entrypoint -----------------------------------------------------


def test_real_snapshot_smoke():
    client = TestClient(create_app(Settings(data_dir=REPO_ROOT / "data")))

    body = client.get("/api/metrics").json()

    assert body["query"]["start"] == "2026-01-02"
    assert body["coverage"]["slots"] == 744
    assert body["coverage"]["paired"] == 744


def test_vercel_entrypoint_exposes_the_app():
    spec = importlib.util.spec_from_file_location("vercel_index", REPO_ROOT / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert isinstance(module.app, FastAPI)
    assert TestClient(module.app).get("/api/health").status_code == 200


def test_lead_time_series_uses_utc_z_suffix(client):
    first = client.get("/api/series").json()["points"][0]

    for key in ("target_time_utc", "cutoff_utc", "publish_time_utc"):
        assert first[key].endswith("Z")
        assert datetime.fromisoformat(first[key]).utcoffset() == timedelta(0)
