"""Download the decision scope from Elexon and write a versioned snapshot to data/.

Writes data/actuals.parquet, data/forecasts.parquet and data/manifest.json. The app serves
from this snapshot (docs/DECISIONS.md D-002), so it never depends on Elexon at request time.

Usage (from the repo root, with the backend installed: pip install -e "backend[dev]"):
    python scripts/build_snapshot.py
    python scripts/build_snapshot.py --first-delivery-day 2026-01-01 --last-delivery-day 2026-01-31
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from app.ingest.elexon_client import BASE_URL, ElexonClient, RequestRecord
from app.ingest.normalize import (
    ActualsResult,
    ForecastsResult,
    missing_slots,
    normalize_actuals,
    normalize_forecasts,
)
from app.ingest.scope import SnapshotScope

SCHEMA_VERSION = 1
REPO_ROOT = Path(__file__).resolve().parent.parent
UTC_TS = pa.timestamp("us", tz="UTC")

ACTUALS_SCHEMA = pa.schema([("start_time_utc", UTC_TS), ("generation_mw", pa.int64())])
FORECASTS_SCHEMA = pa.schema(
    [
        ("publish_time_utc", UTC_TS),
        ("start_time_utc", UTC_TS),
        ("generation_mw", pa.int64()),
    ]
)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def write_parquet(table: pa.Table, path: Path) -> dict[str, Any]:
    pq.write_table(table, path, compression="zstd")
    return {
        "rows": table.num_rows,
        "columns": {f.name: str(f.type) for f in table.schema},
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def quality_summary(
    scope: SnapshotScope, actuals: ActualsResult, forecasts: ForecastsResult
) -> dict[str, Any]:
    window_start, window_end = scope.delivery_window_utc
    missing_actuals = missing_slots(
        (a.start_time_utc for a in actuals.records),
        window_start,
        window_end,
        timedelta(minutes=30),
    )
    # Hourly delivery slots that no downloaded publish covers at all. This ignores the
    # decision cutoff and only checks that the download range is wide enough.
    missing_forecast_hours = missing_slots(
        (f.start_time_utc for f in forecasts.records),
        window_start,
        window_end,
        timedelta(hours=1),
    )
    publishes = Counter(f.publish_time_utc for f in forecasts.records)
    return {
        "actuals": {
            "raw_rows": actuals.rows_in,
            "non_wind_rows_dropped": actuals.non_wind_dropped,
            "duplicates_removed": actuals.duplicates_removed,
            "expected_half_hour_slots": len(actuals.records) + len(missing_actuals),
            "missing_slots": [iso(t) for t in missing_actuals],
        },
        "forecasts": {
            "raw_rows": forecasts.rows_in,
            "duplicates_removed": forecasts.duplicates_removed,
            "off_hour_rows": forecasts.off_hour_rows,
            "publish_count": len(publishes),
            "rows_per_publish": dict(Counter(publishes.values())),
            "off_schedule_publish_times": sorted(iso(p) for p in publishes if p.minute != 30),
            "delivery_hours_without_any_forecast": [iso(t) for t in missing_forecast_hours],
        },
    }


def requests_summary(records: list[RequestRecord]) -> list[dict[str, Any]]:
    return [{**asdict(r), "params": dict(r.params)} for r in records]


async def build(scope: SnapshotScope, out_dir: Path) -> dict[str, Any]:
    fetched_at = datetime.now(UTC)
    async with ElexonClient() as fuelhh_client, ElexonClient() as windfor_client:
        raw_actuals, raw_forecasts = await asyncio.gather(
            fuelhh_client.fetch_fuelhh(*scope.settlement_dates),
            windfor_client.fetch_windfor(*scope.forecast_publish_window_utc),
        )

    actuals = normalize_actuals(raw_actuals)
    forecasts = normalize_forecasts(raw_forecasts)
    if forecasts.off_hour_rows:
        # Alignment (D-003) assumes hourly forecasts. Fail loudly instead of mis-aligning.
        raise SystemExit(
            f"{forecasts.off_hour_rows} WINDFOR rows are not on the hour; "
            "revisit D-003 in docs/DECISIONS.md before building a snapshot."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    actuals_table = pa.Table.from_pylist(
        [a.model_dump() for a in actuals.records], schema=ACTUALS_SCHEMA
    )
    forecasts_table = pa.Table.from_pylist(
        [f.model_dump(include=set(FORECASTS_SCHEMA.names)) for f in forecasts.records],
        schema=FORECASTS_SCHEMA,
    )
    files = {
        "actuals.parquet": write_parquet(actuals_table, out_dir / "actuals.parquet"),
        "forecasts.parquet": write_parquet(forecasts_table, out_dir / "forecasts.parquet"),
    }
    content_hash = hashlib.sha256(
        "".join(files[name]["sha256"] for name in sorted(files)).encode()
    ).hexdigest()

    window_start, window_end = scope.delivery_window_utc
    publish_from, publish_to = scope.forecast_publish_window_utc
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": content_hash[:16],
        "fetched_at_utc": iso(fetched_at),
        "source": {
            "base_url": BASE_URL,
            "datasets": ["FUELHH (fuelType=WIND)", "WINDFOR"],
            "notes": "docs/DATA_NOTES.md",
        },
        "scope": {
            "first_delivery_day": scope.first_delivery_day.isoformat(),
            "last_delivery_day": scope.last_delivery_day.isoformat(),
            "delivery_window_utc": [iso(window_start), iso(window_end)],
            "fuelhh_settlement_dates": [d.isoformat() for d in scope.settlement_dates],
            "windfor_publish_window_utc": [iso(publish_from), iso(publish_to)],
            "forecast_lookback_days": scope.forecast_lookback_days,
        },
        "requests": {
            "fuelhh": requests_summary(fuelhh_client.requests),
            "windfor": requests_summary(windfor_client.requests),
        },
        "files": files,
        "data_quality": quality_summary(scope, actuals, forecasts),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    default = SnapshotScope()
    parser.add_argument(
        "--first-delivery-day", type=date.fromisoformat, default=default.first_delivery_day
    )
    parser.add_argument(
        "--last-delivery-day", type=date.fromisoformat, default=default.last_delivery_day
    )
    parser.add_argument(
        "--forecast-lookback-days", type=int, default=default.forecast_lookback_days
    )
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "data")
    args = parser.parse_args()

    scope = SnapshotScope(
        args.first_delivery_day, args.last_delivery_day, args.forecast_lookback_days
    )
    manifest = asyncio.run(build(scope, args.out))

    quality = manifest["data_quality"]
    print(f"snapshot {manifest['snapshot_id']} written to {args.out}")
    for name, info in manifest["files"].items():
        print(f"  {name}: {info['rows']} rows")
    print(json.dumps(quality, indent=2))
    if (
        quality["actuals"]["missing_slots"]
        or quality["forecasts"]["delivery_hours_without_any_forecast"]
    ):
        print("WARNING: data gaps found; see data/manifest.json", file=sys.stderr)


if __name__ == "__main__":
    main()
