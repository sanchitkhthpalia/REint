import type { ReactNode } from "react";

import type { MetricsResponse } from "../api/types";
import { P90, P95, bufferLevel } from "../lib/buffer";
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
  const p90 = bufferLevel(buffer, P90);
  const p95 = bufferLevel(buffer, P95);
  const unit = slotWord(buffer.slot_minutes);
  const bias = overall.bias_mw;

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card
        label="Typical miss"
        value={formatMw(overall.mae_mw)}
        note={`Average size of the hourly forecast error (MAE) · ${overall.n} of ${coverage.slots} ${unit} have both forecast and actual`}
      />
      <Card
        label="Average bias"
        value={formatSignedMw(bias)}
        note={
          bias === null
            ? undefined
            : `Forecast ${bias > 0 ? "too high" : "too low"} on average · above actual in ${formatPct(buffer.shortfall_share, 0)} of ${unit}`
        }
      />
      <Card
        label="Miss vs typical output"
        value={formatPct(overall.nmae)}
        note={`Typical miss as a share of average wind output, ${formatMw(overall.mean_actual_mw)} (nMAE)`}
      />
      <Card
        highlight
        label="Recommended buffer (P90)"
        value={p90?.buffer_mw == null ? "–" : `${approxMw(p90.buffer_mw)} MW`}
        note={
          p90?.buffer_mw == null ? (
            "Not enough data to size a buffer."
          ) : (
            <>
              Hold {approxMw(p90.buffer_mw)} MW extra to cover 90% of {unit}.
              {p90.walk_forward_coverage != null && (
                <>
                  {" "}
                  Sized only from earlier days, it covered{" "}
                  {formatPct(p90.walk_forward_coverage, 0)}.
                </>
              )}
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
