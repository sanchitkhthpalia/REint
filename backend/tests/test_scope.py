from datetime import UTC, date, datetime

import pytest

from app.ingest.scope import SnapshotScope


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_default_scope_matches_data_notes():
    scope = SnapshotScope()

    assert scope.settlement_dates == (date(2026, 1, 2), date(2026, 2, 1))
    assert scope.delivery_window_utc == (utc(2026, 1, 2), utc(2026, 2, 2))
    assert scope.forecast_publish_window_utc == (utc(2025, 12, 30), utc(2026, 2, 1))


def test_bst_scope_uses_uk_local_midnight():
    scope = SnapshotScope(date(2026, 6, 15), date(2026, 6, 15))

    assert scope.delivery_window_utc == (utc(2026, 6, 14, 23), utc(2026, 6, 15, 23))


def test_invalid_scopes_are_rejected():
    with pytest.raises(ValueError):
        SnapshotScope(date(2026, 2, 1), date(2026, 1, 2))
    with pytest.raises(ValueError):
        SnapshotScope(forecast_lookback_days=0)
