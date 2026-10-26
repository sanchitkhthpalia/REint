import { describe, expect, it } from "vitest";

import {
  type Bounds,
  type Filters,
  parseFilters,
  serializeFilters,
  toAnalysisQuery,
} from "./filters";

const defaults: Filters = {
  start: "2026-01-02",
  end: "2026-02-01",
  mode: "day_ahead",
  horizonH: 24,
  gateTime: "09:00",
};
const bounds: Bounds = { min: "2026-01-02", max: "2026-02-01", horizonMin: 0, horizonMax: 48 };

describe("URL filters", () => {
  it("round-trips a non-default view through the URL", () => {
    const view: Filters = { ...defaults, start: "2026-01-10", mode: "horizon", horizonH: 6 };

    const qs = serializeFilters(view, defaults);

    expect(qs).toBe("?start=2026-01-10&mode=horizon&horizon_h=6");
    expect(parseFilters(qs, defaults, bounds)).toEqual(view);
  });

  it("keeps the default view's URL clean", () => {
    expect(serializeFilters(defaults, defaults)).toBe("");
  });

  it("writes a non-default gate time only in day-ahead mode", () => {
    expect(serializeFilters({ ...defaults, gateTime: "09:50" }, defaults)).toBe("?gate_time=09%3A50");
  });

  it.each([
    ["?start=2025-12-01", "dates outside the dataset"],
    ["?start=2026-01-20&end=2026-01-10", "start after end"],
    ["?start=not-a-date", "malformed dates"],
    ["?mode=intraday", "unknown modes"],
    ["?mode=horizon&horizon_h=99", "horizons above 48 h"],
    ["?mode=horizon&horizon_h=abc", "non-numeric horizons"],
    ["?gate_time=25:00", "invalid gate times"],
  ])("falls back to defaults for %s (%s)", (qs) => {
    const parsed = parseFilters(qs, defaults, bounds);

    expect(parsed.start <= parsed.end).toBe(true);
    expect(parsed.start >= bounds.min && parsed.end <= bounds.max).toBe(true);
    expect(["day_ahead", "horizon"]).toContain(parsed.mode);
    expect(parsed.horizonH).toBeLessThanOrEqual(48);
    expect(parsed.gateTime).toMatch(/^\d{2}:\d{2}$/);
  });

  it("accepts a horizon of zero", () => {
    expect(parseFilters("?mode=horizon&horizon_h=0", defaults, bounds).horizonH).toBe(0);
  });
});

describe("toAnalysisQuery", () => {
  it("sends gate_time but not horizon_h in day-ahead mode", () => {
    expect(toAnalysisQuery(defaults)).toEqual({
      start: "2026-01-02",
      end: "2026-02-01",
      mode: "day_ahead",
      gate_time: "09:00",
    });
  });

  it("sends horizon_h but not gate_time in horizon mode", () => {
    expect(toAnalysisQuery({ ...defaults, mode: "horizon", horizonH: 0 })).toEqual({
      start: "2026-01-02",
      end: "2026-02-01",
      mode: "horizon",
      horizon_h: 0,
    });
  });
});
