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

## D-005: Forecast download window
- **Decision:** WINDFOR publish window = [UK midnight of first delivery day − 3 days,
  end of the delivery window]. For the default scope that is
  2025-12-30T00:00Z to 2026-02-02T00:00Z.
- **Why the start:** a publish on day X covers up to X+2 21:00, so D-1 publishes cover day D.
  Three days of lookback adds margin for a missing D-1 publish.
- **Why the end:**
  - Day-ahead mode only needs publishes up to D-1. Horizon mode with small H needs publishes
    made during the delivery day itself.
  - The first version stopped at 2026-02-01T00:00Z. With H=0, the 1 Feb slots then quietly
    used the 31 Jan 22:30 forecast, with lead times up to 24.5 h.
- **Safety:** over-fetching is safe, because the cutoff rule excludes anything published too
  late.

## D-006: Fetching strategy
- **Decision:** fetch in 7-day chunks, at most 4 concurrent requests, a 60 s timeout, and up
  to 4 retries with exponential backoff plus jitter.
  - Retry on timeouts, transport errors, 429 and 5xx (honouring `Retry-After`).
  - Fail immediately on any other status, or on a body that is not a JSON array.
- **Why:** the API has no pagination and accepted 120-day ranges (DATA_NOTES §4). Chunking is
  for latency and cheap retries, not for correctness.

## D-007: Day-ahead gate time defaults to 09:00 Europe/London (assumption, configurable)
- **Decision:** in `day_ahead` mode (the default), the cutoff for a slot on UK delivery day D
  is **09:00 Europe/London on D-1**.
  - Configure it with `DayAheadRule(gate_time=...)` / `make_rule(..., gate_time=...)`.
  - A `horizon` mode (cutoff = T − H, 0 ≤ H ≤ 48) is also available.
- **Status: this is an assumption** based on GB day-ahead auction timing, not on Elexon data.
  The client's actual internal deadline should replace it.
  - Since Brexit (Jan 2021), the EPEX SPOT GB day-ahead auction closes at about 09:20 UK time
    and the Nord Pool N2EX GB auction at 09:50 UK time (Nord Pool support article
    "About the day-ahead GB auction"; S&P Global Platts subscriber note, Dec 2020).
  - 09:00 leaves a short preparation margin before the earlier auction.
- **Why it matters:**
  - In January, WINDFOR publishes at 07:30 and 09:30 UTC (= UK time in winter).
  - Gates at 09:00 and 09:20 both select the 07:30 publish, giving lead times of 16.5 to 39.5 h.
  - A 09:50 gate would select the 09:30 publish.
  - Small changes to the gate can switch which forecast is used.
- **Clock changes:** the gate is a UK wall-clock time on the calendar day D-1, and D is the UK
  local day of the slot. A gate time that falls in a clock change resolves to the earlier
  instant, which means less information and never lookahead:
  - Ambiguous (repeated) times use the first occurrence.
  - Non-existent times resolve to just before the gap.

## D-008: Selection is an as-of join, and missing data is flagged rather than dropped
- **Decision:** `app/domain/selection.py::select_forecasts` uses `pandas.merge_asof`
  (backward, exact matches allowed, grouped by target slot). This implements "latest
  publishTime ≤ cutoff" without Python loops.
- **Output:** one row per target slot, always. `has_forecast` / `has_actual` flag gaps, and
  `error_mw` / `lead_time_hours` are null where they can't be computed.
- **Target slots:** the hourly grid (D-003).
- **Coverage:** with `horizon` H=48, 155 of the 744 January slots have no eligible forecast,
  because WINDFOR's maximum horizon is 46.5 to 66.5 h depending on publish time. This is a
  real property of the data, and the UI must show it.
- **Column naming:** timestamps carry a `_utc` suffix (`publish_time_utc`, `cutoff_utc`), to
  match the snapshot columns and CLAUDE.md conventions.
