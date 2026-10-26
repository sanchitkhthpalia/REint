"""Pure functions turning raw Elexon stream rows into typed, deduplicated records.

Native resolution is preserved: actuals stay half-hourly, forecasts stay hourly. Aligning
them (match on the hourly grid, docs/DECISIONS.md D-003) is a domain step, so the snapshot
stays lossless. Here we only report forecast rows that are off the hourly grid.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError, field_validator

WIND = "WIND"

RawRow = Mapping[str, Any]


class NormalizationError(ValueError):
    """Raw data cannot be normalized without guessing."""


class _Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Actual(_Record):
    start_time_utc: AwareDatetime
    generation_mw: int

    @field_validator("start_time_utc")
    @classmethod
    def _as_utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC)


class Forecast(_Record):
    start_time_utc: AwareDatetime
    publish_time_utc: AwareDatetime
    generation_mw: int

    @field_validator("start_time_utc", "publish_time_utc")
    @classmethod
    def _as_utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC)


class ActualsResult(_Record):
    records: tuple[Actual, ...]
    rows_in: int
    non_wind_dropped: int
    duplicates_removed: int


class ForecastsResult(_Record):
    records: tuple[Forecast, ...]
    rows_in: int
    duplicates_removed: int
    off_hour_rows: int


# Raw row shapes, validated before conversion. Unknown fields (dataset, settlementDate...)
# are ignored.
class _RawFuelhh(BaseModel):
    publish_time: AwareDatetime = Field(alias="publishTime")
    start_time: AwareDatetime = Field(alias="startTime")
    generation: int


class _RawWindfor(BaseModel):
    publish_time: AwareDatetime = Field(alias="publishTime")
    start_time: AwareDatetime = Field(alias="startTime")
    generation: int


def _validate[M: BaseModel](model: type[M], row: RawRow, dataset: str, index: int) -> M:
    try:
        return model.model_validate(row)
    except ValidationError as e:
        raise NormalizationError(f"{dataset} row {index} is invalid: {row!r}\n{e}") from e


def normalize_actuals(raw: Sequence[RawRow]) -> ActualsResult:
    """FUELHH rows -> one Actual per startTime, WIND only, sorted by startTime.

    Revisions: the row with the latest publishTime wins. Exact duplicates are dropped.
    Two rows with the same startTime and publishTime but different generation raise,
    because neither can be preferred without guessing.
    """
    latest: dict[datetime, tuple[datetime, Actual]] = {}
    non_wind = 0
    duplicates = 0
    for i, row in enumerate(raw):
        if row.get("fuelType") != WIND:
            non_wind += 1
            continue
        parsed = _validate(_RawFuelhh, row, "FUELHH", i)
        actual = Actual(start_time_utc=parsed.start_time, generation_mw=parsed.generation)
        published = parsed.publish_time.astimezone(UTC)
        current = latest.get(actual.start_time_utc)
        if current is None:
            latest[actual.start_time_utc] = (published, actual)
            continue
        duplicates += 1
        current_published, current_actual = current
        if published > current_published:
            latest[actual.start_time_utc] = (published, actual)
        elif published == current_published and actual != current_actual:
            raise NormalizationError(
                f"FUELHH conflicting rows for startTime {actual.start_time_utc.isoformat()} "
                f"with the same publishTime {published.isoformat()}: "
                f"{current_actual.generation_mw} MW vs {actual.generation_mw} MW"
            )
    records = tuple(sorted((a for _, a in latest.values()), key=lambda a: a.start_time_utc))
    return ActualsResult(
        records=records,
        rows_in=len(raw),
        non_wind_dropped=non_wind,
        duplicates_removed=duplicates,
    )


def normalize_forecasts(raw: Sequence[RawRow]) -> ForecastsResult:
    """WINDFOR rows -> Forecasts unique on (publishTime, startTime), sorted by both.

    Every publish is kept: choosing which forecast was available at decision time is the
    domain layer's job. Exact duplicates (e.g. from overlapping fetch chunks) are dropped;
    conflicting duplicates raise.
    """
    unique: dict[tuple[datetime, datetime], Forecast] = {}
    duplicates = 0
    for i, row in enumerate(raw):
        parsed = _validate(_RawWindfor, row, "WINDFOR", i)
        forecast = Forecast(
            start_time_utc=parsed.start_time,
            publish_time_utc=parsed.publish_time,
            generation_mw=parsed.generation,
        )
        key = (forecast.publish_time_utc, forecast.start_time_utc)
        existing = unique.get(key)
        if existing is None:
            unique[key] = forecast
            continue
        if existing != forecast:
            raise NormalizationError(
                f"WINDFOR conflicting rows for publishTime {key[0].isoformat()} "
                f"startTime {key[1].isoformat()}: "
                f"{existing.generation_mw} MW vs {forecast.generation_mw} MW"
            )
        duplicates += 1
    records = tuple(unique[k] for k in sorted(unique))
    off_hour = sum(1 for f in records if not _on_the_hour(f.start_time_utc))
    return ForecastsResult(
        records=records,
        rows_in=len(raw),
        duplicates_removed=duplicates,
        off_hour_rows=off_hour,
    )


def _on_the_hour(t: datetime) -> bool:
    return t.minute == 0 and t.second == 0 and t.microsecond == 0


def missing_slots(
    start_times: Iterable[datetime], window_start: datetime, window_end: datetime, step: timedelta
) -> list[datetime]:
    """Grid points in the half-open UTC window [window_start, window_end) with no start time."""
    present = {t.astimezone(UTC) for t in start_times}
    missing = []
    t = window_start.astimezone(UTC)
    end = window_end.astimezone(UTC)
    while t < end:
        if t not in present:
            missing.append(t)
        t += step
    return missing
