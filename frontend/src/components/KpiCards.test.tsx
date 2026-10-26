import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { MetricsResponse } from "../api/types";
import { KpiCards } from "./KpiCards";

function metrics(slotMinutes: number): MetricsResponse {
  return {
    query: {
      start: "2026-01-02",
      end: "2026-02-01",
      mode: "day_ahead",
      horizon_h: null,
      gate_time: "09:00:00",
      cutoff_rule: "rule",
    },
    coverage: {
      slots: 744,
      with_forecast: 744,
      with_actual: 744,
      paired: 744,
      pct_with_forecast: 100,
      pct_with_actual: 100,
      pct_paired: 100,
    },
    overall: {
      n: 744,
      mae_mw: 2022.4,
      rmse_mw: 2497,
      bias_mw: 1746.2,
      mean_actual_mw: 11286,
      nmae: 0.1792,
    },
    distribution: {
      signed_mw: { p10: -426, p50: 1582, p90: 4154, p95: 5268, p99: 6139 },
      absolute_mw: { p10: 1, p50: 2, p90: 3, p95: 4, p99: 5 },
    },
    buffer: {
      levels: [
        { coverage: 0.9, buffer_mw: 4158, message: "" },
        { coverage: 0.95, buffer_mw: 5285, message: "" },
      ],
      shortfall_share: 0.85,
      slot_minutes: slotMinutes,
      method: "",
    },
    by_day: [],
    worst_slots: [],
  };
}

describe("KpiCards", () => {
  it("states the P90 buffer in plain English, rounded", () => {
    render(<KpiCards metrics={metrics(60)} />);

    expect(screen.getByText(/Hold ~4,160 MW extra to cover 90% of hours\./)).toBeInTheDocument();
    expect(screen.getByText(/P95: ~5,290 MW/)).toBeInTheDocument();
  });

  it("names half-hours when slots are half-hourly", () => {
    render(<KpiCards metrics={metrics(30)} />);

    expect(screen.getByText(/to cover 90% of half-hours\./)).toBeInTheDocument();
  });

  it("shows signed bias and how often the forecast was too high", () => {
    render(<KpiCards metrics={metrics(60)} />);

    expect(screen.getByText("+1,746 MW")).toBeInTheDocument();
    expect(screen.getByText(/forecast above actual in 85% of hours/)).toBeInTheDocument();
    expect(screen.getByText("17.9%")).toBeInTheDocument();
  });
});
