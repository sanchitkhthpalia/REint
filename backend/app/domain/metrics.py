"""Forecast accuracy metrics on selected forecast/actual pairs (output of select_forecasts).

Sign convention (CLAUDE.md): error = forecast - actual. Positive error = over-forecast, meaning
wind fell short of the forecast and the utility must buy the difference.

Metric choices:
- MAE, RMSE and mean bias in MW are reported. nMAE = MAE / mean actual over the same pairs
  gives a scale-free figure.
- MAPE is deliberately not reported. It divides each error by that slot's actual, and GB wind
  output can approach zero on calm days. Near-zero actuals make individual percentage errors
  explode and dominate the average, so MAPE would describe calm hours rather than forecast
  skill. nMAE normalises once by the mean actual and stays stable.
- Descriptive percentiles use linear interpolation (numpy default).
- The procurement buffer is a coverage claim ("covered in 90% of slots"). It therefore uses
  the empirical-CDF percentile (numpy "inverted_cdf"): the smallest observed error E with
  P(error <= E) >= q. In-sample coverage is guaranteed even for small samples. The buffer is
  floored at 0: if over-forecasts are rare enough, no buffer is needed.

Only slots with both a forecast and an actual enter error metrics. Coverage reports the rest.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

import numpy as np
import pandas as pd
from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.domain.selection import (
    OUTPUT_COLUMNS,
    UK_TZ,
    DecisionRule,
    HorizonRule,
    select_forecasts,
)

DISTRIBUTION_PERCENTILES = (10, 50, 90, 95, 99)
BUFFER_COVERAGES = (0.90, 0.95)
DEFAULT_LEAD_TIME_HORIZONS = tuple(range(1, 49))
WORST_SLOTS = 10


# --- response models ---------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Coverage(_Model):
    slots: int
    with_forecast: int
    with_actual: int
    paired: int
    pct_with_forecast: float | None
    pct_with_actual: float | None
    pct_paired: float | None


class ErrorStats(_Model):
    """Error summary for a set of pairs. Values are None when there are no pairs."""

    n: int
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    mean_actual_mw: float | None
    nmae: float | None  # fraction, e.g. 0.12 = 12% of mean actual


class Percentiles(_Model):
    p10: float | None
    p50: float | None
    p90: float | None
    p95: float | None
    p99: float | None


class ErrorDistribution(_Model):
    signed_mw: Percentiles
    absolute_mw: Percentiles


class BufferLevel(_Model):
    coverage: float  # e.g. 0.9
    buffer_mw: float | None
    message: str


class ProcurementBuffer(_Model):
    levels: tuple[BufferLevel, ...]
    shortfall_share: float | None  # fraction of paired slots with error > 0
    slot_minutes: int | None
    method: str


class LeadTimePoint(_Model):
    horizon_hours: float
    n: int
    mean_lead_time_hours: float | None
    mae_mw: float | None
    p90_abs_error_mw: float | None
    buffer_p90_mw: float | None


class HourOfDayStats(_Model):
    hour_local: int  # 0-23, Europe/London
    stats: ErrorStats


class DayStats(_Model):
    delivery_date: date  # Europe/London delivery day
    stats: ErrorStats


class WorstSlot(_Model):
    target_time_utc: AwareDatetime
    publish_time_utc: AwareDatetime
    lead_time_hours: float
    forecast_mw: int
    actual_mw: int
    error_mw: int
    abs_error_mw: int


class MetricsReport(_Model):
    coverage: Coverage
    overall: ErrorStats
    distribution: ErrorDistribution
    buffer: ProcurementBuffer
    by_hour_of_day: tuple[HourOfDayStats, ...]
    by_day: tuple[DayStats, ...]
    worst_slots: tuple[WorstSlot, ...]
    lead_time_curve: tuple[LeadTimePoint, ...]


# --- building blocks ---------------------------------------------------------------------


def paired(selected: pd.DataFrame) -> pd.DataFrame:
    """Rows with both a forecast and an actual, i.e. the rows that have an error."""
    missing = set(OUTPUT_COLUMNS) - set(selected.columns)
    if missing:
        raise ValueError(f"selected frame is missing columns: {sorted(missing)}")
    return selected[selected["has_forecast"] & selected["has_actual"]]


def _floats(values: pd.Series) -> np.ndarray:
    return values.astype("float64").to_numpy()


def _pct(part: int, whole: int) -> float | None:
    return 100 * part / whole if whole else None


def coverage(selected: pd.DataFrame) -> Coverage:
    slots = len(selected)
    with_forecast = int(selected["has_forecast"].sum())
    with_actual = int(selected["has_actual"].sum())
    n_paired = len(paired(selected))
    return Coverage(
        slots=slots,
        with_forecast=with_forecast,
        with_actual=with_actual,
        paired=n_paired,
        pct_with_forecast=_pct(with_forecast, slots),
        pct_with_actual=_pct(with_actual, slots),
        pct_paired=_pct(n_paired, slots),
    )


def error_stats(selected: pd.DataFrame) -> ErrorStats:
    pairs = paired(selected)
    if pairs.empty:
        return ErrorStats(
            n=0, mae_mw=None, rmse_mw=None, bias_mw=None, mean_actual_mw=None, nmae=None
        )
    err = _floats(pairs["error_mw"])
    mean_actual = float(_floats(pairs["actual_mw"]).mean())
    mae = float(np.abs(err).mean())
    return ErrorStats(
        n=len(err),
        mae_mw=mae,
        rmse_mw=float(np.sqrt(np.mean(err**2))),
        bias_mw=float(err.mean()),
        mean_actual_mw=mean_actual,
        nmae=mae / mean_actual if mean_actual > 0 else None,
    )


def _percentiles(values: np.ndarray) -> Percentiles:
    if values.size == 0:
        return Percentiles(p10=None, p50=None, p90=None, p95=None, p99=None)
    p = np.percentile(values, DISTRIBUTION_PERCENTILES)
    return Percentiles(
        **{f"p{q}": float(v) for q, v in zip(DISTRIBUTION_PERCENTILES, p, strict=True)}
    )


def error_distribution(selected: pd.DataFrame) -> ErrorDistribution:
    err = _floats(paired(selected)["error_mw"])
    return ErrorDistribution(signed_mw=_percentiles(err), absolute_mw=_percentiles(np.abs(err)))


def _buffer_mw(err: np.ndarray, coverage_level: float) -> float | None:
    if err.size == 0:
        return None
    return max(0.0, float(np.quantile(err, coverage_level, method="inverted_cdf")))


def _slot_minutes(selected: pd.DataFrame) -> int | None:
    times = selected["target_time_utc"].sort_values()
    if len(times) < 2:
        return None
    return int(times.diff().dropna().min().total_seconds() // 60)


def _slot_word(minutes: int | None) -> str:
    return {30: "half-hours", 60: "hours"}.get(minutes, "slots") if minutes else "slots"


def procurement_buffer(
    selected: pd.DataFrame, coverages: Sequence[float] = BUFFER_COVERAGES
) -> ProcurementBuffer:
    err = _floats(paired(selected)["error_mw"])
    minutes = _slot_minutes(selected)
    word = _slot_word(minutes)
    levels = []
    for level in coverages:
        mw = _buffer_mw(err, level)
        message = (
            f"Buy {mw:,.0f} MW above the forecast-implied need to be covered in "
            f"{level:.0%} of {word}."
            if mw is not None
            else "Not enough paired data to size a buffer."
        )
        levels.append(BufferLevel(coverage=level, buffer_mw=mw, message=message))
    return ProcurementBuffer(
        levels=tuple(levels),
        shortfall_share=float((err > 0).mean()) if err.size else None,
        slot_minutes=minutes,
        method="empirical quantile (inverted CDF) of signed error over all paired slots, "
        "floored at 0",
    )


def by_hour_of_day(selected: pd.DataFrame) -> tuple[HourOfDayStats, ...]:
    hours = selected["target_time_utc"].dt.tz_convert(UK_TZ).dt.hour
    return tuple(
        HourOfDayStats(hour_local=int(hour), stats=error_stats(group))
        for hour, group in selected.groupby(hours, sort=True)
    )


def by_day(selected: pd.DataFrame) -> tuple[DayStats, ...]:
    days = selected["target_time_utc"].dt.tz_convert(UK_TZ).dt.date
    return tuple(
        DayStats(delivery_date=day, stats=error_stats(group))
        for day, group in selected.groupby(days, sort=True)
    )


def worst_slots(selected: pd.DataFrame, n: int = WORST_SLOTS) -> tuple[WorstSlot, ...]:
    pairs = paired(selected).assign(abs_error_mw=lambda d: d["error_mw"].abs())
    # Ties broken by time so the list is deterministic.
    top = pairs.sort_values(["abs_error_mw", "target_time_utc"], ascending=[False, True]).head(n)
    return tuple(
        WorstSlot(
            target_time_utc=row.target_time_utc,
            publish_time_utc=row.publish_time_utc,
            lead_time_hours=float(row.lead_time_hours),
            forecast_mw=int(row.forecast_mw),
            actual_mw=int(row.actual_mw),
            error_mw=int(row.error_mw),
            abs_error_mw=int(row.abs_error_mw),
        )
        for row in top.itertuples()
    )


def lead_time_curve(
    targets: pd.DatetimeIndex,
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    horizons: Iterable[float] = DEFAULT_LEAD_TIME_HORIZONS,
) -> tuple[LeadTimePoint, ...]:
    """Re-run selection in horizon mode for each H: how accuracy decays with lead time."""
    points = []
    for h in horizons:
        pairs = paired(select_forecasts(targets, forecasts, actuals, HorizonRule(h)))
        err = _floats(pairs["error_mw"])
        has_pairs = err.size > 0
        points.append(
            LeadTimePoint(
                horizon_hours=h,
                n=err.size,
                mean_lead_time_hours=float(_floats(pairs["lead_time_hours"]).mean())
                if has_pairs
                else None,
                mae_mw=float(np.abs(err).mean()) if has_pairs else None,
                p90_abs_error_mw=float(np.percentile(np.abs(err), 90)) if has_pairs else None,
                buffer_p90_mw=_buffer_mw(err, 0.90),
            )
        )
    return tuple(points)


def metrics_report(
    targets: pd.DatetimeIndex,
    forecasts: pd.DataFrame,
    actuals: pd.DataFrame,
    rule: DecisionRule,
    lead_time_horizons: Iterable[float] = DEFAULT_LEAD_TIME_HORIZONS,
) -> MetricsReport:
    """Everything the UI needs for one decision rule over one set of target slots."""
    selected = select_forecasts(targets, forecasts, actuals, rule)
    return MetricsReport(
        coverage=coverage(selected),
        overall=error_stats(selected),
        distribution=error_distribution(selected),
        buffer=procurement_buffer(selected),
        by_hour_of_day=by_hour_of_day(selected),
        by_day=by_day(selected),
        worst_slots=worst_slots(selected),
        lead_time_curve=lead_time_curve(targets, forecasts, actuals, lead_time_horizons),
    )
