from datetime import UTC, datetime, time

import pandas as pd
import pytest

from app.domain.selection import (
    OUTPUT_COLUMNS,
    DayAheadRule,
    HorizonRule,
    Mode,
    hourly_targets,
    make_rule,
    select_forecasts,
)


def ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value)


def targets(*values: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(list(values), utc=True))


def forecasts(*rows: tuple[str, str, int]) -> pd.DataFrame:
    """rows: (publish_time, start_time, generation_mw)"""
    publish, start, mw = zip(*rows, strict=True) if rows else ((), (), ())
    return pd.DataFrame(
        {
            "publish_time_utc": pd.to_datetime(list(publish), utc=True),
            "start_time_utc": pd.to_datetime(list(start), utc=True),
            "generation_mw": pd.Series(list(mw), dtype="int64"),
        }
    )


def actuals(*rows: tuple[str, int]) -> pd.DataFrame:
    start, mw = zip(*rows, strict=True) if rows else ((), ())
    return pd.DataFrame(
        {
            "start_time_utc": pd.to_datetime(list(start), utc=True),
            "generation_mw": pd.Series(list(mw), dtype="int64"),
        }
    )


NO_ACTUALS = actuals()
T = "2026-01-16T00:00Z"  # delivery day 16 Jan (GMT), default cutoff 2026-01-15 09:00Z


# --- day-ahead cutoff boundary -------------------------------------------------------------


def test_forecast_published_one_minute_after_cutoff_is_not_selected():
    fc = forecasts(
        ("2026-01-15T07:30Z", T, 100),
        ("2026-01-15T09:01Z", T, 999),  # one minute after the 09:00 gate
    )

    (row,) = select_forecasts(targets(T), fc, NO_ACTUALS, DayAheadRule()).itertuples()

    assert row.cutoff_utc == ts("2026-01-15T09:00Z")
    assert row.publish_time_utc == ts("2026-01-15T07:30Z")
    assert row.forecast_mw == 100


def test_forecast_published_exactly_at_cutoff_is_selected():
    fc = forecasts(("2026-01-15T07:30Z", T, 100), ("2026-01-15T09:00Z", T, 200))

    (row,) = select_forecasts(targets(T), fc, NO_ACTUALS, DayAheadRule()).itertuples()

    assert row.publish_time_utc == ts("2026-01-15T09:00Z")
    assert row.forecast_mw == 200


def test_latest_eligible_forecast_wins_over_earlier_ones():
    fc = forecasts(
        ("2026-01-15T07:30Z", T, 300),
        ("2026-01-14T22:30Z", T, 100),
        ("2026-01-15T04:30Z", T, 200),
        ("2026-01-15T09:30Z", T, 999),  # after the cutoff
        ("2026-01-16T02:30Z", T, 999),  # after the slot itself (restated past slot)
    )

    (row,) = select_forecasts(targets(T), fc, NO_ACTUALS, DayAheadRule()).itertuples()

    assert row.publish_time_utc == ts("2026-01-15T07:30Z")
    assert row.forecast_mw == 300


def test_selection_only_uses_forecasts_for_the_same_target_slot():
    t2 = "2026-01-16T01:00Z"
    fc = forecasts(
        ("2026-01-15T04:30Z", T, 100),
        ("2026-01-15T07:30Z", t2, 200),  # newer, but for a different slot
    )

    out = select_forecasts(targets(T, t2), fc, NO_ACTUALS, DayAheadRule())

    assert out["forecast_mw"].tolist() == [100, 200]
    assert out["publish_time_utc"].tolist() == [ts("2026-01-15T04:30Z"), ts("2026-01-15T07:30Z")]


def test_whole_delivery_day_shares_one_cutoff():
    out = select_forecasts(
        targets("2026-01-16T00:00Z", "2026-01-16T23:00Z", "2026-01-17T00:00Z"),
        forecasts(),
        NO_ACTUALS,
        DayAheadRule(),
    )

    assert out["cutoff_utc"].tolist() == [
        ts("2026-01-15T09:00Z"),
        ts("2026-01-15T09:00Z"),
        ts("2026-01-16T09:00Z"),
    ]


@pytest.mark.parametrize(
    ("gate", "expected_publish", "expected_mw"),
    [
        (time(9, 0), None, None),  # both publishes are after 09:00
        (time(10, 0), "2026-01-15T09:30Z", [7472, 7039, 6716]),
        (time(12, 30), "2026-01-15T12:25Z", [7449, 7152, 6908]),  # the late publish
    ],
)
def test_gate_time_is_configurable_on_real_windfor_rows(
    windfor, gate, expected_publish, expected_mw
):
    fc = pd.DataFrame(
        {
            "publish_time_utc": pd.to_datetime([r["publishTime"] for r in windfor], utc=True),
            "start_time_utc": pd.to_datetime([r["startTime"] for r in windfor], utc=True),
            "generation_mw": [r["generation"] for r in windfor],
        }
    )
    slots = targets("2026-01-16T00:00Z", "2026-01-16T01:00Z", "2026-01-16T02:00Z")

    out = select_forecasts(slots, fc, NO_ACTUALS, DayAheadRule(gate))

    if expected_publish is None:
        assert not out["has_forecast"].any()
    else:
        assert (out["publish_time_utc"] == ts(expected_publish)).all()
        assert out["forecast_mw"].tolist() == expected_mw


# --- outputs -------------------------------------------------------------------------------


def test_lead_time_and_error_sign():
    t2 = "2026-01-16T01:00Z"
    fc = forecasts(("2026-01-15T07:30Z", T, 7000), ("2026-01-15T07:30Z", t2, 6000))
    act = actuals((T, 6500), ("2026-01-16T00:30Z", 1), (t2, 6400))

    out = select_forecasts(targets(T, t2), fc, act, DayAheadRule())

    assert out["lead_time_hours"].tolist() == [16.5, 17.5]
    assert out["actual_mw"].tolist() == [6500, 6400]  # half-hour actual is not a target
    # error = forecast - actual; positive = over-forecast (utility short of wind)
    assert out["error_mw"].tolist() == [500, -400]


def test_output_has_one_row_per_target_sorted_with_stable_columns():
    unsorted = targets("2026-01-16T02:00Z", T, "2026-01-16T01:00Z")

    out = select_forecasts(unsorted, forecasts(), NO_ACTUALS, DayAheadRule())

    assert list(out.columns) == OUTPUT_COLUMNS
    assert out["target_time_utc"].is_monotonic_increasing
    assert len(out) == 3
    assert str(out["target_time_utc"].dt.tz) == "UTC"


def test_non_utc_inputs_are_normalised_to_utc():
    local_target = pd.DatetimeIndex([pd.Timestamp("2026-06-15 13:00", tz="Europe/London")])
    fc = forecasts(("2026-06-14T07:30Z", "2026-06-15T12:00Z", 500))

    (row,) = select_forecasts(local_target, fc, NO_ACTUALS, DayAheadRule()).itertuples()

    assert row.target_time_utc == ts("2026-06-15T12:00Z")
    assert row.forecast_mw == 500


# --- missing data flags --------------------------------------------------------------------


def test_slots_without_forecast_or_actual_are_kept_and_flagged():
    t_ok, t_no_fc, t_no_act, t_none = (
        "2026-01-16T00:00Z",
        "2026-01-16T01:00Z",
        "2026-01-16T02:00Z",
        "2026-01-16T03:00Z",
    )
    fc = forecasts(
        ("2026-01-15T07:30Z", t_ok, 100),
        ("2026-01-15T09:30Z", t_no_fc, 999),  # only published after the cutoff
        ("2026-01-15T07:30Z", t_no_act, 300),
    )
    act = actuals((t_ok, 90), (t_no_fc, 200))

    out = select_forecasts(targets(t_ok, t_no_fc, t_no_act, t_none), fc, act, DayAheadRule())

    assert len(out) == 4
    assert out["has_forecast"].tolist() == [True, False, True, False]
    assert out["has_actual"].tolist() == [True, True, False, False]
    assert out["error_mw"].isna().tolist() == [False, True, True, True]
    assert out.loc[0, "error_mw"] == 10
    missing_fc = out.loc[1]
    assert pd.isna(missing_fc["publish_time_utc"])
    assert pd.isna(missing_fc["forecast_mw"])
    assert pd.isna(missing_fc["lead_time_hours"])
    assert missing_fc["actual_mw"] == 200


def test_no_forecasts_at_all_flags_every_slot():
    out = select_forecasts(targets(T), forecasts(), actuals((T, 5)), DayAheadRule())

    assert out["has_forecast"].tolist() == [False]
    assert out["has_actual"].tolist() == [True]


# --- DST / timezone correctness --------------------------------------------------------------


def test_day_ahead_cutoff_around_spring_clock_change():
    # Clocks go forward 2026-03-29 01:00Z (01:00 GMT -> 02:00 BST).
    out = select_forecasts(
        targets(
            "2026-03-29T00:00Z",  # 00:00 GMT on 29 Mar -> D-1 = 28 Mar (GMT)
            "2026-03-29T22:00Z",  # 23:00 BST on 29 Mar -> D-1 = 28 Mar (GMT)
            "2026-03-29T23:00Z",  # 00:00 BST on 30 Mar -> D-1 = 29 Mar (BST)
        ),
        forecasts(),
        NO_ACTUALS,
        DayAheadRule(),
    )

    assert out["cutoff_utc"].tolist() == [
        ts("2026-03-28T09:00Z"),
        ts("2026-03-28T09:00Z"),
        ts("2026-03-29T08:00Z"),  # 09:00 BST
    ]


def test_utc_gate_would_leak_a_forecast_that_uk_gate_excludes():
    # Target 2026-03-29T23:00Z is 00:00 BST on 30 Mar. Cutoff is 09:00 BST on 29 Mar = 08:00Z.
    # A forecast published 08:30Z (09:30 BST) is after the real gate even though it is
    # before 09:00 UTC; a UTC-based implementation would wrongly select it.
    t = "2026-03-29T23:00Z"
    fc = forecasts(("2026-03-29T06:30Z", t, 100), ("2026-03-29T08:30Z", t, 999))

    (row,) = select_forecasts(targets(t), fc, NO_ACTUALS, DayAheadRule()).itertuples()

    assert row.forecast_mw == 100


def test_day_ahead_cutoff_around_autumn_clock_change():
    # Clocks go back 2026-10-25 01:00Z (02:00 BST -> 01:00 GMT).
    out = select_forecasts(
        targets(
            "2026-10-24T23:00Z",  # 00:00 BST on 25 Oct -> D-1 = 24 Oct (BST)
            "2026-10-25T23:00Z",  # 23:00 GMT on 25 Oct -> D-1 = 24 Oct (BST)
            "2026-10-26T00:00Z",  # 00:00 GMT on 26 Oct -> D-1 = 25 Oct (GMT)
        ),
        forecasts(),
        NO_ACTUALS,
        DayAheadRule(),
    )

    assert out["cutoff_utc"].tolist() == [
        ts("2026-10-24T08:00Z"),
        ts("2026-10-24T08:00Z"),
        ts("2026-10-25T09:00Z"),
    ]


def test_ambiguous_gate_time_resolves_to_earlier_instant():
    # 01:30 on 25 Oct 2026 happens twice (00:30Z BST, then 01:30Z GMT). Use the earlier one.
    out = select_forecasts(
        targets("2026-10-26T12:00Z"), forecasts(), NO_ACTUALS, DayAheadRule(time(1, 30))
    )

    assert out.loc[0, "cutoff_utc"] == ts("2026-10-25T00:30Z")


def test_nonexistent_gate_time_resolves_to_just_before_the_gap():
    # 01:30 on 29 Mar 2026 does not exist (01:00 GMT jumps to 02:00 BST).
    out = select_forecasts(
        targets("2026-03-30T12:00Z"), forecasts(), NO_ACTUALS, DayAheadRule(time(1, 30))
    )

    cutoff = out.loc[0, "cutoff_utc"]
    assert ts("2026-03-29T00:59Z") < cutoff < ts("2026-03-29T01:00Z")


def test_horizon_is_absolute_elapsed_time_across_clock_change():
    out = select_forecasts(targets("2026-03-29T12:00Z"), forecasts(), NO_ACTUALS, HorizonRule(24))

    assert out.loc[0, "cutoff_utc"] == ts("2026-03-28T12:00Z")


# --- horizon mode --------------------------------------------------------------------------


def test_horizon_mode_requires_publish_at_least_h_hours_before_target():
    fc = forecasts(
        ("2026-01-15T18:00Z", T, 100),  # exactly T - 6h: eligible
        ("2026-01-15T18:01Z", T, 999),  # T - 5h59m: too late
    )

    (row,) = select_forecasts(targets(T), fc, NO_ACTUALS, HorizonRule(6)).itertuples()

    assert row.cutoff_utc == ts("2026-01-15T18:00Z")
    assert row.forecast_mw == 100
    assert row.lead_time_hours == 6.0


def test_horizon_zero_allows_publish_at_target_time_but_not_after():
    fc = forecasts(
        ("2026-01-15T22:30Z", T, 100),
        ("2026-01-16T00:00Z", T, 200),  # published exactly at T
        ("2026-01-16T00:01Z", T, 999),  # after T (WINDFOR restates past slots)
    )

    (row,) = select_forecasts(targets(T), fc, NO_ACTUALS, HorizonRule(0)).itertuples()

    assert row.forecast_mw == 200
    assert row.lead_time_hours == 0.0


def test_fractional_horizon():
    fc = forecasts(("2026-01-15T22:30Z", T, 100), ("2026-01-15T22:31Z", T, 999))

    (row,) = select_forecasts(targets(T), fc, NO_ACTUALS, HorizonRule(1.5)).itertuples()

    assert row.forecast_mw == 100


@pytest.mark.parametrize("hours", [0, 48])
def test_horizon_bounds_are_inclusive(hours):
    assert HorizonRule(hours).hours == hours


@pytest.mark.parametrize("hours", [-0.5, 48.01])
def test_horizon_outside_bounds_is_rejected(hours):
    with pytest.raises(ValueError, match="between 0 and 48"):
        HorizonRule(hours)


# --- rule construction ---------------------------------------------------------------------


def test_make_rule():
    assert make_rule("day_ahead") == DayAheadRule()
    assert make_rule(Mode.DAY_AHEAD, gate_time=time(11)) == DayAheadRule(time(11))
    assert make_rule("horizon", horizon_h=12) == HorizonRule(12)
    assert make_rule("horizon", horizon_h=12).mode is Mode.HORIZON
    assert DayAheadRule().mode is Mode.DAY_AHEAD


def test_make_rule_rejects_bad_input():
    with pytest.raises(ValueError, match="horizon_h"):
        make_rule("horizon")
    with pytest.raises(ValueError):
        make_rule("intraday")


def test_gate_time_with_timezone_is_rejected():
    with pytest.raises(ValueError, match="without tzinfo"):
        DayAheadRule(time(9, tzinfo=UTC))


# --- input validation ----------------------------------------------------------------------


def test_naive_timestamps_are_rejected():
    naive = pd.DatetimeIndex([pd.Timestamp("2026-01-16 00:00")])
    with pytest.raises(ValueError, match="targets must be timezone-aware"):
        select_forecasts(naive, forecasts(), NO_ACTUALS, DayAheadRule())


def test_missing_timestamps_are_rejected():
    with_nat = pd.DatetimeIndex([pd.NaT], tz="UTC")
    with pytest.raises(ValueError, match="missing timestamps"):
        select_forecasts(with_nat, forecasts(), NO_ACTUALS, DayAheadRule())


def test_duplicates_are_rejected():
    with pytest.raises(ValueError, match="targets contain duplicate"):
        select_forecasts(targets(T, T), forecasts(), NO_ACTUALS, DayAheadRule())
    dup_fc = forecasts(("2026-01-15T07:30Z", T, 1), ("2026-01-15T07:30Z", T, 2))
    with pytest.raises(ValueError, match="forecasts contain duplicate"):
        select_forecasts(targets(T), dup_fc, NO_ACTUALS, DayAheadRule())
    with pytest.raises(ValueError, match="actuals contain duplicate"):
        select_forecasts(targets(T), forecasts(), actuals((T, 1), (T, 2)), DayAheadRule())


# --- target grid ---------------------------------------------------------------------------


def test_hourly_targets_cover_half_open_window():
    grid = hourly_targets(datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 2, 2, tzinfo=UTC))

    assert len(grid) == 31 * 24
    assert grid[0] == ts("2026-01-02T00:00Z")
    assert grid[-1] == ts("2026-02-01T23:00Z")
    assert str(grid.tz) == "UTC"


def test_hourly_targets_reject_naive_bounds():
    with pytest.raises(ValueError, match="timezone-aware"):
        hourly_targets(datetime(2026, 1, 2), datetime(2026, 1, 3, tzinfo=UTC))
