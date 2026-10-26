"""Computations behind the API, with an in-memory LRU cache.

The snapshot is immutable, so results depend only on the query and can be cached for the
life of the process. Cached DataFrames are shared between requests and must not be mutated.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import pandas as pd

from app.domain.metrics import LeadTimePoint, lead_time_curve
from app.domain.selection import DecisionRule, hourly_targets, select_forecasts
from app.ingest.scope import uk_midnight_utc
from app.snapshot import Snapshot


class AnalysisService:
    def __init__(self, snapshot: Snapshot, cache_size: int) -> None:
        self.snapshot = snapshot
        self.selection = lru_cache(maxsize=cache_size)(self._selection)
        self.lead_time_curve = lru_cache(maxsize=cache_size)(self._lead_time_curve)

    @staticmethod
    def targets(start: date, end: date) -> pd.DatetimeIndex:
        """Hourly target slots for UK delivery days start..end inclusive."""
        return hourly_targets(uk_midnight_utc(start), uk_midnight_utc(end + timedelta(days=1)))

    def _selection(self, start: date, end: date, rule: DecisionRule) -> pd.DataFrame:
        return select_forecasts(
            self.targets(start, end), self.snapshot.forecasts, self.snapshot.actuals, rule
        )

    def _lead_time_curve(self, start: date, end: date) -> tuple[LeadTimePoint, ...]:
        return lead_time_curve(
            self.targets(start, end), self.snapshot.forecasts, self.snapshot.actuals
        )

    def cache_info(self) -> dict[str, dict[str, Any]]:
        return {
            name: fn.cache_info()._asdict()
            for name, fn in (
                ("selection", self.selection),
                ("lead_time_curve", self.lead_time_curve),
            )
        }
