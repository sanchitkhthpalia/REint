from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx

from app.ingest.elexon_client import (
    BASE_URL,
    FUELHH_PATH,
    WINDFOR_PATH,
    ElexonClient,
    ElexonError,
    date_chunks,
    datetime_chunks,
)


def test_date_chunks_are_inclusive_and_non_overlapping():
    assert date_chunks(date(2026, 1, 2), date(2026, 1, 16), 7) == [
        (date(2026, 1, 2), date(2026, 1, 8)),
        (date(2026, 1, 9), date(2026, 1, 15)),
        (date(2026, 1, 16), date(2026, 1, 16)),
    ]


def test_datetime_chunks_cover_range_with_shared_boundaries():
    start = datetime(2025, 12, 30, tzinfo=UTC)
    chunks = datetime_chunks(start, start + timedelta(days=10), timedelta(days=7))

    assert chunks == [
        (start, start + timedelta(days=7)),
        (start + timedelta(days=7), start + timedelta(days=10)),
    ]


@respx.mock
async def test_fuelhh_requests_each_chunk_with_verified_params():
    route = respx.get(BASE_URL + FUELHH_PATH).mock(return_value=httpx.Response(200, json=[]))

    async with ElexonClient(chunk_days=7) as client:
        await client.fetch_fuelhh(date(2026, 1, 2), date(2026, 1, 9))

    sent = [dict(call.request.url.params.multi_items()) for call in route.calls]
    assert sent == [
        {"settlementDateFrom": "2026-01-02", "settlementDateTo": "2026-01-08", "fuelType": "WIND"},
        {"settlementDateFrom": "2026-01-09", "settlementDateTo": "2026-01-09", "fuelType": "WIND"},
    ]
    assert len(client.requests) == 2


@respx.mock
async def test_windfor_sends_utc_z_timestamps():
    route = respx.get(BASE_URL + WINDFOR_PATH).mock(return_value=httpx.Response(200, json=[]))

    async with ElexonClient() as client:
        await client.fetch_windfor(
            datetime(2025, 12, 30, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    params = route.calls[0].request.url.params
    assert params["publishDateTimeFrom"] == "2025-12-30T00:00:00Z"
    assert params["publishDateTimeTo"] == "2026-01-02T00:00:00Z"


@respx.mock
async def test_retries_transient_failures_then_succeeds():
    row = {"publishTime": "x"}
    route = respx.get(BASE_URL + WINDFOR_PATH).mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectTimeout("slow"),
            httpx.Response(200, json=[row]),
        ]
    )

    async with ElexonClient(backoff_s=0) as client:
        rows = await client.fetch_windfor(
            datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
        )

    assert rows == [row]
    assert route.call_count == 3
    assert client.requests[0].attempts == 3


@respx.mock
async def test_gives_up_after_max_retries_with_clear_error():
    respx.get(BASE_URL + WINDFOR_PATH).mock(return_value=httpx.Response(502))

    async with ElexonClient(backoff_s=0, max_retries=2) as client:
        with pytest.raises(ElexonError, match="failed after 3 attempts; last: HTTP 502"):
            await client.fetch_windfor(
                datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 2, tzinfo=UTC)
            )


@respx.mock
async def test_client_errors_are_not_retried():
    route = respx.get(BASE_URL + FUELHH_PATH).mock(
        return_value=httpx.Response(400, text="bad settlementDate")
    )

    async with ElexonClient(backoff_s=0) as client:
        with pytest.raises(ElexonError, match="HTTP 400: bad settlementDate"):
            await client.fetch_fuelhh(date(2026, 1, 2), date(2026, 1, 2))

    assert route.call_count == 1


@respx.mock
async def test_non_array_body_is_an_error():
    respx.get(BASE_URL + FUELHH_PATH).mock(return_value=httpx.Response(200, json={"data": []}))

    async with ElexonClient() as client:
        with pytest.raises(ElexonError, match="expected a JSON array"):
            await client.fetch_fuelhh(date(2026, 1, 2), date(2026, 1, 2))


async def test_naive_datetimes_are_rejected():
    async with ElexonClient() as client:
        with pytest.raises(ValueError, match="naive"):
            await client.fetch_windfor(datetime(2026, 1, 1), datetime(2026, 1, 2))
