import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  subtitle?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function Panel({ title, subtitle, className = "", children }: PanelProps) {
  return (
    <section
      aria-label={title}
      className={`rounded-lg border border-slate-800 bg-slate-900/80 p-4 ${className}`}
    >
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-sm font-semibold tracking-wide text-slate-100">{title}</h2>
        {subtitle && <p className="text-xs text-slate-400">{subtitle}</p>}
      </header>
      {children}
    </section>
  );
}

interface QueryStateProps<T> {
  query: UseQueryResult<T>;
  height: number;
  isEmpty?: (data: T) => boolean;
  emptyMessage?: string;
  children: (data: T) => ReactNode;
}

/** Loading skeleton, error with retry, empty state, or the content. */
export function QueryState<T>({
  query,
  height,
  isEmpty,
  emptyMessage = "No data for this selection.",
  children,
}: QueryStateProps<T>) {
  if (query.isPending) {
    return (
      <div
        role="status"
        aria-label="Loading"
        className="animate-pulse rounded bg-slate-800/60"
        style={{ height }}
      />
    );
  }
  if (query.isError) {
    return (
      <div
        role="alert"
        className="flex flex-col items-center justify-center gap-2 rounded border border-rose-900 bg-rose-950/40 p-4 text-center text-sm text-rose-200"
        style={{ minHeight: height }}
      >
        <p>{query.error.message}</p>
        <button
          type="button"
          onClick={() => void query.refetch()}
          className="rounded border border-rose-700 px-3 py-1 text-xs hover:bg-rose-900/50"
        >
          Retry
        </button>
      </div>
    );
  }
  if (isEmpty?.(query.data)) {
    return (
      <div
        className="flex items-center justify-center rounded border border-dashed border-slate-700 text-sm text-slate-400"
        style={{ minHeight: height }}
      >
        {emptyMessage}
      </div>
    );
  }
  return (
    <div className={`relative ${query.isPlaceholderData ? "opacity-60" : ""}`} aria-busy={query.isFetching}>
      {children(query.data)}
    </div>
  );
}
