import type { MetricsResponse } from "../api/types";

/** A /api/metrics response shaped like the real January day-ahead result. */
export function metricsFixture(overrides: { slotMinutes?: number; mode?: "day_ahead" | "horizon" } = {}): MetricsResponse {
  const mode = overrides.mode ?? "day_ahead";
  return {
    query: {
      start: "2026-01-02",
      end: "2026-02-01",
      mode,
      horizon_h: mode === "horizon" ? 6 : null,
      gate_time: mode === "day_ahead" ? "09:00:00" : null,
      cutoff_rule: "rule",
    },
    coverage: {
      slots: 744,
      with_forecast: 744,
      with_actual: 744,
      paired: 744,
      share_with_forecast: 1,
      share_with_actual: 1,
      share_paired: 1,
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
        { coverage: 0.9, buffer_mw: 4158, message: "", walk_forward_coverage: 0.861 },
        { coverage: 0.95, buffer_mw: 5285, message: "", walk_forward_coverage: 0.898 },
      ],
      shortfall_share: 0.85,
      slot_minutes: overrides.slotMinutes ?? 60,
      walk_forward_days: 24,
      method: "",
    },
    by_day: [],
    worst_slots: [],
  };
}
