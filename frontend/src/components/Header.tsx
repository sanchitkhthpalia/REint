import type { MetaResponse } from "../api/types";
import { formatLongDate } from "../lib/format";

export function Header({ meta }: { meta: MetaResponse }) {
  const snapshot = meta.snapshot as { fetched_at_utc?: string; snapshot_id?: string };
  const fetched = snapshot.fetched_at_utc ? formatLongDate(snapshot.fetched_at_utc) : "unknown date";
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-slate-50">
          Wind Forecast Monitor
          <span className="ml-2 text-sm font-normal text-slate-400">GB day-ahead · national wind</span>
        </h1>
      </div>
      <span
        className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-300"
        title={`Snapshot ${snapshot.snapshot_id ?? ""}: FUELHH (WIND) actuals and WINDFOR forecasts`}
      >
        <span className="size-1.5 rounded-full bg-emerald-400" aria-hidden />
        Elexon BMRS · snapshot {fetched}
      </span>
    </header>
  );
}
