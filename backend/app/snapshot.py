"""Load the versioned data snapshot written by scripts/build_snapshot.py (DECISIONS D-002).

The API reads the gzipped CSV serving copies with plain pandas, so pyarrow is not a runtime
dependency (D-013). The parquet archive copies hold the same data and are not read here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

SERVING_FILES = {
    "actuals.csv.gz": ("start_time_utc",),
    "forecasts.csv.gz": ("publish_time_utc", "start_time_utc"),
}
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class SnapshotError(RuntimeError):
    """The snapshot is missing, incomplete, or does not match its manifest."""


@dataclass(frozen=True)
class Snapshot:
    actuals: pd.DataFrame  # start_time_utc, generation_mw
    forecasts: pd.DataFrame  # publish_time_utc, start_time_utc, generation_mw
    manifest: dict[str, Any]

    @property
    def snapshot_id(self) -> str:
        return str(self.manifest["snapshot_id"])

    @property
    def first_delivery_day(self) -> date:
        return date.fromisoformat(self.manifest["scope"]["first_delivery_day"])

    @property
    def last_delivery_day(self) -> date:
        return date.fromisoformat(self.manifest["scope"]["last_delivery_day"])


def read_serving_table(path: Path, timestamp_columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"generation_mw": "int64"})
    for column in timestamp_columns:
        frame[column] = pd.to_datetime(frame[column], format=TIMESTAMP_FORMAT, utc=True)
    return frame


def load_snapshot(data_dir: Path) -> Snapshot:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotError(f"no manifest at {manifest_path}; run scripts/build_snapshot.py")
    manifest = json.loads(manifest_path.read_text())

    frames = {}
    for name, timestamp_columns in SERVING_FILES.items():
        path = data_dir / name
        expected = manifest.get("files", {}).get(name, {}).get("sha256")
        if not path.is_file() or expected is None:
            raise SnapshotError(f"{name} missing from {data_dir} or from its manifest")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SnapshotError(f"{name} sha256 {actual} does not match manifest {expected}")
        frames[name] = read_serving_table(path, timestamp_columns)

    return Snapshot(
        actuals=frames["actuals.csv.gz"],
        forecasts=frames["forecasts.csv.gz"],
        manifest=manifest,
    )
