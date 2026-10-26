import type { WorstSlot } from "../api/types";
import { COLORS } from "../lib/colors";
import { formatHours, formatMw, formatSignedMw, formatUkDateTime } from "../lib/format";

const th = "px-3 py-2 text-left text-[11px] font-medium uppercase tracking-wider text-slate-400";
const td = "num whitespace-nowrap px-3 py-1.5 text-sm";

export function WorstMissesTable({ rows }: { rows: readonly WorstSlot[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse">
        <caption className="sr-only">Ten largest forecast errors by absolute size</caption>
        <thead className="border-b border-slate-800">
          <tr>
            <th scope="col" className={th}>
              #
            </th>
            <th scope="col" className={th}>
              Slot (UK)
            </th>
            <th scope="col" className={`${th} text-right`}>
              Forecast
            </th>
            <th scope="col" className={`${th} text-right`}>
              Actual
            </th>
            <th scope="col" className={`${th} text-right`}>
              Error
            </th>
            <th scope="col" className={th}>
              Forecast published (UK)
            </th>
            <th scope="col" className={`${th} text-right`}>
              Lead
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.target_time_utc} className="border-b border-slate-800/60 hover:bg-slate-800/40">
              <td className={`${td} text-slate-500`}>{i + 1}</td>
              <td className={`${td} text-slate-200`}>{formatUkDateTime(r.target_time_utc)}</td>
              <td className={`${td} text-right text-slate-200`}>{formatMw(r.forecast_mw)}</td>
              <td className={`${td} text-right text-slate-200`}>{formatMw(r.actual_mw)}</td>
              <td
                className={`${td} text-right font-medium`}
                style={{ color: r.error_mw > 0 ? COLORS.over : COLORS.under }}
              >
                {formatSignedMw(r.error_mw)}
              </td>
              <td className={`${td} text-slate-300`}>{formatUkDateTime(r.publish_time_utc)}</td>
              <td className={`${td} text-right text-slate-300`}>{formatHours(r.lead_time_hours)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
