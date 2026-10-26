import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "./client";
import type { AnalysisQuery, RangeQuery } from "./types";

// The snapshot is immutable, so successful results never go stale within a session.
const IMMUTABLE = { staleTime: Infinity, gcTime: 30 * 60 * 1000 } as const;

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: ({ signal }) => api.meta({ signal }),
    ...IMMUTABLE,
  });
}

// keepPreviousData keeps the last chart on screen while a new filter combination loads.
export function useSeries(q: AnalysisQuery) {
  return useQuery({
    queryKey: ["series", q],
    queryFn: ({ signal }) => api.series(q, { signal }),
    placeholderData: keepPreviousData,
    ...IMMUTABLE,
  });
}

export function useMetrics(q: AnalysisQuery) {
  return useQuery({
    queryKey: ["metrics", q],
    queryFn: ({ signal }) => api.metrics(q, { signal }),
    placeholderData: keepPreviousData,
    ...IMMUTABLE,
  });
}

export function useByHour(q: AnalysisQuery) {
  return useQuery({
    queryKey: ["by-hour", q],
    queryFn: ({ signal }) => api.byHour(q, { signal }),
    placeholderData: keepPreviousData,
    ...IMMUTABLE,
  });
}

export function useByHorizon(q: RangeQuery) {
  return useQuery({
    queryKey: ["by-horizon", q],
    queryFn: ({ signal }) => api.byHorizon(q, { signal }),
    placeholderData: keepPreviousData,
    ...IMMUTABLE,
  });
}
