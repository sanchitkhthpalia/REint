# Data Notes: Elexon BMRS FUELHH and WINDFOR

Facts below come from the published OpenAPI spec and live calls made on 2026-10-26 with
`scripts/probe_elexon.py`. Anything not directly observed is marked **Inferred** or listed under
Open questions.

Reproduce:
```
python scripts/probe_elexon.py                 # contract + 1-2 day samples
python scripts/probe_elexon.py --range-probe   # max range per request
python scripts/probe_elexon.py --coverage      # gaps over the Jan 2026 scope + BST checks
```
(On python.org macOS builds, prefix with `SSL_CERT_FILE=/etc/ssl/cert.pem`.)

## 1. Sources and contract

The docs pages at `bmrs.elexon.co.uk/api-documentation/...` are a JavaScript single-page app
with no server-rendered content. The machine-readable source behind them is the OpenAPI spec at
`https://data.elexon.co.uk/swagger/v1/swagger.json` (OpenAPI 3.0.4, "Insights.Api").

- Base URL (spec `servers`): `https://data.elexon.co.uk/bmrs/api/v1`
- No authentication or API key was needed for any call.

| Endpoint | Query params (all optional) |
|---|---|
| `GET /datasets/FUELHH/stream` | `publishDateTimeFrom`, `publishDateTimeTo` (date-time), `settlementDateFrom`, `settlementDateTo` (date `yyyy-MM-dd`), `settlementPeriod` (int[]), `fuelType` (string[]) |
| `GET /datasets/WINDFOR/stream` | `publishDateTimeFrom`, `publishDateTimeTo` (date-time) |

- FUELHH spec: "The Settlement Date fields cannot be set when a Publish Date field is set."
- WINDFOR spec: with no publish filters it "will retrieve the latest published forecast".
  Verified: no params returned 73 rows from a single publish (`2026-10-26T11:30:00Z`).
- **WINDFOR cannot be filtered by `startTime`.** You select by publish time and get each
  publish's full window.
- Response: a **bare JSON array** with no envelope, metadata or pagination cursor.
  (The non-stream endpoints `/datasets/FUELHH` and `/datasets/WINDFOR` wrap rows in a
  `DatasetResponse` per the spec. Not probed.)

### Fields and types (observed)
| Dataset | Field | JSON type | Notes |
|---|---|---|---|
| both | `dataset` | string | `"FUELHH"` / `"WINDFOR"` |
| both | `publishTime` | string | ISO-8601 UTC with `Z`, e.g. `"2026-01-05T00:00:00Z"` |
| both | `startTime` | string | ISO-8601 UTC with `Z` |
| both | `generation` | integer | MW. Spec: int64 |
| FUELHH | `settlementDate` | string | `yyyy-MM-dd`, **UK local** settlement day |
| FUELHH | `settlementPeriod` | integer | 1..48 (46 / 50 on clock-change days) |
| FUELHH | `fuelType` | string | `"WIND"` when filtered |

All timestamps observed are UTC with a `Z` suffix. No offsets or local times appear in either
dataset.

## 2. FUELHH (actuals, fuelType=WIND)

```json
{"dataset": "FUELHH", "publishTime": "2026-01-03T00:30:00Z", "startTime": "2026-01-03T00:00:00Z",
 "settlementDate": "2026-01-03", "settlementPeriod": 1, "fuelType": "WIND", "generation": 14380}
```

- **One row per startTime.** Settlement days 2026-01-03..04 gave 96 rows and 96 distinct
  startTimes. The wider window 2025-12-31..2026-02-02 gave 1632 rows and 1632 distinct startTimes.
- **No revisions visible.** `publishTime` is always exactly `startTime + 30 min`. If the data
  were revised, `publishTime` would be the distinguishing field, but the stream only ever
  shows one version per slot (see open questions).
- **No missing slots** from 2025-12-31 00:00Z to 2026-02-02 23:30Z. All gaps are 30 min, and
  no rows have generation <= 0.
- Resolution is 30 min. startTimes fall on `:00` and `:30`.
- `settlementDate` is the UK local day:
  - On 2026-06-15 (BST), SP1 starts `2026-06-14T23:00:00Z`.
  - 2026-03-29 (clocks forward) has 46 rows.
  - In January (GMT), settlement day = UTC day.
- Filtering by `publishDateTimeFrom/To` is **inclusive at both ends**. A 2-day publish window
  returned 97 rows, not 96.
- Rows came back in descending `startTime` order. Don't rely on the ordering.
- Jan sample: WIND generation 10,841 to 16,012 MW (3 to 4 Jan).

## 3. WINDFOR (forecasts)

```json
[
 {"dataset": "WINDFOR", "publishTime": "2026-01-01T11:30:00Z", "startTime": "2025-12-31T21:00:00Z", "generation": 19498},
 {"dataset": "WINDFOR", "publishTime": "2026-01-01T11:30:00Z", "startTime": "2025-12-31T22:00:00Z", "generation": 19866},
 {"dataset": "WINDFOR", "publishTime": "2026-01-01T11:30:00Z", "startTime": "2026-01-03T21:00:00Z", "generation": 16629}
]
```

- **Cadence: 8 publishes per day.** In winter (UTC = GMT) they are at
  02:30, 04:30, 07:30, 09:30, 11:30, 15:30, 18:30 and 22:30 UTC, so the gaps are 2, 3 or 4 h.
  - All 33 days from 2025-12-30 to 2026-01-31 had exactly 8 publishes (264 in total), with
    no gap over 4 h.
  - **Exception:** on 2026-01-15 the 11:30 publish appeared at **12:25** instead. Publish
    times are not guaranteed to follow the schedule.
- **Each publish has 73 hourly rows (all 264 checked).** They cover a fixed window from
  `D-1 21:00` to `D+2 21:00` UK local, where D is the publish day:
  - Winter: `21:00Z` to `21:00Z`.
  - Summer, 2026-06-15: `20:00Z` to `20:00Z`, which is 21:00 BST. So the window is anchored
    to UK local time.
- **Horizon (startTime - publishTime) runs from -25.5 h to +66.5 h** in the Jan sample.
  - **Every forecast includes up to ~25 h of past startTimes.** These are restated
    "forecasts" for slots that had already started.
  - Lookahead risk: picking "the latest publish for each startTime" without a cutoff would
    choose a forecast published *after* the target time. This is why the cutoff rule in
    `CLAUDE.md` matters.
- **Resolution: 60 min.** Every startTime is on `:00`. No `:30` slots occur, and the
  forecast startTime grid has no gaps over Dec 29 to Feb 2.
- No duplicate `(publishTime, startTime)` pairs.
- Jan sample: forecast generation 7,171 to 19,213 MW.
- Summer publish times are 03:30, 05:30, 08:30, 10:30, 12:30, 16:30, 19:30 and 23:30 UTC, which
  is +1 h in UTC compared with winter. Not relevant to the January scope.

### Aligning hourly forecasts with half-hourly actuals
FUELHH has 30-min slots and WINDFOR is hourly at `HH:00`. Options:
1. **Match on the hourly grid (recommended default).** Compare forecast `HH:00` with the actual
   for the `HH:00` slot only, and discard `HH:30` actuals from the metrics. This invents no
   forecast values and is easy to explain. It halves the sample (about 744 points for Jan).
2. Hold the forecast for both half-hours. `HH:30` takes the `HH:00` value. This keeps the 30-min
   unit, but adds error whenever wind ramps within the hour.
3. Linearly interpolate the forecast to `HH:30`. This is smoother, but assumes `HH:00` is a
   point value.
4. Average the two actual half-hours to compare with the hourly forecast. This assumes `HH:00`
   means the average over the hour `HH:00` to `HH+1:00`.

Which is right depends on what a WINDFOR `HH:00` value means, which is open question 2. Charts
can still show actuals at 30-min resolution and forecasts as hourly points. This choice affects
`CLAUDE.md`, which currently defines the core rule per 30-min slot. Record the final choice in
`docs/DECISIONS.md`.

## 4. Max range, pagination and chunking

There is no documented limit in the spec. Requests starting 2026-01-01:

| Range | FUELHH by settlementDate | FUELHH by publishDateTime | WINDFOR by publishDateTime |
|---|---|---|---|
| 7 d | 200, 384 rows, 1.3 s | 200, 337 rows | 200, 4,088 rows, 3.4 s |
| 31 d | 200, 1,536 rows, 9.2 s | 200, 1,489 rows | 200, 18,104 rows, 11.1 s |
| 62 d | 200, 3,024 rows | 200, 2,977 rows | 200, 36,208 rows, 23.4 s |
| 120 d | 200, 5,806 rows | 200, 5,761 rows | 200, 70,056 rows, 33.8 s |

- **No pagination exists, and no truncation was seen up to 120 days.** Row counts match the
  expected values exactly: 120-day FUELHH is 121×48 minus the 2 periods lost at the March
  clock change, and 31-day WINDFOR is 31×8×73 = 18,104.
- **Chunking is not required for correctness.** Still, fetch in weekly chunks with retries:
  latency grows with range (WINDFOR takes over 30 s for 120 days), and smaller requests make
  retries cheaper.
- Fetch offline with a script and commit the processed data to `data/`. Don't call Elexon
  from the deployed request path, because serverless timeouts and Elexon availability would
  both become risks.

## 5. What to download for January 2026 decisions

Default scope (from `CLAUDE.md`): decisions are made on D-1 in January, so delivery days run
from 2 Jan to 1 Feb 2026. All of January is GMT, so UK local = UTC.

| Data | Request | Resulting range |
|---|---|---|
| Actuals | FUELHH `settlementDateFrom=2026-01-02&settlementDateTo=2026-02-01&fuelType=WIND` | startTime `2026-01-02T00:00Z` .. `2026-02-01T23:30Z` (1,488 rows) |
| Forecasts | WINDFOR `publishDateTimeFrom=2025-12-30T00:00:00Z&publishDateTimeTo=2026-02-02T00:00:00Z` | publishTime `2025-12-30T02:30Z` .. `2026-02-01T22:30Z` (272 publishes, 19,856 rows). Extended to the end of the delivery window so horizon mode has same-day publishes (DECISIONS D-005) |

- **Why start forecasts on 30 Dec:**
  - A publish on day X covers startTimes up to X+2 21:00. The 31 Dec publishes therefore
    already cover all of 2 Jan, the first delivery day, except 21:00 to 23:00.
  - Starting on 30 Dec adds a day of margin in case a slot has no D-1 publish before the
    cutoff.
  - Rows published after a slot's cutoff are excluded by the selection rule, so
    over-fetching is safe.
- Required forecast startTime coverage is `2026-01-02T00:00Z` .. `2026-02-01T23:00Z`, and the
  forecast range above covers it.
- If the alternative scope is chosen (delivery days 1 to 31 Jan), shift both ranges back by a
  day. The 30 Dec start already covers this.
- Illustration only, since the cutoff is not decided: with a cutoff of 11:00 UK on D-1, the
  latest eligible publish is normally 09:30 on D-1. That gives horizons from about 14.5 h
  (D 00:00) to about 37.5 h (D 23:00). On 15 Jan, a cutoff between 11:30 and 12:25 would land
  in the late-publish gap.

## 6. Open questions

1. **Decision cutoff time on D-1.** Resolved as a configurable assumption: 09:00 UK
   (DECISIONS D-007).
   - The "about 11:00" figure first written here was out of date. 11:00 was the pre-Brexit
     gate time. Since 2021 the GB auctions close at about 09:20 (EPEX) and 09:50 (N2EX).
   - The client's real internal deadline should still be confirmed.
2. **What does WINDFOR `HH:00` represent?** It could be a point value, the average over
   `HH:00` to `HH+1:00`, or something else. Neither the spec nor the data says. This drives
   the alignment choice in §3.
3. **Are FUELHH values revised after first publication?**
   - The stream shows one row per slot with `publishTime = startTime + 30 min`.
   - Revisions, if any, overwrite in place without being visible. We would also not know
     whether today's values for January match what was published in January.
4. **Are FUELHH WIND values comparable to the WINDFOR scope?**
   - FUELHH WIND is transmission-metered generation.
   - Whether WINDFOR forecasts the same population (for example, whether embedded wind is
     excluded) is not stated in the spec.
   - A systematic bias in the metrics could come from a difference in scope rather than
     forecast skill.
5. **Is the WINDFOR publish-time filter inclusive at both ends?** It is for FUELHH. WINDFOR is
   assumed to match, but this is not verified.
6. **Rate limits:** none were documented in the spec and none were hit. Not tested beyond about
   20 requests.
