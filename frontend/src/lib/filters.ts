import type { AnalysisQuery, MetaResponse, Mode, RangeQuery } from "../api/types";

/** Dashboard filters. Mirrors the API query, and is reflected in the page URL. */
export interface Filters {
  start: string; // YYYY-MM-DD, UK delivery day
  end: string;
  mode: Mode;
  horizonH: number; // used when mode = horizon
  gateTime: string; // HH:MM Europe/London, used when mode = day_ahead
}

export interface Bounds {
  min: string;
  max: string;
  horizonMin: number;
  horizonMax: number;
}

/** Gate times offered in the selector. 09:20 / 09:50 are the GB day-ahead auction closures. */
export const GATE_TIME_OPTIONS: { value: string; label: string }[] = [
  { value: "07:00", label: "07:00" },
  { value: "08:00", label: "08:00" },
  { value: "09:00", label: "09:00 (default)" },
  { value: "09:20", label: "09:20 (EPEX GB auction)" },
  { value: "09:50", label: "09:50 (N2EX GB auction)" },
  { value: "10:00", label: "10:00" },
  { value: "11:00", label: "11:00" },
  { value: "12:00", label: "12:00" },
];

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const HH_MM = /^([01]\d|2[0-3]):[0-5]\d$/;

export function defaultsFromMeta(meta: MetaResponse): { defaults: Filters; bounds: Bounds } {
  return {
    defaults: {
      start: meta.defaults.start,
      end: meta.defaults.end,
      mode: meta.defaults.mode,
      horizonH: meta.defaults.horizon_h,
      gateTime: meta.defaults.gate_time.slice(0, 5),
    },
    bounds: {
      min: meta.date_range.first_delivery_day,
      max: meta.date_range.last_delivery_day,
      horizonMin: meta.limits.horizon_h_min,
      horizonMax: meta.limits.horizon_h_max,
    },
  };
}

function isValidDate(value: string): boolean {
  return ISO_DATE.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));
}

/** Read filters from a URL query string. Anything missing or invalid falls back to defaults. */
export function parseFilters(search: string, defaults: Filters, bounds: Bounds): Filters {
  const params = new URLSearchParams(search);
  const inRange = (d: string | null): d is string =>
    d !== null && isValidDate(d) && d >= bounds.min && d <= bounds.max;

  let start = params.get("start");
  let end = params.get("end");
  start = inRange(start) ? start : defaults.start;
  end = inRange(end) ? end : defaults.end;
  if (start > end) [start, end] = [defaults.start, defaults.end];

  const modeParam = params.get("mode");
  const mode: Mode = modeParam === "horizon" || modeParam === "day_ahead" ? modeParam : defaults.mode;

  const h = Number(params.get("horizon_h"));
  const horizonH =
    params.has("horizon_h") && Number.isFinite(h) && h >= bounds.horizonMin && h <= bounds.horizonMax
      ? h
      : defaults.horizonH;

  const gate = params.get("gate_time");
  const gateTime = gate !== null && HH_MM.test(gate) ? gate : defaults.gateTime;

  return { start, end, mode, horizonH, gateTime };
}

/** Write filters as a URL query string. Only values that differ from the defaults appear. */
export function serializeFilters(filters: Filters, defaults: Filters): string {
  const params = new URLSearchParams();
  if (filters.start !== defaults.start) params.set("start", filters.start);
  if (filters.end !== defaults.end) params.set("end", filters.end);
  if (filters.mode !== defaults.mode) params.set("mode", filters.mode);
  if (filters.mode === "horizon") params.set("horizon_h", String(filters.horizonH));
  if (filters.mode === "day_ahead" && filters.gateTime !== defaults.gateTime) {
    params.set("gate_time", filters.gateTime);
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

/** The API query for the current filters: only the parameters the chosen mode uses. */
export function toAnalysisQuery(filters: Filters): AnalysisQuery {
  const base = { start: filters.start, end: filters.end, mode: filters.mode };
  return filters.mode === "horizon"
    ? { ...base, horizon_h: filters.horizonH }
    : { ...base, gate_time: filters.gateTime };
}

export function toRangeQuery(filters: Filters): RangeQuery {
  return { start: filters.start, end: filters.end };
}
