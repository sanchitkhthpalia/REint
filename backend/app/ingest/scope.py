"""Which date ranges to download for a set of delivery days. Pure, no I/O.

See docs/DECISIONS.md (D-001, D-005) and docs/DATA_NOTES.md section 5.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

# Decisions made on D-1 during January 2026 -> delivery days 2 Jan .. 1 Feb 2026.
DEFAULT_FIRST_DELIVERY_DAY = date(2026, 1, 2)
DEFAULT_LAST_DELIVERY_DAY = date(2026, 2, 1)

# A WINDFOR publish on day X covers startTimes up to X+2 21:00 UK, so D-1 publishes
# cover delivery day D. Three days of lookback adds margin in case D-1 has no publish
# before the cutoff. Forecasts published after a slot's cutoff are excluded later.
DEFAULT_FORECAST_LOOKBACK_DAYS = 3


def uk_midnight_utc(day: date) -> datetime:
    """Start of a UK local day, expressed in UTC."""
    return datetime.combine(day, time(0), tzinfo=UK_TZ).astimezone(UTC)


@dataclass(frozen=True)
class SnapshotScope:
    first_delivery_day: date = DEFAULT_FIRST_DELIVERY_DAY
    last_delivery_day: date = DEFAULT_LAST_DELIVERY_DAY
    forecast_lookback_days: int = DEFAULT_FORECAST_LOOKBACK_DAYS

    def __post_init__(self) -> None:
        if self.last_delivery_day < self.first_delivery_day:
            raise ValueError("last_delivery_day is before first_delivery_day")
        if self.forecast_lookback_days < 1:
            raise ValueError("forecast_lookback_days must be >= 1 (decisions are made on D-1)")

    @property
    def settlement_dates(self) -> tuple[date, date]:
        """Inclusive FUELHH settlementDate range. Settlement days are UK local days."""
        return self.first_delivery_day, self.last_delivery_day

    @property
    def delivery_window_utc(self) -> tuple[datetime, datetime]:
        """Half-open [start, end) UTC window covering every delivery slot."""
        return (
            uk_midnight_utc(self.first_delivery_day),
            uk_midnight_utc(self.last_delivery_day + timedelta(days=1)),
        )

    @property
    def forecast_publish_window_utc(self) -> tuple[datetime, datetime]:
        """WINDFOR publishTime range: from lookback before the first delivery day to the end
        of the delivery window. Day-ahead mode only needs publishes up to D-1, but horizon
        mode with small H needs publishes made during the delivery day itself."""
        return (
            uk_midnight_utc(self.first_delivery_day - timedelta(days=self.forecast_lookback_days)),
            self.delivery_window_utc[1],
        )
