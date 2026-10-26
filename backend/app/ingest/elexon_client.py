"""Async client for the Elexon BMRS FUELHH and WINDFOR stream endpoints.

Contract verified in docs/DATA_NOTES.md: no auth, responses are bare JSON arrays with no
pagination, and publish-time filters are inclusive at both ends. Ranges are split into
chunks to keep each request fast and cheap to retry.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Self

import httpx

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
FUELHH_PATH = "/datasets/FUELHH/stream"
WINDFOR_PATH = "/datasets/WINDFOR/stream"

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

RawRow = dict[str, Any]
QueryParams = list[tuple[str, str]]


class ElexonError(RuntimeError):
    """A request failed permanently, or kept failing after all retries."""


@dataclass(frozen=True)
class RequestRecord:
    url: str
    params: QueryParams
    rows: int
    attempts: int


def date_chunks(start: date, end: date, days: int) -> list[tuple[date, date]]:
    """Split the inclusive range [start, end] into inclusive, non-overlapping chunks."""
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def datetime_chunks(
    start: datetime, end: datetime, span: timedelta
) -> list[tuple[datetime, datetime]]:
    """Split [start, end] into consecutive windows that share boundaries.

    The API treats both bounds as inclusive, so a row exactly on a boundary can come back
    twice. Normalization drops those exact duplicates.
    """
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    chunks = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + span, end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks or [(start, end)]


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime {dt!r}; pass an aware UTC datetime")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ElexonClient:
    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout_s: float = 60.0,
        max_retries: int = 4,
        backoff_s: float = 1.0,
        chunk_days: int = 7,
        max_concurrency: int = 4,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_s,
            transport=transport,
            headers={"Accept": "application/json"},
        )
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._chunk_days = chunk_days
        self._max_concurrency = max_concurrency
        self.requests: list[RequestRecord] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_fuelhh(
        self,
        settlement_date_from: date,
        settlement_date_to: date,
        fuel_types: Sequence[str] = ("WIND",),
    ) -> list[RawRow]:
        """FUELHH rows for an inclusive range of settlement (UK local) days."""
        param_sets = [
            [
                ("settlementDateFrom", a.isoformat()),
                ("settlementDateTo", b.isoformat()),
                *(("fuelType", f) for f in fuel_types),
            ]
            for a, b in date_chunks(settlement_date_from, settlement_date_to, self._chunk_days)
        ]
        return await self._fetch_all(FUELHH_PATH, param_sets)

    async def fetch_windfor(self, publish_from: datetime, publish_to: datetime) -> list[RawRow]:
        """WINDFOR rows for every forecast published in [publish_from, publish_to]."""
        param_sets = [
            [("publishDateTimeFrom", iso_utc(a)), ("publishDateTimeTo", iso_utc(b))]
            for a, b in datetime_chunks(publish_from, publish_to, timedelta(days=self._chunk_days))
        ]
        return await self._fetch_all(WINDFOR_PATH, param_sets)

    async def _fetch_all(self, path: str, param_sets: list[QueryParams]) -> list[RawRow]:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def one(params: QueryParams) -> tuple[list[RawRow], int]:
            async with semaphore:
                return await self._get(path, params)

        results = await asyncio.gather(*(one(p) for p in param_sets))
        rows: list[RawRow] = []
        for params, (chunk_rows, attempts) in zip(param_sets, results, strict=True):
            self.requests.append(
                RequestRecord(f"{self._base_url}{path}", params, len(chunk_rows), attempts)
            )
            rows.extend(chunk_rows)
        return rows

    async def _get(self, path: str, params: QueryParams) -> tuple[list[RawRow], int]:
        """GET one chunk, retrying timeouts, transport errors, 429 and 5xx with backoff."""
        where = f"GET {self._base_url}{path} params={params}"
        problem = ""
        attempts = 0
        while True:
            attempts += 1
            retry_after: float | None = None
            try:
                response = await self._client.get(path, params=params)
            except httpx.TimeoutException as e:
                problem = f"timeout ({type(e).__name__})"
            except httpx.TransportError as e:
                problem = f"transport error ({type(e).__name__}: {e})"
            else:
                if response.status_code == 200:
                    return self._parse(response, where), attempts
                if response.status_code not in RETRYABLE_STATUS:
                    raise ElexonError(
                        f"{where} -> HTTP {response.status_code}: {response.text[:500]}"
                    )
                problem = f"HTTP {response.status_code}"
                retry_after = _retry_after_s(response)

            if attempts > self._max_retries:
                raise ElexonError(f"{where} failed after {attempts} attempts; last: {problem}")
            await asyncio.sleep(retry_after if retry_after is not None else self._backoff(attempts))

    def _backoff(self, attempt: int) -> float:
        delay = self._backoff_s * 2 ** (attempt - 1)
        return delay + random.uniform(0, delay / 4)

    @staticmethod
    def _parse(response: httpx.Response, where: str) -> list[RawRow]:
        try:
            body = response.json()
        except ValueError as e:
            raise ElexonError(f"{where} -> response is not JSON: {response.text[:200]}") from e
        if not isinstance(body, list):
            raise ElexonError(f"{where} -> expected a JSON array, got {type(body).__name__}")
        return body


def _retry_after_s(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
