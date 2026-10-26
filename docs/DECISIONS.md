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

## D-009: Metric definitions (`app/domain/metrics.py`)
- **Headline metrics:** MAE, RMSE, mean bias, and nMAE = MAE / mean actual.
- **No MAPE:** wind output can approach 0 MW, and dividing by near-zero actuals lets a few
  calm hours dominate. nMAE normalises once by the mean actual.
- **Procurement buffer** = the empirical quantile of **signed** error over **all** paired
  slots, floored at 0 (P90 and P95).
  - This makes the sentence "buy X MW above the forecast-implied need to be covered in 90% of
    hours" literally true in-sample.
  - The alternative of taking the quantile of positive errors only answers "how big are
    shortfalls when they happen". It over-sizes the buffer for the coverage claim.
- **Percentile method:**
  - The buffer uses `inverted_cdf`: the smallest observed error with at least q of slots at
    or below it, which guarantees the coverage.
  - Descriptive percentiles use linear interpolation.
  - At n=744 the two differ by a few MW. On small samples, linear interpolation can claim
    coverage it does not deliver.
- **"Half-hours" vs "hours":** the buffer message names the slot unit from the target grid.
  Under D-003 the grid is hourly, so it reads "of hours". It would read "half-hours" on a
  30-minute grid.
- **Groupings:** hour of day and delivery day use Europe/London time. Groups with no paired
  slots are kept with n=0.
- **Lead-time curve:** horizon mode for H = 1..48 h. Each point reports MAE, linear P90 of
  |error| and the P90 buffer. Lead times within a point are H+0.5 to H+3.5 h, because
  publishes are 2 to 4 h apart.
- **Caveat on results:** January day-ahead bias is +1,746 MW and 85% of hours are
  over-forecast, so the buffer (about 4.2 GW at P90) is mostly systematic bias.
  - If WINDFOR and FUELHH cover different wind fleets (DATA_NOTES open question 4), part of
    that bias is a definitional gap, not forecast error.
  - This must be stated wherever the buffer is shown.

## D-010: HTTP API shape and runtime
- **Endpoints:** `/api/health`, `/api/meta`, `/api/series`, `/api/metrics`,
  `/api/metrics/by-hour`, `/api/metrics/by-horizon`. Docs are at `/api/docs`.
- **Parameters:**
  - `start`/`end` are UK delivery days, inclusive. They default to the whole snapshot and must
    lie within it.
  - `mode=day_ahead` (default, with `gate_time`) or `mode=horizon` (with `horizon_h`, 0 to 48).
  - Unknown parameters are rejected, so a typo like `horizon=6` fails loudly instead of being
    ignored.
  - Every 422 uses FastAPI's standard error format, located at the offending parameter, and
    reports all problems at once.
- **Caching:** the snapshot is immutable, so selections and lead-time curves are LRU-cached in
  process, keyed on (start, end, rule). Size is set by `CACHE_SIZE`, default 128. On Vercel the
  cache lives only as long as a warm instance; that is acceptable because a cold month query
  takes about 60 ms, and the 48-horizon curve about 0.4 s.
- **Snapshot integrity:** the app checks parquet sha256 hashes against `manifest.json` at
  startup and refuses to start on a mismatch.
- **Logging:** JSON lines on stdout, with one access-log line per request (request id, path,
  query, status, duration) and an `X-Request-ID` response header.
- **CORS:** set by the `CORS_ORIGINS` env var (comma-separated), GET only. Default is the Vite
  dev server, `http://localhost:5173`. An empty value disables CORS for same-origin
  deployments.
- **Two runtimes, one app:**
  - Docker/local: `uvicorn app.main:app` from `backend/`.
  - Vercel: `api/index.py` re-exports the same app. `vercel.json` rewrites `/api/*` to it and
    bundles `backend/app/**` and `data/**`. Runtime dependencies are pinned in the root
    `requirements.txt`.
- **Frontend deploy:** Vercel builds `frontend/` (`npm ci && npm run build`) and serves
  `frontend/dist` statically. The SPA calls same-origin `/api`, so production needs no CORS.
- **Bundle size risk:** confirmed and resolved. See D-013.

## D-011: Frontend
- **Stack:** Vite, React 19, TypeScript (strict), Tailwind v4, TanStack Query and Recharts.
  - Recharts is enough because a month is 744 hourly points per series, about 1.5k marks per
    chart, rendered without animation. ECharts' canvas renderer only pays off at much higher
    point counts.
- **Typed client:** `backend/openapi.json` is exported from FastAPI with
  `scripts/export_openapi.py`, and `npm run gen:api` turns it into `src/api/schema.ts`. Request
  and response types therefore come from the backend models rather than being hand-copied.
- **Shareable views:** filters live in the URL (`start`, `end`, `mode`, `horizon_h`,
  `gate_time`), and only non-default values are written. Invalid or out-of-range URL values
  fall back to defaults rather than producing an error page.
- **Fetching:** requests use filters debounced by 250 ms, so dragging the horizon slider sends
  one request. `keepPreviousData` keeps the last chart visible, dimmed, while a new one loads.
  Results never go stale in a session because the snapshot is immutable.
- **Wording:** the buffer card says "Hold ~X MW extra to cover 90% of hours", rounded to the
  nearest 10 MW. The unit follows the API's `slot_minutes` (D-009), so it would read
  "half-hours" on a 30-minute grid.
- **Gate options:** 07:00 to 12:00, including 09:20 and 09:50 labelled as the EPEX and N2EX GB
  auction closures. A custom value from a shared URL is still shown.
- **Accessibility:**
  - Dark theme with text at least slate-400 on slate-900.
  - A blue/amber pair for actual and forecast, which stays distinguishable for common
    colour-vision deficiencies.
  - Error colour is backed by a +/− sign in text.
  - Charts carry aria-labels, and the table has a caption and header scopes.
- **Times:** shown in Europe/London. Chart ticks fall on UK midnights, or every 6 h for ranges
  of three days or less.

## D-012: Containers
- **Command:** `docker compose up --build`, or `make up`, serves the full app on
  http://localhost:8080.
  - nginx serves the built SPA and proxies `/api/*` to the backend over the compose network.
  - The browser sees one origin, so CORS is disabled (`CORS_ORIGINS=""`).
- **Backend image** (`backend/Dockerfile`, build context = repo root):
  - Multi-stage `python:3.12-slim`. The build stage installs the pinned `requirements.txt`
    (shared with Vercel) plus uvicorn into `/opt/venv`.
  - The runtime stage copies only the venv, `backend/app` and `data/`, and runs as uid 10001.
  - The healthcheck uses Python's urllib, because slim has no curl.
  - The image is about 700 MB, almost all pandas/pyarrow/numpy (see the D-010 size risk).
- **Frontend image** (`frontend/Dockerfile`):
  - `node:22-alpine` build, then `nginxinc/nginx-unprivileged` (non-root, port 8080).
  - SPA fallback; immutable caching for hashed assets; `no-cache` for `index.html`; gzip.
  - `/healthz` endpoint.
- **Startup order:** the frontend waits for `backend: service_healthy`.
- **nginx re-resolves `backend` through Docker DNS** (`resolver 127.0.0.11` plus a variable
  upstream). A static `proxy_pass http://backend:8000` is resolved once at startup and returned
  502s after the backend was recreated on a new IP. Verified by recreating the backend on a
  different address with the frontend still running.
- **Log noise:** healthcheck requests to `/api/health` are logged at DEBUG, so the 15-second
  probes don't drown the INFO access log.

## D-013: Vercel deployment, with pyarrow removed from the serving path
- **Shape:** one Vercel project.
  - `framework: null`; Vercel builds `frontend/` (`npm ci && npm run build`) and serves
    `frontend/dist` statically.
  - `api/index.py` is a file-based Python function, Python 3.12 on x86_64 (Vercel's default),
    exporting the FastAPI `app`.
  - The rewrite `/api/(.*)` sends every API path to that one function, and FastAPI routes on
    the original path.
  - `includeFiles` bundles only `backend/app/**`, `data/manifest.json` and `data/*.csv.gz`.
    `excludeFiles` drops the frontend, tests, docs, scripts and the parquet archive.
- **Evidence:**
  - Vercel's docs list a 500 MB Python limit. A local `vercel build` (CLI 65.2.0, Linux x86_64
    wheels), however, rejected the function with
    `LAMBDA_SIZE_EXCEEDED: Total bundle size (292.54 MB) exceeds the maximum function size
    (225 MB)`.
  - pyarrow alone was 162 MB of that, and the app only used it to read parquet.
- **Decision:** the API reads gzipped CSV serving copies with plain pandas, and pyarrow leaves
  the runtime dependencies.
  - `build_snapshot.py` writes both formats from the same in-memory records.
  - Parquet stays as the typed archive for analysis.
  - The manifest hashes both and labels each file `serving` or `archive`.
  - `tests/test_snapshot_files.py` asserts the two copies are value-identical.
  - Result: the function bundle is **110 MB** (pandas 43, numpy 54, pydantic 7), the Docker
    backend image 482 MB (was 695 MB), and the serving data 107 KB.
- **Alternatives rejected:**
  - Fully precomputed JSON: users pick arbitrary date ranges, gate times and horizons, so the
    combinations are unbounded.
  - Replacing pandas with numpy-only code: it would rewrite the tested domain layer for little
    gain once the bundle fits.
  - The Large Functions beta (5 GB): it avoids the problem rather than fixing it, and adds
    cold-start weight.
- **Cold start**, measured on a fresh Linux container:
  - Imports take about 1.4 s (pandas+numpy 0.9–1.1 s, FastAPI 0.4 s), and the snapshot loads
    in 0.07 s.
  - First requests take 4–40 ms, except `/api/metrics/by-horizon` (0.4 s, 48 selections).
  - Mitigation: successful GETs send `Cache-Control: public, max-age=300, s-maxage=86400,
    stale-while-revalidate=604800`, so Vercel's CDN answers repeat requests without invoking
    the function.
  - Vercel's CDN cache is scoped per deployment, so new data means a new deploy and fresh
    answers.
  - Errors and `/api/health` are `no-store`.
- **Python version:** no `.python-version` file. Pinning `3.12` made the local `vercel build`
  fail, because the builder's generated project demanded the host's Python. Vercel's default
  is already 3.12, and Docker matches it.
- **Verification:** `make verify URL=<deployment>` (`scripts/verify_deploy.sh`) checks:
  - the UI shell and assets;
  - every endpoint, plus validation 422s and the docs;
  - cache headers;
  - that the deployed `snapshot_id` matches `data/`;
  - that production `/api/metrics` equals the local computation.
