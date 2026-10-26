"""Lookahead audit on the real January snapshot.

Re-derives every selection with a deliberately naive loop (no pandas joins) and checks that
the vectorised implementation picks exactly the same forecast, and never one published after
its cutoff, for every hourly slot under several decision rules.
"""

from collections import defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.domain.selection import DayAheadRule, HorizonRule, hourly_targets, select_forecasts
from app.ingest.scope import SnapshotScope, uk_midnight_utc
from app.snapshot import load_snapshot

UK = ZoneInfo("Europe/London")
DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def snapshot():
    return load_snapshot(DATA_DIR)


@pytest.fixture(scope="module")
def forecasts_by_slot(snapshot) -> dict[datetime, list[tuple[datetime, int]]]:
    by_slot = defaultdict(list)
    frame = snapshot.forecasts[["publish_time_utc", "start_time_utc", "generation_mw"]]
    for published, start, mw in frame.itertuples(index=False):
        by_slot[start.to_pydatetime()].append((published.to_pydatetime(), int(mw)))
    return by_slot


def naive_cutoff(target: datetime, rule: DayAheadRule | HorizonRule) -> datetime:
    if isinstance(rule, HorizonRule):
        return target - timedelta(hours=rule.hours)
    decision_day = target.astimezone(UK).date() - timedelta(days=1)
    return datetime.combine(decision_day, rule.gate_time, tzinfo=UK)


@pytest.mark.parametrize(
    "rule",
    [
        DayAheadRule(),
        DayAheadRule(time(9, 50)),
        DayAheadRule(time(12, 30)),  # straddles the late 12:25 publish on 15 Jan
        HorizonRule(0),
        HorizonRule(6.5),
        HorizonRule(48),
    ],
    ids=str,
)
def test_selection_matches_naive_reference_on_real_data(snapshot, forecasts_by_slot, rule):
    scope = SnapshotScope(snapshot.first_delivery_day, snapshot.last_delivery_day)
    targets = hourly_targets(*scope.delivery_window_utc)
    assert targets[0] == uk_midnight_utc(snapshot.first_delivery_day)

    selected = select_forecasts(targets, snapshot.forecasts, snapshot.actuals, rule)

    problems = []
    for row in selected.itertuples():
        target = row.target_time_utc.to_pydatetime()
        cutoff = naive_cutoff(target, rule)
        eligible = [f for f in forecasts_by_slot[target] if f[0] <= cutoff]
        expected = max(eligible) if eligible else None
        got = (
            None
            if pd.isna(row.publish_time_utc)
            else (row.publish_time_utc.to_pydatetime(), int(row.forecast_mw))
        )
        if got != expected or (got is not None and got[0] > cutoff):
            problems.append((target, cutoff, expected, got))

    assert len(selected) == 744
    assert problems == []
