"""Query parameter and response models for the HTTP API."""

from __future__ import annotations

from datetime import date, time
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.metrics import (
    Coverage,
    DayStats,
    ErrorDistribution,
    ErrorStats,
    HourOfDayStats,
    LeadTimePoint,
    ProcurementBuffer,
    WorstSlot,
)
from app.domain.selection import DEFAULT_GATE_TIME, MAX_HORIZON_HOURS, Mode

# --- query parameters ----------------------------------------------------------------------


class RangeQuery(BaseModel):
    """Delivery-day range (Europe/London, inclusive). Defaults to the whole snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start: date | None = Field(None, description="First UK delivery day, YYYY-MM-DD.")
    end: date | None = Field(None, description="Last UK delivery day (inclusive), YYYY-MM-DD.")


class AnalysisQuery(RangeQuery):
    mode: Mode = Field(
        Mode.DAY_AHEAD,
        description="day_ahead: latest forecast published by gate_time on D-1 (UK). "
        "horizon: latest forecast published at least horizon_h hours before each slot.",
    )
    horizon_h: float | None = Field(
        None,
        ge=0,
        le=MAX_HORIZON_HOURS,
        description="Hours between publish and slot start. Required when mode=horizon.",
    )
    gate_time: time = Field(
        DEFAULT_GATE_TIME,
        description="Day-ahead decision gate, Europe/London wall-clock time, HH:MM.",
    )


# --- responses -----------------------------------------------------------------------------


class _Response(BaseModel):
    model_config = ConfigDict(frozen=True)


class QueryEcho(_Response):
    start: date
    end: date
    mode: Mode
    horizon_h: float | None
    gate_time: time | None
    cutoff_rule: str


class HealthResponse(_Response):
    status: str
    snapshot_id: str
    cache: dict[str, dict[str, Any]]


class DateRange(_Response):
    first_delivery_day: date
    last_delivery_day: date
    timezone: str


class Defaults(_Response):
    start: date
    end: date
    mode: Mode
    gate_time: time
    horizon_h: float


class Limits(_Response):
    horizon_h_min: float
    horizon_h_max: float


class MetaResponse(_Response):
    date_range: DateRange
    defaults: Defaults
    limits: Limits
    snapshot: dict[str, Any]


class SeriesPoint(_Response):
    target_time_utc: AwareDatetime
    cutoff_utc: AwareDatetime
    actual_mw: int | None
    forecast_mw: int | None
    publish_time_utc: AwareDatetime | None
    lead_time_hours: float | None
    error_mw: int | None


class SeriesResponse(_Response):
    query: QueryEcho
    coverage: Coverage
    points: tuple[SeriesPoint, ...]


class MetricsResponse(_Response):
    query: QueryEcho
    coverage: Coverage
    overall: ErrorStats
    distribution: ErrorDistribution
    buffer: ProcurementBuffer
    by_day: tuple[DayStats, ...]
    worst_slots: tuple[WorstSlot, ...]


class ByHourResponse(_Response):
    query: QueryEcho
    hours: tuple[HourOfDayStats, ...]


class ByHorizonResponse(_Response):
    start: date
    end: date
    points: tuple[LeadTimePoint, ...]
