"""Select the forecast that was available at decision time for each target slot.

Core rule (CLAUDE.md section 3): for target slot T, use the forecast with the latest
publishTime <= cutoff(T). Anything published after the cutoff is lookahead and is never used.
The cutoff depends on the decision rule:

- HorizonRule:  cutoff = T - H hours (absolute elapsed time, unaffected by clock changes).
- DayAheadRule: cutoff = gate time on D-1 in Europe/London, where D is T's UK delivery day.

Slots with no eligible forecast or no actual are kept and flagged, never dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum

import numpy as np
import pandas as pd

UK_TZ = "Europe/London"
DEFAULT_GATE_TIME = time(9, 0)  # Assumption, see docs/DECISIONS.md D-007
MAX_HORIZON_HOURS = 48.0
TS_UNIT = "us"

OUTPUT_COLUMNS = [
    "target_time_utc",
    "cutoff_utc",
    "publish_time_utc",
    "lead_time_hours",
    "forecast_mw",
    "actual_mw",
    "error_mw",
    "has_forecast",
    "has_actual",
]


class Mode(StrEnum):
    HORIZON = "horizon"
    DAY_AHEAD = "day_ahead"


@dataclass(frozen=True)
class HorizonRule:
    """Forecast must be published at least `hours` before the target slot starts."""

    hours: float

    def __post_init__(self) -> None:
        if not 0 <= self.hours <= MAX_HORIZON_HOURS:
            raise ValueError(f"horizon must be between 0 and {MAX_HORIZON_HOURS:g} hours")

    @property
    def mode(self) -> Mode:
        return Mode.HORIZON

    def cutoffs(self, targets: pd.Series) -> pd.Series:
        return targets - pd.Timedelta(hours=self.hours)


@dataclass(frozen=True)
class DayAheadRule:
    """Forecast must be published by the gate time on the day before the UK delivery day."""

    gate_time: time = DEFAULT_GATE_TIME
    timezone: str = UK_TZ

    def __post_init__(self) -> None:
        if self.gate_time.tzinfo is not None:
            raise ValueError("gate_time is a local wall-clock time; pass it without tzinfo")

    @property
    def mode(self) -> Mode:
        return Mode.DAY_AHEAD

    def cutoffs(self, targets: pd.Series) -> pd.Series:
        # Work in naive local wall-clock time so "D-1" is a calendar day, not 24 hours.
        delivery_day = targets.dt.tz_convert(self.timezone).dt.tz_localize(None).dt.normalize()
        gate = pd.Timedelta(
            hours=self.gate_time.hour,
            minutes=self.gate_time.minute,
            seconds=self.gate_time.second,
        )
        local_cutoff = delivery_day - pd.Timedelta(days=1) + gate
        # A gate time that falls in a clock change resolves to the earlier instant, so the
        # cutoff errs towards less information, never lookahead: ambiguous -> first
        # occurrence (DST side), non-existent -> just before the gap.
        return local_cutoff.dt.tz_localize(
            self.timezone,
            ambiguous=np.ones(len(local_cutoff), dtype=bool),
            nonexistent="shift_backward",
        ).dt.tz_convert("UTC")


DecisionRule = HorizonRule | DayAheadRule


def make_rule(
    mode: Mode | str,
    *,
    horizon_hours: float | None = None,
    gate_time: time = DEFAULT_GATE_TIME,
) -> DecisionRule:
    mode = Mode(mode)
    if mode is Mode.HORIZON:
        if horizon_hours is None:
            raise ValueError("horizon mode needs horizon_hours")
        return HorizonRule(horizon_hours)
    return DayAheadRule(gate_time)


def hourly_targets(window_start: datetime, window_end: datetime) -> pd.DatetimeIndex:
    """Hourly UTC target slots in [window_start, window_end), the grid WINDFOR uses (D-003)."""
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise ValueError("window bounds must be timezone-aware")
    return pd.date_range(
        window_start, window_end, freq="1h", inclusive="left", unit=TS_UNIT
    ).tz_convert("UTC")


def select_forecasts(
    targets: pd.DatetimeIndex | pd.Series,
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    rule: DecisionRule,
) -> pd.DataFrame:
    """One row per target slot with the forecast available at its cutoff and the actual.

    forecasts: columns publish_time_utc, start_time_utc, generation_mw (unique on the pair).
    actuals:   columns start_time_utc, generation_mw (unique on start_time_utc).
    Returns OUTPUT_COLUMNS sorted by target_time_utc; error_mw = forecast - actual.
    """
    slots = pd.DataFrame({"target_time_utc": _utc(pd.Series(targets), "targets")})
    if slots["target_time_utc"].duplicated().any():
        raise ValueError("targets contain duplicate slots")
    slots["cutoff_utc"] = rule.cutoffs(slots["target_time_utc"]).dt.as_unit(TS_UNIT)

    fc = pd.DataFrame(
        {
            "publish_time_utc": _utc(forecasts["publish_time_utc"], "forecasts.publish_time_utc"),
            "start_time_utc": _utc(forecasts["start_time_utc"], "forecasts.start_time_utc"),
            "forecast_mw": forecasts["generation_mw"].to_numpy(),
        }
    )
    if fc.duplicated(["publish_time_utc", "start_time_utc"]).any():
        raise ValueError("forecasts contain duplicate (publish_time_utc, start_time_utc) rows")

    act = pd.DataFrame(
        {
            "target_time_utc": _utc(actuals["start_time_utc"], "actuals.start_time_utc"),
            "actual_mw": actuals["generation_mw"].to_numpy(),
        }
    )
    if act["target_time_utc"].duplicated().any():
        raise ValueError("actuals contain duplicate start_time_utc rows")

    # Backward as-of join: per target slot, the last publish at or before its cutoff.
    selected = pd.merge_asof(
        slots.sort_values("cutoff_utc"),
        fc.sort_values("publish_time_utc"),
        left_on="cutoff_utc",
        right_on="publish_time_utc",
        left_by="target_time_utc",
        right_by="start_time_utc",
        direction="backward",
        allow_exact_matches=True,
    ).drop(columns="start_time_utc")

    out = selected.merge(act, on="target_time_utc", how="left", validate="one_to_one")
    out = out.sort_values("target_time_utc", ignore_index=True)

    out["forecast_mw"] = out["forecast_mw"].astype("Int64")
    out["actual_mw"] = out["actual_mw"].astype("Int64")
    out["error_mw"] = out["forecast_mw"] - out["actual_mw"]
    out["lead_time_hours"] = (
        (out["target_time_utc"] - out["publish_time_utc"]).dt.total_seconds() / 3600
    ).astype("Float64")
    out["has_forecast"] = out["publish_time_utc"].notna()
    out["has_actual"] = out["actual_mw"].notna()
    return out[OUTPUT_COLUMNS]


def _utc(values: pd.Series, name: str) -> pd.Series:
    """Validate timezone-aware timestamps and normalise to UTC at one resolution."""
    series = pd.Series(values).reset_index(drop=True)
    if not isinstance(series.dtype, pd.DatetimeTZDtype):
        raise ValueError(f"{name} must be timezone-aware datetimes, got dtype {series.dtype}")
    if series.isna().any():
        raise ValueError(f"{name} contains missing timestamps")
    return series.dt.tz_convert("UTC").dt.as_unit(TS_UNIT)
