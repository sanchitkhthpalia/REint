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

// Recharts takes data keys as plain strings; `satisfies` makes a renamed API field a type error.
const KEYS = {
  x: "horizon_h",
  mae: "mae_mw",
  p90: "p90_abs_error_mw",
  buffer: "buffer_p90_mw",
} as const satisfies Record<string, keyof LeadTimePoint>;

const TICK_STEP_H = 6;

export function LeadTimeChart({ points, mode, horizonH, dayAheadLeads }: LeadTimeChartProps) {
  const maxH = points.length > 0 ? Math.max(...points.map((p) => p.horizon_h)) : 0;
  const ticks = Array.from({ length: Math.floor(maxH / TICK_STEP_H) + 1 }, (_, i) => i * TICK_STEP_H);
  return (
    <div className="h-64 w-full" role="img" aria-label="Forecast error against hours ahead">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points as LeadTimePoint[]} margin={{ top: 4, right: 8, bottom: 12, left: 8 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis
            dataKey={KEYS.x}
            type="number"
            domain={[0, maxH]}
            ticks={ticks}
            stroke={COLORS.axis}
            tick={{ fontSize: 11 }}
            label={{
              value: "Hours ahead the forecast was published",
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
            labelFormatter={(h) => `Published ≥ ${String(h)} h ahead`}
            formatter={(v) => formatMw(typeof v === "number" ? v : null)}
          />
          <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} verticalAlign="top" />
          {mode === "day_ahead" && dayAheadLeads && (
            <ReferenceArea
              x1={dayAheadLeads[0]}
              x2={Math.min(maxH, dayAheadLeads[1])}
              fill={COLORS.reference}
              fillOpacity={0.06}
              label={{ value: "your day-ahead range", fill: COLORS.axis, fontSize: 10, position: "insideTop" }}
            />
          )}
          {mode === "horizon" && (
            <ReferenceLine x={horizonH} stroke={COLORS.reference} strokeDasharray="4 3" />
          )}
          <Line
            dataKey={KEYS.mae}
            name="Typical miss (MAE)"
            stroke={COLORS.mae}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey={KEYS.p90}
            name="90% of misses smaller than"
            stroke={COLORS.p90}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey={KEYS.buffer}
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
