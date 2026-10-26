import type { ReactNode } from "react";

import type { MetricsResponse } from "../api/types";
import { P90, bufferLevel } from "../lib/buffer";
import { approxMw, formatDay, formatMw, formatPct, slotWord } from "../lib/format";

const B = ({ children }: { children: ReactNode }) => (
  <strong className="num font-semibold text-slate-50">{children}</strong>
);

/** One plain-English paragraph so a buyer gets the answer without reading any chart. */
export function Summary({ metrics }: { metrics: MetricsResponse }) {
  const { query, overall, buffer } = metrics;
  const p90 = bufferLevel(buffer, P90);
  const unit = slotWord(buffer.slot_minutes);
  const which =
    query.mode === "day_ahead"
      ? `available at ${query.gate_time?.slice(0, 5)} the day before`
      : `published at least ${query.horizon_h} h ahead`;
  if (overall.mae_mw === null) return null;

  return (
    <p className="rounded-lg border border-sky-900/60 bg-sky-950/30 px-4 py-3 text-sm leading-relaxed text-slate-200">
      {formatDay(query.start)} to {formatDay(query.end)}: the wind forecast {which} missed by{" "}
      <B>{formatMw(overall.mae_mw)}</B> in a typical hour and was too high in{" "}
      <B>{formatPct(buffer.shortfall_share, 0)}</B> of {unit}.
      {p90?.buffer_mw != null && (
        <>
          {" "}
          Holding <B>{approxMw(p90.buffer_mw)} MW</B> extra would have covered the shortfall in 90%
          of {unit}
          {p90.walk_forward_coverage != null && (
            <>
              {" "}
              (<B>{formatPct(p90.walk_forward_coverage, 0)}</B> if sized only from earlier days, as
              you would in practice)
            </>
          )}
          .
        </>
      )}
    </p>
  );
}
