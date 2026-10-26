from datetime import UTC, datetime, timedelta

import pytest

from app.ingest.normalize import (
    Actual,
    Forecast,
    NormalizationError,
    missing_slots,
    normalize_actuals,
    normalize_forecasts,
)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


# --- actuals -----------------------------------------------------------------------------


def test_actuals_from_real_wind_rows(fuelhh_wind):
    result = normalize_actuals(fuelhh_wind)

    assert result.rows_in == 4
    assert result.non_wind_dropped == 0
    assert result.duplicates_removed == 0
    assert [a.start_time_utc for a in result.records] == [
        utc(2026, 1, 3, 0, 0),
        utc(2026, 1, 3, 0, 30),
        utc(2026, 1, 3, 1, 0),
        utc(2026, 1, 3, 1, 30),
    ]
    assert result.records[0] == Actual(start_time_utc=utc(2026, 1, 3), generation_mw=14380)
    assert all(a.start_time_utc.tzinfo == UTC for a in result.records)


def test_actuals_keep_only_wind(fuelhh_all_fuels):
    result = normalize_actuals(fuelhh_all_fuels)

    assert result.rows_in == 20
    assert result.non_wind_dropped == 19
    assert len(result.records) == 1
    wind_row = next(r for r in fuelhh_all_fuels if r["fuelType"] == "WIND")
    assert result.records[0].generation_mw == wind_row["generation"]


def _revised(row: dict, minutes_later: int, generation: int) -> dict:
    # Synthetic revision built from a real row: real data shows no revisions (DATA_NOTES §2),
    # but the dedupe rule must hold if one ever appears.
    published = datetime.fromisoformat(row["publishTime"]) + timedelta(minutes=minutes_later)
    return {
        **row,
        "publishTime": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generation": generation,
    }


@pytest.mark.parametrize("revision_first", [False, True])
def test_actuals_latest_revision_wins_regardless_of_order(fuelhh_wind, revision_first):
    original = fuelhh_wind[0]
    revision = _revised(original, minutes_later=60, generation=original["generation"] + 500)
    rows = [revision, *fuelhh_wind] if revision_first else [*fuelhh_wind, revision]

    result = normalize_actuals(rows)

    assert result.duplicates_removed == 1
    assert len(result.records) == 4
    by_start = {a.start_time_utc: a.generation_mw for a in result.records}
    assert by_start[datetime.fromisoformat(original["startTime"])] == revision["generation"]


def test_actuals_exact_duplicate_is_dropped(fuelhh_wind):
    result = normalize_actuals([*fuelhh_wind, dict(fuelhh_wind[1])])

    assert result.duplicates_removed == 1
    assert len(result.records) == 4


def test_actuals_conflicting_rows_with_same_publish_time_raise(fuelhh_wind):
    conflicting = {**fuelhh_wind[0], "generation": fuelhh_wind[0]["generation"] + 1}

    with pytest.raises(NormalizationError, match="conflicting"):
        normalize_actuals([*fuelhh_wind, conflicting])


def test_actuals_offset_timestamps_are_converted_to_utc(fuelhh_wind):
    row = {**fuelhh_wind[0], "startTime": "2026-01-03T01:00:00+01:00"}

    (actual,) = normalize_actuals([row]).records

    assert actual.start_time_utc == utc(2026, 1, 3, 0, 0)
    assert actual.start_time_utc.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "change",
    [
        {"startTime": "2026-01-03T00:00:00"},  # naive: timezone unknown, refuse to guess
        {"generation": None},
        {"publishTime": "not a time"},
    ],
)
def test_actuals_invalid_rows_raise_with_context(fuelhh_wind, change):
    with pytest.raises(NormalizationError, match="FUELHH row 0"):
        normalize_actuals([{**fuelhh_wind[0], **change}])


# --- forecasts ---------------------------------------------------------------------------


def test_forecasts_from_real_rows_keep_every_publish(windfor):
    result = normalize_forecasts(windfor)

    assert result.rows_in == 6
    assert result.duplicates_removed == 0
    assert result.off_hour_rows == 0
    # Both publishes are kept; choosing one per decision cutoff happens in the domain layer.
    assert sorted({f.publish_time_utc for f in result.records}) == [
        utc(2026, 1, 15, 9, 30),
        utc(2026, 1, 15, 12, 25),
    ]
    assert result.records[0] == Forecast(
        start_time_utc=utc(2026, 1, 16, 0),
        publish_time_utc=utc(2026, 1, 15, 9, 30),
        generation_mw=7472,
    )
    keys = [(f.publish_time_utc, f.start_time_utc) for f in result.records]
    assert keys == sorted(keys)


def test_forecasts_exact_duplicates_from_chunk_overlap_are_dropped(windfor):
    result = normalize_forecasts([*windfor, *windfor[:2]])

    assert result.duplicates_removed == 2
    assert len(result.records) == 6


def test_forecasts_conflicting_duplicate_raises(windfor):
    conflicting = {**windfor[0], "generation": windfor[0]["generation"] + 1}

    with pytest.raises(NormalizationError, match="WINDFOR conflicting"):
        normalize_forecasts([*windfor, conflicting])


def test_forecasts_off_hour_rows_are_counted(windfor):
    half_hour = {**windfor[0], "startTime": "2026-01-16T00:30:00Z"}

    result = normalize_forecasts([*windfor, half_hour])

    assert result.off_hour_rows == 1


def test_forecasts_naive_timestamp_raises(windfor):
    with pytest.raises(NormalizationError, match="WINDFOR row 0"):
        normalize_forecasts([{**windfor[0], "publishTime": "2026-01-15T12:25:00"}])


# --- missing slots -----------------------------------------------------------------------


def test_missing_slots_reports_gaps_in_half_open_window(fuelhh_wind):
    actuals = normalize_actuals([r for r in fuelhh_wind if r["settlementPeriod"] != 2]).records

    missing = missing_slots(
        (a.start_time_utc for a in actuals),
        utc(2026, 1, 3, 0, 0),
        utc(2026, 1, 3, 2, 30),
        timedelta(minutes=30),
    )

    assert missing == [utc(2026, 1, 3, 0, 30), utc(2026, 1, 3, 2, 0)]
