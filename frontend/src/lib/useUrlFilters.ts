import { useCallback, useEffect, useState } from "react";

import { type Bounds, type Filters, parseFilters, serializeFilters } from "./filters";

/** Filters held in state and mirrored into the URL, so any view can be shared as a link. */
export function useUrlFilters(defaults: Filters, bounds: Bounds) {
  const [filters, setFilters] = useState<Filters>(() =>
    parseFilters(window.location.search, defaults, bounds),
  );

  useEffect(() => {
    const qs = serializeFilters(filters, defaults);
    if (qs !== window.location.search) {
      window.history.replaceState(null, "", `${window.location.pathname}${qs}`);
    }
  }, [filters, defaults]);

  const update = useCallback(
    (patch: Partial<Filters>) => setFilters((current) => ({ ...current, ...patch })),
    [],
  );
  const reset = useCallback(() => setFilters(defaults), [defaults]);

  return { filters, update, reset };
}
