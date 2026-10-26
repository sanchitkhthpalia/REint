import type {
  AnalysisQuery,
  ByHorizonResponse,
  ByHourResponse,
  MetaResponse,
  MetricsResponse,
  RangeQuery,
  SeriesResponse,
  ValidationErrorItem,
} from "./types";

// Same-origin by default: Vite proxies /api in dev, Vercel serves /api in production.
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "";

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors: FieldError[];

  constructor(
    status: number,
    message: string,
    fieldErrors: FieldError[] = [],
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

type QueryValue = string | number | null | undefined;

export function buildQueryString(params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

function toFieldErrors(detail: unknown): FieldError[] {
  if (!Array.isArray(detail)) return [];
  return (detail as ValidationErrorItem[]).map((item) => ({
    field: String(item.loc[item.loc.length - 1] ?? "request"),
    message: item.msg,
  }));
}

export async function getJson<T>(
  path: string,
  params?: Record<string, QueryValue>,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}${buildQueryString(params)}`, {
      headers: { Accept: "application/json" },
      ...init,
    });
  } catch (cause) {
    throw new ApiError(0, "Cannot reach the API. Check your connection and try again.", [], {
      cause,
    });
  }
  if (response.ok) return (await response.json()) as T;

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON error body (e.g. a proxy error page); fall through to a generic message.
  }
  const detail = (body as { detail?: unknown } | null)?.detail;
  const fieldErrors = toFieldErrors(detail);
  const message =
    fieldErrors.length > 0
      ? `Invalid request: ${fieldErrors.map((e) => `${e.field}: ${e.message}`).join("; ")}`
      : typeof detail === "string"
        ? detail
        : `Request failed (HTTP ${response.status})`;
  throw new ApiError(response.status, message, fieldErrors);
}

export const api = {
  meta: (init?: RequestInit) => getJson<MetaResponse>("/api/meta", undefined, init),
  series: (q: AnalysisQuery, init?: RequestInit) => getJson<SeriesResponse>("/api/series", q, init),
  metrics: (q: AnalysisQuery, init?: RequestInit) =>
    getJson<MetricsResponse>("/api/metrics", q, init),
  byHour: (q: AnalysisQuery, init?: RequestInit) =>
    getJson<ByHourResponse>("/api/metrics/by-hour", q, init),
  byHorizon: (q: RangeQuery, init?: RequestInit) =>
    getJson<ByHorizonResponse>("/api/metrics/by-horizon", q, init),
};
