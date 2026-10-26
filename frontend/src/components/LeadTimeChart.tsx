import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { LeadTimePoint, Mode } from "../api/types";
import { COLORS } from "../lib/colors";
import { formatMw } from "../lib/format";

interface LeadTimeChartProps {
  points: readonly LeadTimePoint[];
  mode: Mode;
  horizonH: number;
  /** Lead-time range used by the current day-ahead selection, to show where it sits. */
  dayAheadLeads: [number, number] | null;
}

export function LeadTimeChart({ points, mode, horizonH, dayAheadLeads }: LeadTimeChartProps) {
  return (
    <div className="h-64 w-full" role="img" aria-label="Forecast error against forecast horizon">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points as LeadTimePoint[]} margin={{ top: 4, right: 8, bottom: 12, left: 8 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis
            dataKey="horizon_hours"
            type="number"
            domain={[0, 48]}
            ticks={[0, 6, 12, 18, 24, 30, 36, 42, 48]}
            stroke={COLORS.axis}
            tick={{ fontSize: 11 }}
            label={{
              value: "Horizon H (forecast published ≥ H h before slot)",
              position: "insideBottom",
              offset: -8,
              fill: COLORS.axis,
              fontSize: 11,
            }}
          />
          <YAxis
            stroke={COLORS.axis}
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`}
            width={40}
          />
          <Tooltip
            contentStyle={{ background: "#020617", border: "1px solid #334155", fontSize: 12 }}
            labelFormatter={(h) => `H = ${String(h)} h`}
            formatter={(v) => formatMw(typeof v === "number" ? v : null)}
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} verticalAlign="top" />
          {mode === "day_ahead" && dayAheadLeads && (
            <ReferenceArea
              x1={dayAheadLeads[0]}
              x2={Math.min(48, dayAheadLeads[1])}
              fill={COLORS.reference}
              fillOpacity={0.06}
              label={{ value: "day-ahead leads", fill: COLORS.axis, fontSize: 10, position: "insideTop" }}
            />
          )}
          {mode === "horizon" && (
            <ReferenceLine x={horizonH} stroke={COLORS.reference} strokeDasharray="4 3" />
          )}
          <Line dataKey="mae_mw" name="MAE" stroke={COLORS.mae} dot={false} isAnimationActive={false} />
          <Line
            dataKey="p90_abs_error_mw"
            name="P90 |error|"
            stroke={COLORS.p90}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="buffer_p90_mw"
            name="P90 buffer"
            stroke={COLORS.forecast}
            strokeDasharray="5 3"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
