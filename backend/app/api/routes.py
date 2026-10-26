"""API routes. Thin: validate the request, call the cached service and domain functions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError

from app.api.schemas import (
    AnalysisQuery,
    ByHorizonResponse,
    ByHourResponse,
    DateRange,
    Defaults,
    HealthResponse,
    Limits,
    MetaResponse,
    MetricsResponse,
    QueryEcho,
    RangeQuery,
    SeriesPoint,
    SeriesResponse,
)
from app.domain import metrics
from app.domain.selection import (
    DEFAULT_GATE_TIME,
    MAX_HORIZON_HOURS,
    UK_TZ,
    DayAheadRule,
    DecisionRule,
    Mode,
    make_rule,
)
from app.service import AnalysisService

DEFAULT_HORIZON_H = 24.0  # suggested starting value for the UI's horizon slider

router = APIRouter(prefix="/api")


def get_service(request: Request) -> AnalysisService:
    return request.app.state.service


Service = Annotated[AnalysisService, Depends(get_service)]


@dataclass(frozen=True)
class Analysis:
    start: date
    end: date
    rule: DecisionRule

    def echo(self) -> QueryEcho:
        if isinstance(self.rule, DayAheadRule):
            gate = self.rule.gate_time.strftime("%H:%M")
            return QueryEcho(
                start=self.start,
                end=self.end,
                mode=Mode.DAY_AHEAD,
                horizon_h=None,
                gate_time=self.rule.gate_time,
                cutoff_rule=f"Latest forecast published by {gate} {UK_TZ} on the day "
                "before delivery.",
            )
        return QueryEcho(
            start=self.start,
            end=self.end,
            mode=Mode.HORIZON,
            horizon_h=self.rule.hours,
            gate_time=None,
            cutoff_rule=f"Latest forecast published at least {self.rule.hours:g} h before "
            "each slot.",
        )


def _query_error(field: str, msg: str, value: object) -> dict[str, object]:
    """One error in FastAPI's standard 422 format, located at the offending parameter."""
    return {"type": "value_error", "loc": ("query", field), "msg": msg, "input": value}


def _range(
    service: AnalysisService, start: date | None, end: date | None
) -> tuple[date, date, list[dict[str, object]]]:
    first, last = service.snapshot.first_delivery_day, service.snapshot.last_delivery_day
    start = start or first
    end = end or last
    errors = [
        _query_error(name, f"{name} must be within the snapshot range {first} to {last}", str(v))
        for name, v in (("start", start), ("end", end))
        if not first <= v <= last
    ]
    if not errors and start > end:
        errors.append(
            _query_error("end", f"end ({end}) must not be before start ({start})", str(end))
        )
    return start, end, errors


def range_params(q: Annotated[RangeQuery, Query()], service: Service) -> tuple[date, date]:
    start, end, errors = _range(service, q.start, q.end)
    if errors:
        raise RequestValidationError(errors)
    return start, end


def analysis_params(q: Annotated[AnalysisQuery, Query()], service: Service) -> Analysis:
    start, end, errors = _range(service, q.start, q.end)
    if q.mode is Mode.HORIZON and q.horizon_h is None:
        errors.append(
            _query_error("horizon_h", "horizon_h is required when mode=horizon (0 to 48)", None)
        )
    if q.gate_time.tzinfo is not None:
        errors.append(
            _query_error(
                "gate_time",
                "gate_time is a Europe/London wall-clock time (HH:MM); omit the offset",
                q.gate_time.isoformat(),
            )
        )
    if errors:
        raise RequestValidationError(errors)
    rule = make_rule(q.mode, horizon_hours=q.horizon_h, gate_time=q.gate_time)
    return Analysis(start, end, rule)


AnalysisParams = Annotated[Analysis, Depends(analysis_params)]


def _selected(service: AnalysisService, a: Analysis) -> pd.DataFrame:
    return service.selection(a.start, a.end, a.rule)


@router.get("/health", response_model=HealthResponse)
def health(service: Service) -> HealthResponse:
    return HealthResponse(
        status="ok", snapshot_id=service.snapshot.snapshot_id, cache=service.cache_info()
    )


@router.get("/meta", response_model=MetaResponse)
def meta(service: Service) -> MetaResponse:
    snap = service.snapshot
    return MetaResponse(
        date_range=DateRange(
            first_delivery_day=snap.first_delivery_day,
            last_delivery_day=snap.last_delivery_day,
            timezone=UK_TZ,
        ),
        defaults=Defaults(
            start=snap.first_delivery_day,
            end=snap.last_delivery_day,
            mode=Mode.DAY_AHEAD,
            gate_time=DEFAULT_GATE_TIME,
            horizon_h=DEFAULT_HORIZON_H,
        ),
        limits=Limits(horizon_h_min=0, horizon_h_max=MAX_HORIZON_HOURS),
        snapshot=snap.manifest,
    )


@router.get("/series", response_model=SeriesResponse)
def series(service: Service, a: AnalysisParams) -> SeriesResponse:
    """Per hourly slot: actual, the forecast available at the cutoff, its publish time,
    lead time and error (forecast - actual). Missing values are null, never dropped."""
    selected = _selected(service, a)
    rows = selected.astype(object).where(selected.notna(), None).to_dict("records")
    return SeriesResponse(
        query=a.echo(),
        coverage=metrics.coverage(selected),
        points=tuple(SeriesPoint.model_validate(row, from_attributes=False) for row in rows),
    )


@router.get("/metrics", response_model=MetricsResponse)
def summary_metrics(service: Service, a: AnalysisParams) -> MetricsResponse:
    """Accuracy summary and procurement buffer recommendation for the selected forecasts."""
    selected = _selected(service, a)
    return MetricsResponse(
        query=a.echo(),
        coverage=metrics.coverage(selected),
        overall=metrics.error_stats(selected),
        distribution=metrics.error_distribution(selected),
        buffer=metrics.procurement_buffer(selected),
        by_day=metrics.by_day(selected),
        worst_slots=metrics.worst_slots(selected),
    )


@router.get("/metrics/by-horizon", response_model=ByHorizonResponse)
def by_horizon(
    service: Service, date_range: Annotated[tuple[date, date], Depends(range_params)]
) -> ByHorizonResponse:
    """Lead-time decay curve: horizon mode re-run for H = 1..48 h."""
    start, end = date_range
    return ByHorizonResponse(start=start, end=end, points=service.lead_time_curve(start, end))


@router.get("/metrics/by-hour", response_model=ByHourResponse)
def by_hour(service: Service, a: AnalysisParams) -> ByHourResponse:
    """Error statistics by hour of day (Europe/London)."""
    return ByHourResponse(query=a.echo(), hours=metrics.by_hour_of_day(_selected(service, a)))
