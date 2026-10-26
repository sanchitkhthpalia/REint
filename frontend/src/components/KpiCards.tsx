import type { ReactNode } from "react";

import type { MetricsResponse } from "../api/types";
import { approxMw, formatMw, formatPct, formatSignedMw, slotWord } from "../lib/format";

function Card({
  label,
  value,
  note,
  highlight = false,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex flex-col gap-1 rounded-lg border p-4 ${
        highlight ? "border-amber-500/60 bg-amber-500/10" : "border-slate-800 bg-slate-900/80"
      }`}
    >
      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-400">{label}</span>
      <span className="num text-2xl font-semibold text-slate-50">{value}</span>
      {note && <span className="text-xs leading-snug text-slate-300">{note}</span>}
    </div>
  );
}

export function KpiCards({ metrics }: { metrics: MetricsResponse }) {
  const { overall, buffer, coverage } = metrics;
  const p90 = buffer.levels.find((l) => l.coverage === 0.9);
  const p95 = buffer.levels.find((l) => l.coverage === 0.95);
  const unit = slotWord(buffer.slot_minutes);
  const bias = overall.bias_mw;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card
        label="Mean absolute error"
        value={formatMw(overall.mae_mw)}
        note={`${overall.n} of ${coverage.slots} ${unit} with forecast and actual`}
      />
      <Card
        label="Bias (forecast − actual)"
        value={formatSignedMw(bias)}
        note={
          bias === null
            ? undefined
            : `${bias > 0 ? "Over-forecast" : "Under-forecast"} on average · forecast above actual in ${formatPct(buffer.shortfall_share, 0)} of ${unit}`
        }
      />
      <Card
        label="nMAE"
        value={formatPct(overall.nmae)}
        note={`MAE as a share of mean actual wind (${formatMw(overall.mean_actual_mw)})`}
      />
      <Card
        highlight
        label="P90 procurement buffer"
        value={p90?.buffer_mw == null ? "–" : `${approxMw(p90.buffer_mw)} MW`}
        note={
          p90?.buffer_mw == null ? (
            "Not enough data to size a buffer."
          ) : (
            <>
              Hold {approxMw(p90.buffer_mw)} MW extra to cover 90% of {unit}.
              {p95?.buffer_mw != null && (
                <span className="text-slate-400"> P95: {approxMw(p95.buffer_mw)} MW.</span>
              )}
            </>
          )
        }
      />
    </div>
  );
}
