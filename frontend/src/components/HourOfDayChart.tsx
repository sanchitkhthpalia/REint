import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { HourOfDayStats } from "../api/types";
import { COLORS } from "../lib/colors";
import { formatMw, formatSignedMw } from "../lib/format";

export function HourOfDayChart({ hours }: { hours: readonly HourOfDayStats[] }) {
  const rows = hours.map((h) => ({
    hour: `${String(h.hour_local).padStart(2, "0")}:00`,
    mae: h.stats.mae_mw,
    bias: h.stats.bias_mw,
  }));
  return (
    <div className="h-64 w-full" role="img" aria-label="Forecast error by hour of day">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis dataKey="hour" stroke={COLORS.axis} tick={{ fontSize: 11 }} interval={2} />
          <YAxis
            stroke={COLORS.axis}
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}k`}
            width={40}
          />
          <Tooltip
            contentStyle={{ background: "#020617", border: "1px solid #334155", fontSize: 12 }}
            labelFormatter={(h) => `${String(h)} UK time`}
            formatter={(v, name) => {
              const value = typeof v === "number" ? v : null;
              return name === "MAE" ? formatMw(value) : formatSignedMw(value);
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} verticalAlign="top" />
          <ReferenceLine y={0} stroke={COLORS.axis} />
          <Bar dataKey="mae" name="MAE" fill={COLORS.mae} fillOpacity={0.8} isAnimationActive={false} />
          <Line
            dataKey="bias"
            name="Bias"
            stroke={COLORS.forecast}
            dot={false}
            strokeWidth={2}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
