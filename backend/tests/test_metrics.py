"""Metrics tests on tiny datasets with hand-computed expected values (worked in comments)."""

import math
from datetime import date

import pandas as pd
import pytest

from app.domain.metrics import (
    DEFAULT_LEAD_TIME_HORIZONS,
    by_day,
    by_hour_of_day,
    coverage,
    error_distribution,
    error_stats,
    lead_time_curve,
    paired,
    procurement_buffer,
    worst_slots,
)
from app.domain.selection import HorizonRule, select_forecasts


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value)


def frames(
    rows: list[tuple[str, int | None, int | None]],
) -> tuple[pd.DatetimeIndex, pd.DataFrame, pd.DataFrame]:
    """rows: (target_time, forecast_mw or None, actual_mw or None).

    Each forecast is published exactly at its target time, so HorizonRule(0) selects it.
    """
    targets = pd.DatetimeIndex(pd.to_datetime([r[0] for r in rows], utc=True))
    fc_rows = [(t, f) for t, f, _ in rows if f is not None]
    act_rows = [(t, a) for t, _, a in rows if a is not None]
    fc_times = pd.to_datetime([t for t, _ in fc_rows], utc=True)
    forecasts = pd.DataFrame(
        {
            "publish_time_utc": fc_times,
            "start_time_utc": fc_times,
            "generation_mw": pd.Series([f for _, f in fc_rows], dtype="int64"),
        }
    )
    actuals = pd.DataFrame(
        {
            "start_time_utc": pd.to_datetime([t for t, _ in act_rows], utc=True),
            "generation_mw": pd.Series([a for _, a in act_rows], dtype="int64"),
        }
    )
    return targets, forecasts, actuals


def selected(rows: list[tuple[str, int | None, int | None]]) -> pd.DataFrame:
    return select_forecasts(*frames(rows), HorizonRule(0))


# Dataset A: 5 paired hourly slots, plus one slot without forecast and one without actual.
#   actual   = [1000, 500, 800, 700, 1000]
#   error    = [ 100, -50, 200,   0, -150]   (forecast = actual + error)
DATASET_A = [
    ("2026-01-16T00:00Z", 1100, 1000),
    ("2026-01-16T01:00Z", 450, 500),
    ("2026-01-16T02:00Z", 1000, 800),
    ("2026-01-16T03:00Z", 700, 700),
    ("2026-01-16T04:00Z", 850, 1000),
    ("2026-01-16T05:00Z", None, 900),  # no forecast
    ("2026-01-16T06:00Z", 10, None),  # no actual
]


@pytest.fixture
def sel_a() -> pd.DataFrame:
    return selected(DATASET_A)


# --- coverage ------------------------------------------------------------------------------


def test_coverage_counts_all_slots(sel_a):
    cov = coverage(sel_a)

    assert (cov.slots, cov.with_forecast, cov.with_actual, cov.paired) == (7, 6, 6, 5)
    assert cov.share_with_forecast == pytest.approx(6 / 7)
    assert cov.share_with_actual == pytest.approx(6 / 7)
    assert cov.share_paired == pytest.approx(5 / 7)


def test_coverage_of_empty_selection_has_no_percentages():
    cov = coverage(selected([]))

    assert cov.slots == 0
    assert cov.share_with_forecast is None


# --- overall stats -------------------------------------------------------------------------


def test_error_stats_hand_computed(sel_a):
    stats = error_stats(sel_a)

    assert stats.n == 5
    assert stats.mae_mw == pytest.approx(100.0)  # (100+50+200+0+150)/5
    assert stats.rmse_mw == pytest.approx(math.sqrt(15000))  # sqrt(75000/5)
    assert stats.bias_mw == pytest.approx(20.0)  # (100-50+200+0-150)/5
    assert stats.mean_actual_mw == pytest.approx(800.0)  # 4000/5
    assert stats.nmae == pytest.approx(0.125)  # 100/800


def test_nmae_is_undefined_when_mean_actual_is_zero():
    # Calm conditions: actual 0 MW. A per-slot percentage error (MAPE) would divide by zero.
    stats = error_stats(selected([("2026-01-16T00:00Z", 50, 0)]))

    assert stats.mae_mw == 50
    assert stats.nmae is None


def test_error_stats_without_pairs_are_none():
    stats = error_stats(selected([("2026-01-16T00:00Z", None, 900)]))

    assert stats.n == 0
    assert stats.mae_mw is stats.rmse_mw is stats.bias_mw is stats.nmae is None


# --- distribution --------------------------------------------------------------------------


def test_percentiles_hand_computed_with_linear_interpolation(sel_a):
    dist = error_distribution(sel_a)

    # signed sorted [-150, -50, 0, 100, 200]; position = p * (n - 1) = p * 4
    assert dist.signed_mw.p10 == pytest.approx(-110)  # -150 + 0.4 * 100
    assert dist.signed_mw.p50 == pytest.approx(0)
    assert dist.signed_mw.p90 == pytest.approx(160)  # 100 + 0.6 * 100
    assert dist.signed_mw.p95 == pytest.approx(180)  # 100 + 0.8 * 100
    assert dist.signed_mw.p99 == pytest.approx(196)  # 100 + 0.96 * 100
    # absolute sorted [0, 50, 100, 150, 200]
    assert dist.absolute_mw.p10 == pytest.approx(20)
    assert dist.absolute_mw.p50 == pytest.approx(100)
    assert dist.absolute_mw.p90 == pytest.approx(180)
    assert dist.absolute_mw.p95 == pytest.approx(190)
    assert dist.absolute_mw.p99 == pytest.approx(198)


def test_percentiles_without_pairs_are_none():
    dist = error_distribution(selected([]))

    assert dist.signed_mw.p90 is None
    assert dist.absolute_mw.p50 is None


# --- procurement buffer --------------------------------------------------------------------


def test_buffer_uses_empirical_quantile_and_guarantees_coverage():
    # 10 hourly slots, errors sorted: [-100, -50, 0, 10, 20, 30, 40, 50, 60, 500]
    errors = [-100, -50, 0, 10, 20, 30, 40, 50, 60, 500]
    rows = [(f"2026-01-16T{i:02d}:00Z", 1000 + e, 1000) for i, e in enumerate(errors)]

    buffer = procurement_buffer(selected(rows))

    p90, p95 = buffer.levels
    # P90: smallest error E with share(error <= E) >= 0.9 -> 60 (9 of 10 slots covered).
    # Linear interpolation would give 104, which over-states what the data needs.
    assert (p90.coverage, p90.buffer_mw) == (0.9, 60)
    assert (p95.coverage, p95.buffer_mw) == (0.95, 500)  # needs 9.5 of 10 -> all 10
    assert sum(e <= p90.buffer_mw for e in errors) / len(errors) >= 0.9
    assert buffer.shortfall_share == pytest.approx(0.7)  # 7 of 10 errors > 0
    assert buffer.slot_minutes == 60
    assert p90.message == (
        "Buy 60 MW above the forecast-implied need to be covered in 90% of hours."
    )
    assert p95.message == (
        "Buy 500 MW above the forecast-implied need to be covered in 95% of hours."
    )


def test_buffer_on_dataset_a(sel_a):
    buffer = procurement_buffer(sel_a)

    # sorted [-150, -50, 0, 100, 200]: share(<=100) = 0.8 < 0.9, share(<=200) = 1.0
    assert [lvl.buffer_mw for lvl in buffer.levels] == [200, 200]
    assert buffer.shortfall_share == pytest.approx(0.4)


def test_buffer_is_zero_when_forecasts_never_over_forecast():
    rows = [(f"2026-01-16T{i:02d}:00Z", 900, 1000) for i in range(5)]  # always -100

    p90, _ = procurement_buffer(selected(rows)).levels

    assert p90.buffer_mw == 0
    assert p90.message.startswith("Buy 0 MW above")


def test_buffer_message_names_half_hours_on_a_half_hourly_grid():
    rows = [("2026-01-16T00:00Z", 1100, 1000), ("2026-01-16T00:30Z", 1050, 1000)]

    buffer = procurement_buffer(selected(rows))

    assert buffer.slot_minutes == 30
    assert buffer.levels[0].message.endswith("covered in 90% of half-hours.")


def test_buffer_with_large_values_uses_thousands_separator():
    p90, _ = procurement_buffer(selected([("2026-01-16T00:00Z", 3500, 1000)])).levels

    assert p90.buffer_mw == 2500
    assert (
        p90.message == "Buy 2,500 MW above the forecast-implied need to be covered in 90% of slots."
    )


def test_buffer_without_pairs():
    buffer = procurement_buffer(selected([("2026-01-16T00:00Z", None, 900)]))

    assert buffer.levels[0].buffer_mw is None
    assert buffer.levels[0].message == "Not enough paired data to size a buffer."
    assert buffer.shortfall_share is None
    assert buffer.slot_minutes is None


# --- by hour of day / by day ---------------------------------------------------------------


def test_by_hour_of_day_uses_uk_local_time():
    sel = selected(
        [
            ("2026-01-15T13:00Z", 1010, 1000),  # 13:00 GMT -> hour 13, error +10
            ("2026-06-15T12:00Z", 1030, 1000),  # 13:00 BST -> hour 13, error +30
            ("2026-06-15T13:00Z", 980, 1000),  # 14:00 BST -> hour 14, error -20
        ]
    )

    result = {h.hour_local: h.stats for h in by_hour_of_day(sel)}

    assert sorted(result) == [13, 14]
    assert (result[13].n, result[13].mae_mw, result[13].bias_mw) == (2, 20, 20)
    assert (result[14].n, result[14].mae_mw, result[14].bias_mw) == (1, 20, -20)


def test_by_day_uses_uk_delivery_day_and_keeps_days_without_pairs():
    sel = selected(
        [
            ("2026-06-14T22:00Z", 1100, 1000),  # 23:00 BST on 14 Jun, error +100
            ("2026-06-14T23:00Z", 900, 1000),  # 00:00 BST on 15 Jun, error -100
            ("2026-06-15T23:00Z", None, 1000),  # 00:00 BST on 16 Jun, no forecast
        ]
    )

    days = by_day(sel)

    assert [d.delivery_date for d in days] == [
        date(2026, 6, 14),
        date(2026, 6, 15),
        date(2026, 6, 16),
    ]
    assert [d.stats.bias_mw for d in days] == [100, -100, None]
    assert days[2].stats.n == 0


# --- worst slots ---------------------------------------------------------------------------


def test_worst_slots_sorted_by_abs_error_with_time_tiebreak():
    errors = [1, -2, 3, -4, 5, -6, 7, -8, 9, -10, 11, -11]
    rows = [(f"2026-01-16T{i:02d}:00Z", 1000 + e, 1000) for i, e in enumerate(errors)]

    worst = worst_slots(selected(rows))

    assert len(worst) == 10
    assert [w.error_mw for w in worst] == [11, -11, -10, 9, -8, 7, -6, 5, -4, 3]
    assert [w.abs_error_mw for w in worst] == [11, 11, 10, 9, 8, 7, 6, 5, 4, 3]
    first = worst[0]
    assert first.target_time_utc == ts("2026-01-16T10:00Z")  # +11 is earlier than -11
    assert first.publish_time_utc == ts("2026-01-16T10:00Z")
    assert (first.forecast_mw, first.actual_mw, first.lead_time_hours) == (1011, 1000, 0.0)


def test_worst_slots_ignore_unpaired_slots(sel_a):
    worst = worst_slots(sel_a)

    assert len(worst) == 5
    assert worst[0].error_mw == 200


# --- lead time curve -----------------------------------------------------------------------


def test_lead_time_curve_hand_computed():
    t1, t2 = "2026-01-16T12:00Z", "2026-01-16T13:00Z"
    targets = pd.DatetimeIndex(pd.to_datetime([t1, t2], utc=True))
    forecasts = pd.DataFrame(
        {
            "publish_time_utc": pd.to_datetime(
                [
                    "2026-01-16T09:00Z",
                    "2026-01-16T11:00Z",
                    "2026-01-16T10:00Z",
                    "2026-01-16T12:00Z",
                ],
                utc=True,
            ),
            "start_time_utc": pd.to_datetime([t1, t1, t2, t2], utc=True),
            "generation_mw": [1300, 1100, 2400, 1900],  # errors: +300, +100, +400, -100
        }
    )
    actuals = pd.DataFrame(
        {"start_time_utc": pd.to_datetime([t1, t2], utc=True), "generation_mw": [1000, 2000]}
    )

    h1, h2, h3, h4 = lead_time_curve(targets, forecasts, actuals, horizons=[1, 2, 3, 4])

    # H=1: t1 <- 11:00 (+100), t2 <- 12:00 (-100); leads 1h
    assert (h1.n, h1.mean_lead_time_hours, h1.mae_mw) == (2, 1.0, 100)
    assert h1.p90_abs_error_mw == pytest.approx(100)
    assert h1.buffer_p90_mw == 100
    # H=2: t1 <- 09:00 (+300), t2 <- 10:00 (+400); leads 3h; accuracy decays
    assert (h2.n, h2.mean_lead_time_hours, h2.mae_mw) == (2, 3.0, 350)
    assert h2.p90_abs_error_mw == pytest.approx(390)  # 300 + 0.9 * 100
    assert h2.buffer_p90_mw == 400
    # H=3: same publishes as H=2 (cutoffs land exactly on them)
    assert (h3.n, h3.mae_mw) == (2, 350)
    # H=4: nothing published early enough
    assert h4.n == 0
    assert h4.mae_mw is h4.mean_lead_time_hours is h4.p90_abs_error_mw is h4.buffer_p90_mw is None


def test_default_lead_time_sweep_is_1_to_48_hours():
    sweep = DEFAULT_LEAD_TIME_HORIZONS
    assert (sweep[0], sweep[-1], len(sweep)) == (1, 48, 48)


# --- walk-forward buffer check -------------------------------------------------------------


def _days(errors_by_day: dict[str, list[int]]) -> pd.DataFrame:
    rows = [
        (f"{day}T{hour:02d}:00Z", 1000 + e, 1000)
        for day, errors in errors_by_day.items()
        for hour, e in enumerate(errors)
    ]
    return selected(rows)


def test_walk_forward_sizes_each_day_from_earlier_days_only():
    sel = _days(
        {
            "2026-01-16": [10, 20, 30, 40],  # history only
            "2026-01-17": [5, 50],
            "2026-01-18": [100, 0],
        }
    )

    buffer = procurement_buffer(sel, coverages=(0.5,), min_history_days=1)

    # 17 Jan: median of [10, 20, 30, 40] (inverted CDF) = 20 -> covers 5, misses 50.
    # 18 Jan: median of [5, 10, 20, 30, 40, 50] = 20 -> covers 0, misses 100.
    (level,) = buffer.levels
    assert level.walk_forward_coverage == pytest.approx(2 / 4)
    assert buffer.walk_forward_days == 2
    # In-sample over all 8 slots: sorted [0, 5, 10, 20, 30, 40, 50, 100] -> 20 covers 4 of 8.
    assert level.buffer_mw == 20


def test_walk_forward_never_uses_the_day_being_scored():
    # If the scored day leaked into its own buffer, the 1,000 MW miss would be covered.
    sel = _days({"2026-01-16": [10, 10], "2026-01-17": [1000]})

    (level,) = procurement_buffer(sel, coverages=(0.9,), min_history_days=1).levels

    assert level.walk_forward_coverage == 0.0


def test_walk_forward_needs_enough_history():
    sel = _days({"2026-01-16": [10], "2026-01-17": [20]})

    buffer = procurement_buffer(sel, min_history_days=7)

    assert buffer.walk_forward_days == 0
    assert all(lvl.walk_forward_coverage is None for lvl in buffer.levels)


def test_paired_requires_selection_columns():
    with pytest.raises(ValueError, match="missing columns"):
        paired(pd.DataFrame({"error_mw": [1]}))
