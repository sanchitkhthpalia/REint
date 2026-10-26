# Decisions

Each entry: the decision, why, and what would change it. Facts about the data live in
`docs/DATA_NOTES.md`. This file records the choices made on top of them.

## D-001: Scope = delivery days 2 Jan to 1 Feb 2026
- **Decision:** "Purchase decisions made in January 2026" means day-ahead decisions made on D-1
  during January, so delivery days run from **2 Jan to 1 Feb 2026** (UK local days).
- **Alternative:** delivery days 1 to 31 Jan, i.e. decisions on 31 Dec to 30 Jan.
- **Configurable:** `SnapshotScope` in `backend/app/ingest/scope.py`, and
  `scripts/build_snapshot.py --first-delivery-day/--last-delivery-day`.

## D-002: Serve from a versioned snapshot, not live Elexon calls
- **Decision:** `scripts/build_snapshot.py` downloads the scope once and writes
  `data/actuals.parquet`, `data/forecasts.parquet` and `data/manifest.json`, which are
  committed. The backend serves from these files. An optional live refresh endpoint may be
  added later, reusing the same client and normalization code.
- **Why:**
  - January 2026 data is historical and immutable, so live calls add latency and failure
    modes without adding information.
  - A snapshot makes responses fast and reproducible.
  - It keeps the Vercel deployment independent of Elexon uptime and of serverless timeouts.
    A full WINDFOR month takes about 11 s to fetch.
- **Versioning:** the manifest records `schema_version`, a `snapshot_id` (a hash of the parquet
  contents), the fetch time, the exact request URLs and params, per-chunk row counts and a
  data-quality summary. A rebuild that changes data produces a new `snapshot_id` and a
  reviewable git diff.
- **Would change if:** the scope became rolling or near-real-time.

## D-003: Native resolution in storage, hourly-grid alignment in the domain layer
- **Decision:** ingestion keeps actuals half-hourly and forecasts hourly, so the snapshot is
  lossless. For forecast error metrics, actuals and forecasts are compared **on the hourly grid
  only**: forecast `HH:00` vs the FUELHH slot starting `HH:00`. No forecast values are
  interpolated (option 1 in DATA_NOTES §3).
- **Guard:** `normalize_forecasts` counts rows that are off the hour, and
  `build_snapshot.py` refuses to write a snapshot if any exist.
- **Status:** default, pending confirmation. It depends on what a WINDFOR `HH:00` value
  represents (DATA_NOTES open question 2). `CLAUDE.md` describes the core rule per 30-min
  slot. In practice the selection runs per forecast slot, which is hourly.

## D-004: Deduplication rules
- **Actuals:** one record per `startTime`. The row with the latest `publishTime` wins (latest
  revision). Exact duplicates are dropped. Two rows with the same `startTime` and
  `publishTime` but different generation raise an error instead of guessing.
- **Forecasts:** unique on `(publishTime, startTime)`. Exact duplicates are dropped; they
  appear at fetch-chunk boundaries because the API's publish-time bounds are inclusive.
  Conflicting duplicates raise.
- The January snapshot removed 0 duplicates from either dataset (`data/manifest.json`).

## D-005: Forecast download starts 3 days before the first delivery day
- **Decision:** WINDFOR publish window = [UK midnight of first delivery day − 3 days,
  UK midnight of last delivery day). For the default scope that is
  2025-12-30T00:00Z to 2026-02-01T00:00Z.
- **Why:** a publish on day X covers up to X+2 21:00, so D-1 publishes cover day D. Three days
  of lookback adds margin for a missing D-1 publish. Over-fetching is safe because the
  cutoff rule excludes anything published too late.

## D-006: Fetching strategy
- **Decision:** fetch in 7-day chunks, at most 4 concurrent requests, a 60 s timeout, and up
  to 4 retries with exponential backoff plus jitter.
  - Retry on timeouts, transport errors, 429 and 5xx (honouring `Retry-After`).
  - Fail immediately on any other status, or on a body that is not a JSON array.
- **Why:** the API has no pagination and accepted 120-day ranges (DATA_NOTES §4). Chunking is
  for latency and cheap retries, not for correctness.

## Open
- **Decision cutoff time on D-1:** not decided yet (DATA_NOTES open question 1). It must be
  chosen and justified before implementing forecast selection.
