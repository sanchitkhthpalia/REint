"""Load the versioned data snapshot written by scripts/build_snapshot.py (DECISIONS D-002)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


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


def load_snapshot(data_dir: Path) -> Snapshot:
    manifest_path = data_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotError(f"no manifest at {manifest_path}; run scripts/build_snapshot.py")
    manifest = json.loads(manifest_path.read_text())

    frames = {}
    for name in ("actuals.parquet", "forecasts.parquet"):
        path = data_dir / name
        expected = manifest.get("files", {}).get(name, {}).get("sha256")
        if not path.is_file() or expected is None:
            raise SnapshotError(f"{name} missing from {data_dir} or from its manifest")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SnapshotError(f"{name} sha256 {actual} does not match manifest {expected}")
        frames[name] = pd.read_parquet(path)

    return Snapshot(
        actuals=frames["actuals.parquet"],
        forecasts=frames["forecasts.parquet"],
        manifest=manifest,
    )
