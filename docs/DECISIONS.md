# Decision log

Short ADR-style records. Data facts behind these choices are in [DATA_NOTES.md](DATA_NOTES.md);
the overall design is in [ARCHITECTURE.md](ARCHITECTURE.md). All entries are accepted unless
marked otherwise.

---

## D-001 Scope: delivery days 2 Jan to 1 Feb 2026

**Context.** The brief says "purchase decisions made in January 2026". Day-ahead purchases are
made on D-1, so the decision day and the delivery day differ by one.

**Decision.** Decisions on 1 to 31 January cover UK delivery days 2 January to 1 February 2026.

**Consequences.** The range is a parameter (`SnapshotScope`, `--first-delivery-day` /
`--last-delivery-day`), so the other reading (delivery days 1 to 31 Jan) is one command away.

---

## D-002 Serve from a versioned snapshot, not live Elexon calls

**Context.** January 2026 is history. Live calls would only add latency and a dependency on
Elexon being up, and a full month of WINDFOR takes about 11 s to fetch.

**Decision.** `scripts/build_snapshot.py` downloads the scope once and writes data files plus
`data/manifest.json` (request params, row counts, content hashes, data-quality summary). The
files are committed and the API reads only them. A live refresh endpoint can be added later
on top of the same client and normaliser.

**Consequences.** Fast, reproducible answers and a deployment that does not care whether Elexon
is up. New data means rebuilding the snapshot and redeploying.

---

## D-003 Compare forecasts and actuals on the hourly grid

**Context.** FUELHH is half-hourly. WINDFOR is hourly, always on `HH:00`. Neither source says
whether `HH:00` is a point value or an hourly average.

**Decision.** Store both at native resolution. For error metrics, compare the forecast at
`HH:00` with the actual for the half-hour starting `HH:00`. Nothing is interpolated.

**Consequences.** No invented forecast values; 744 comparison points per month instead of
1,488. The snapshot build refuses to run if WINDFOR ever returns a non-hourly row.

---

## D-004 Deduplication

**Decision.** Actuals: one row per `startTime`, latest `publishTime` wins. Forecasts: unique
on `(publishTime, startTime)`. Exact duplicates (e.g. from overlapping fetch chunks) are
dropped. Two rows with the same key but different MW raise an error rather than picking one.

**Consequences.** The January snapshot removed zero duplicates, but the rule is tested with a
synthetic revision.

---

## D-005 Forecast download window

**Context.** A forecast published on day X covers up to X+2 21:00 UK. Horizon mode with small
H also needs forecasts published during the delivery day itself.

**Decision.** Download WINDFOR publishes from UK midnight three days before the first delivery
day to the end of the delivery window (2025-12-30T00:00Z to 2026-02-02T00:00Z).

**Consequences.** 272 publishes, 19,856 rows. An earlier version stopped at the last decision
day, which made horizon mode quietly fall back to 24 h old forecasts on 1 February; that was
caught on real data and fixed.

---

## D-006 Fetching strategy

**Decision.** 7-day chunks, at most 4 concurrent requests, 60 s timeout, 4 retries with
exponential backoff and jitter on timeouts, transport errors, 429 and 5xx (honouring
`Retry-After`). Any other error fails immediately with the URL, params and response body.

**Consequences.** The API needs no pagination (120-day requests worked); chunking is for speed
and cheap retries.

---

## D-007 Day-ahead gate time defaults to 09:00 UK (assumption)

**Context.** The data does not say when the desk commits its day-ahead position. Since 2021 the
GB day-ahead auctions close at about 09:20 (EPEX) and 09:50 (N2EX) UK time.

**Decision.** Default cutoff is 09:00 Europe/London on D-1, configurable per request. A gate time
that falls in a clock change resolves to the earlier instant, so an edge case can only remove
information, never leak it.

**Consequences.** In January this picks the 07:30 publish (lead times 16.5 to 39.5 h). A 09:50
gate would pick the 09:30 publish; MAE moves from 2,022 to 1,996 MW. The client's real deadline
should replace the default.

---

## D-008 Selection as an as-of join; missing data is flagged

**Decision.** For each target slot, `pandas.merge_asof` (backward, exact matches allowed,
grouped by slot) picks the latest forecast with `publishTime <= cutoff`. Every slot is returned;
`has_forecast` and `has_actual` flag gaps and the dependent values are null.

**Consequences.** No Python loops, and gaps stay visible. With a 48 h horizon, 155 of 744 slots
have no forecast at all because WINDFOR rarely reaches that far ahead; the UI shows this.

---

## D-009 Metrics and the procurement buffer

**Decision.**
- Report MAE, RMSE, mean bias and nMAE (MAE / mean actual). No MAPE: wind output can be near
  zero, and dividing by it lets a few calm hours dominate.
- Error is forecast minus actual. Positive means over-forecast, i.e. a wind shortfall.
- The buffer is the empirical quantile (`inverted_cdf`) of signed error over all paired slots,
  floored at zero, at 90% and 95%. That makes "buy X MW above the forecast to be covered in 90%
  of hours" literally true in-sample. Descriptive percentiles use linear interpolation.

**Consequences.** January bias is large (+1,746 MW, 85% of hours over-forecast), so most of the
buffer is systematic rather than random. Part of it may come from WINDFOR and FUELHH covering
different sets of wind farms. The UI states this caveat next to the numbers.

---

## D-010 HTTP API

**Decision.** FastAPI with `/api/health`, `/api/meta`, `/api/series`, `/api/metrics`,
`/api/metrics/by-hour`, `/api/metrics/by-horizon`; OpenAPI docs at `/api/docs`. Unknown query
parameters are rejected. All validation problems come back together as standard 422 errors that
name the offending parameter. Selections and lead-time curves are LRU-cached in process.
Hashes of the served data files are checked against the manifest at startup. Logs are one JSON object per line.

**Consequences.** The frontend gets typed, predictable errors; the app will not start on a
corrupted snapshot.

---

## D-011 Frontend stack

**Decision.** Vite, React 19, strict TypeScript, Tailwind, TanStack Query, Recharts. API types
are generated from the backend's OpenAPI schema. Filters live in the URL so views can be shared.
Requests are debounced by 250 ms so dragging the horizon slider sends one request.

**Consequences.** Recharts copes comfortably with ~1,500 points per chart. The single JS bundle
is about 200 kB gzipped, mostly the chart library.

---

## D-012 Containers

**Decision.** Two images run by `docker compose up --build` on port 8080. Backend:
multi-stage `python:3.12-slim`, non-root, urllib healthcheck. Frontend: Node build stage, then
unprivileged nginx that serves the SPA and proxies `/api` to the backend. nginx re-resolves the
backend through Docker DNS; a static upstream gave 502s after the backend container was
recreated with a new IP.

**Consequences.** One origin for the browser, so no CORS in Docker. Health probes are logged at
DEBUG to keep the access log readable.

---

## D-013 Vercel: one project, no pyarrow at runtime

**Context.** A local `vercel build` rejected the function: 292.5 MB against a 225 MB limit.
pyarrow was 162 MB of it, used only to read parquet.

**Decision.** The snapshot builder writes each table twice from the same records: parquet as
the archive and gzipped CSV as the serving copy. The API reads the CSV with plain pandas, and
pyarrow is a dev-only dependency. A test asserts both copies hold identical values.
`vercel.json` builds the frontend as static files and routes `/api/*` to one Python function
(`api/index.py`) that bundles only the backend code, manifest and CSV files. Successful GETs
carry `s-maxage=86400, stale-while-revalidate=604800` so Vercel's CDN answers repeat requests.

**Consequences.** Function bundle 110 MB; backend image 482 MB (was 695 MB). Cold start is about
1.4 s of imports on a fresh Linux container, after which requests take 4 to 40 ms except the
48-horizon sweep (0.4 s). Fully precomputed JSON was rejected because date range, gate time and
horizon combine into too many cases.
