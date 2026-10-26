"""Probe the Elexon BMRS FUELHH and WINDFOR stream endpoints with small real calls.

Prints the endpoint contract (from the published OpenAPI spec), response shape,
field types, timestamp formats, row counts, and the facts we need for the
lookahead-safe forecast selection: duplicates, missing slots, publish cadence,
forecast horizons, and resolution.

Stdlib only. Usage:
    python scripts/probe_elexon.py               # small 1-2 day probes
    python scripts/probe_elexon.py --range-probe # also test max range per request
    python scripts/probe_elexon.py --coverage    # also check gaps over the Jan 2026 scope

On python.org macOS builds without CA certs, prefix with SSL_CERT_FILE=/etc/ssl/cert.pem.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
SPEC_URL = "https://data.elexon.co.uk/swagger/v1/swagger.json"
ENDPOINTS = ("/datasets/FUELHH/stream", "/datasets/WINDFOR/stream")


def get(url: str, params: dict[str, Any] | None = None) -> tuple[int, dict[str, str], Any, float]:
    """GET a URL; return (status, headers, parsed JSON or raw text, seconds)."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            status, headers = resp.status, dict(resp.headers)
    except urllib.error.HTTPError as e:
        body, status, headers = e.read().decode(), e.code, dict(e.headers)
    elapsed = time.monotonic() - t0
    try:
        return status, headers, json.loads(body), elapsed
    except json.JSONDecodeError:
        return status, headers, body, elapsed


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def hours(td: timedelta) -> float:
    return td.total_seconds() / 3600


def print_spec() -> None:
    print("=" * 78)
    print(f"OpenAPI spec: {SPEC_URL}")
    _, _, spec, _ = get(SPEC_URL)
    print(f"servers: {spec.get('servers')}")
    for path in ENDPOINTS:
        op = spec["paths"][path]["get"]
        print(f"\nGET {BASE_URL}{path}")
        for p in op.get("parameters", []):
            req = "required" if p.get("required") else "optional"
            print(f"  {p['name']:<22} {req:<9} {json.dumps(p.get('schema'))}")


def describe_rows(
    name: str,
    url: str,
    params: dict[str, Any],
    status: int,
    headers: dict[str, str],
    rows: Any,
    secs: float,
) -> None:
    print("\n" + "=" * 78)
    print(f"{name}: GET {url}?{urllib.parse.urlencode(params, doseq=True)}")
    print(f"status={status} time={secs:.1f}s content-type={headers.get('Content-Type')}")
    print(f"response top-level type: {type(rows).__name__}")
    if not isinstance(rows, list) or not rows:
        print(f"body: {str(rows)[:500]}")
        return
    print(f"row count: {len(rows)}")
    types: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        for k, v in r.items():
            types[k].add(type(v).__name__)
    print("fields: " + ", ".join(f"{k}:{'|'.join(sorted(t))}" for k, t in types.items()))
    print(
        f"raw timestamp samples: publishTime={rows[0]['publishTime']!r} "
        f"startTime={rows[0]['startTime']!r}"
    )
    print("first row:", json.dumps(rows[0]))
    print("last row: ", json.dumps(rows[-1]))


def analyse_fuelhh(rows: list[dict[str, Any]]) -> None:
    print("\n--- FUELHH analysis (fuelType=WIND) ---")
    print(f"fuelTypes present: {Counter(r['fuelType'] for r in rows)}")
    per_start = Counter(r["startTime"] for r in rows)
    dups = {k: v for k, v in per_start.items() if v > 1}
    print(f"distinct startTimes: {len(per_start)}; startTimes with >1 row: {len(dups)}")
    for k in list(dups)[:3]:
        print("  duplicate example:", [r for r in rows if r["startTime"] == k])
    starts = sorted(parse_ts(s) for s in per_start)
    gaps = [(a, b) for a, b in pairwise(starts) if b - a != timedelta(minutes=30)]
    print(f"startTime range: {starts[0].isoformat()} .. {starts[-1].isoformat()}")
    print(f"non-30-min gaps between consecutive startTimes: {gaps[:5] or 'none'}")
    sp_by_date = defaultdict(list)
    for r in rows:
        sp_by_date[r["settlementDate"]].append(r["settlementPeriod"])
    for d, sps in sorted(sp_by_date.items()):
        print(f"  settlementDate {d}: periods {min(sps)}..{max(sps)} (n={len(sps)})")
    lags = [hours(parse_ts(r["publishTime"]) - parse_ts(r["startTime"])) for r in rows]
    print(f"publishTime - startTime (h): min={min(lags):.2f} max={max(lags):.2f}")
    gens = [r["generation"] for r in rows]
    print(f"generation MW: min={min(gens)} max={max(gens)} mean={statistics.mean(gens):.0f}")


def analyse_windfor(rows: list[dict[str, Any]]) -> None:
    print("\n--- WINDFOR analysis ---")
    by_pub: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_pub[r["publishTime"]].append(r)
    pubs = sorted(parse_ts(p) for p in by_pub)
    print(f"distinct publishTimes: {len(pubs)}")
    print("publishTimes:", [p.strftime("%m-%d %H:%M") for p in pubs])
    cad = Counter(hours(b - a) for a, b in pairwise(pubs))
    print(f"publish cadence (h between publishes -> count): {dict(cad)}")
    print("per publish: rows, first/last startTime, horizon min/max (h), step(s) (min):")
    for p in sorted(by_pub, key=parse_ts):
        rs = sorted(by_pub[p], key=lambda r: r["startTime"])
        st = [parse_ts(r["startTime"]) for r in rs]
        hz = [hours(s - parse_ts(p)) for s in st]
        steps = sorted({int((b - a).total_seconds() // 60) for a, b in pairwise(st)})
        print(
            f"  {p}  n={len(rs):>3}  {rs[0]['startTime']} .. {rs[-1]['startTime']}  "
            f"h={min(hz):6.2f}..{max(hz):6.2f}  steps={steps}"
        )
    all_hz = [hours(parse_ts(r["startTime"]) - parse_ts(r["publishTime"])) for r in rows]
    print(
        f"overall horizon (startTime - publishTime) h: min={min(all_hz):.2f} max={max(all_hz):.2f}"
    )
    minutes = Counter(parse_ts(r["startTime"]).minute for r in rows)
    print(f"startTime minute-of-hour distribution: {dict(minutes)}")
    dup = Counter((r["publishTime"], r["startTime"]) for r in rows)
    print(f"(publishTime, startTime) pairs with >1 row: {sum(1 for v in dup.values() if v > 1)}")
    gens = [r["generation"] for r in rows]
    print(f"generation MW: min={min(gens)} max={max(gens)}")


def range_probe() -> None:
    """Find whether large ranges are rejected, truncated, or served."""
    print("\n" + "=" * 78)
    print("RANGE PROBE (max date range per request)")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for days in (7, 31, 62, 120):
        end = start + timedelta(days=days)
        cases = [
            (
                "FUELHH settlementDate",
                "/datasets/FUELHH/stream",
                {
                    "settlementDateFrom": start.date().isoformat(),
                    "settlementDateTo": end.date().isoformat(),
                    "fuelType": "WIND",
                },
            ),
            (
                "FUELHH publishDateTime",
                "/datasets/FUELHH/stream",
                {
                    "publishDateTimeFrom": start.isoformat().replace("+00:00", "Z"),
                    "publishDateTimeTo": end.isoformat().replace("+00:00", "Z"),
                    "fuelType": "WIND",
                },
            ),
            (
                "WINDFOR publishDateTime",
                "/datasets/WINDFOR/stream",
                {
                    "publishDateTimeFrom": start.isoformat().replace("+00:00", "Z"),
                    "publishDateTimeTo": end.isoformat().replace("+00:00", "Z"),
                },
            ),
        ]
        for label, path, params in cases:
            status, _, body, secs = get(BASE_URL + path, params)
            if isinstance(body, list):
                last = max((r["startTime"] for r in body), default=None)
                lastp = max((r["publishTime"] for r in body), default=None)
                info = f"rows={len(body)} max startTime={last} max publishTime={lastp}"
            else:
                info = f"body={str(body)[:300]}"
            print(f"  {days:>3}d {label:<24} status={status} {secs:5.1f}s {info}")


def coverage_check() -> None:
    """Check the full January 2026 decision scope for gaps, plus a BST day."""
    print("\n" + "=" * 78)
    print("COVERAGE CHECK (Jan 2026 decision scope)")
    _, _, act, secs = get(
        BASE_URL + "/datasets/FUELHH/stream",
        {"settlementDateFrom": "2025-12-31", "settlementDateTo": "2026-02-02", "fuelType": "WIND"},
    )
    starts = sorted({parse_ts(r["startTime"]) for r in act})
    print(
        f"FUELHH rows={len(act)} distinct startTimes={len(starts)} ({secs:.1f}s) "
        f"{starts[0]} .. {starts[-1]}"
    )
    gaps = [(a, b) for a, b in pairwise(starts) if b - a != timedelta(minutes=30)]
    print(f"  missing half-hours: {gaps or 'none'}")
    print(f"  zero/negative generation rows: {sum(1 for r in act if r['generation'] <= 0)}")

    _, _, fc, secs = get(
        BASE_URL + "/datasets/WINDFOR/stream",
        {
            "publishDateTimeFrom": "2025-12-30T00:00:00Z",
            "publishDateTimeTo": "2026-02-01T00:00:00Z",
        },
    )
    pubs = sorted({parse_ts(r["publishTime"]) for r in fc})
    print(
        f"WINDFOR rows={len(fc)} distinct publishTimes={len(pubs)} ({secs:.1f}s) "
        f"{pubs[0]} .. {pubs[-1]}"
    )
    per_day = Counter(p.date() for p in pubs)
    print(
        f"  publishes per UTC day: {sorted(Counter(per_day.values()).items())} "
        "(publishes/day -> number of days)"
    )
    print(f"  publish clock times (UTC): {sorted({p.strftime('%H:%M') for p in pubs})}")
    big = [(a, b) for a, b in pairwise(pubs) if b - a > timedelta(hours=4)]
    print(f"  publish gaps > 4h: {big or 'none'}")
    sizes = Counter(Counter(r["publishTime"] for r in fc).values())
    print(f"  rows per publish -> count: {dict(sizes)}")
    stimes = sorted({parse_ts(r["startTime"]) for r in fc})
    hgaps = [(a, b) for a, b in pairwise(stimes) if b - a != timedelta(hours=1)]
    print(
        f"  forecast startTime range {stimes[0]} .. {stimes[-1]}; non-hourly gaps: "
        f"{hgaps or 'none'}"
    )

    # Summer (BST) day: do publish times and windows shift in UTC?
    _, _, summer, _ = get(
        BASE_URL + "/datasets/WINDFOR/stream",
        {
            "publishDateTimeFrom": "2026-06-15T00:00:00Z",
            "publishDateTimeTo": "2026-06-16T00:00:00Z",
        },
    )
    by_pub: dict[str, list[str]] = defaultdict(list)
    for r in summer:
        by_pub[r["publishTime"]].append(r["startTime"])
    print("BST check WINDFOR 2026-06-15 (UTC): publishTime -> first..last startTime")
    for p in sorted(by_pub):
        print(f"  {p} -> {min(by_pub[p])} .. {max(by_pub[p])} n={len(by_pub[p])}")
    _, _, sact, _ = get(
        BASE_URL + "/datasets/FUELHH/stream",
        {"settlementDateFrom": "2026-06-15", "settlementDateTo": "2026-06-15", "fuelType": "WIND"},
    )
    sact.sort(key=lambda r: r["startTime"])
    print(
        f"BST check FUELHH settlementDate 2026-06-15: SP{sact[0]['settlementPeriod']} "
        f"starts {sact[0]['startTime']}, SP{sact[-1]['settlementPeriod']} starts "
        f"{sact[-1]['startTime']}"
    )
    _, _, dst, _ = get(
        BASE_URL + "/datasets/FUELHH/stream",
        {"settlementDateFrom": "2026-03-29", "settlementDateTo": "2026-03-29", "fuelType": "WIND"},
    )
    print(f"DST check FUELHH settlementDate 2026-03-29 (clocks forward): rows={len(dst)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range-probe", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    args = ap.parse_args()

    print_spec()

    # FUELHH actuals for two settlement days in early Jan 2026.
    url = BASE_URL + "/datasets/FUELHH/stream"
    params = {
        "settlementDateFrom": "2026-01-03",
        "settlementDateTo": "2026-01-04",
        "fuelType": "WIND",
    }
    status, headers, rows, secs = get(url, params)
    describe_rows("FUELHH", url, params, status, headers, rows, secs)
    if isinstance(rows, list) and rows:
        analyse_fuelhh(rows)

    # Same FUELHH data filtered by publish time instead (does it differ?).
    params = {
        "publishDateTimeFrom": "2026-01-03T00:00:00Z",
        "publishDateTimeTo": "2026-01-05T00:00:00Z",
        "fuelType": "WIND",
    }
    status, headers, rows, secs = get(url, params)
    describe_rows("FUELHH (by publishTime)", url, params, status, headers, rows, secs)

    # WINDFOR forecasts published over ~1.5 days in early Jan 2026.
    url = BASE_URL + "/datasets/WINDFOR/stream"
    params = {
        "publishDateTimeFrom": "2026-01-02T00:00:00Z",
        "publishDateTimeTo": "2026-01-03T12:00:00Z",
    }
    status, headers, rows, secs = get(url, params)
    describe_rows("WINDFOR", url, params, status, headers, rows, secs)
    if isinstance(rows, list) and rows:
        analyse_windfor(rows)

    # WINDFOR with no filters: spec says it returns the latest published forecast.
    status, headers, rows, secs = get(url, {})
    describe_rows("WINDFOR (no params)", url, {}, status, headers, rows, secs)

    if args.range_probe:
        range_probe()
    if args.coverage:
        coverage_check()


if __name__ == "__main__":
    main()
