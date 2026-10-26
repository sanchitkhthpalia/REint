import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { COLORS } from "../lib/colors";
import { formatSignedMw } from "../lib/format";
import { histogram } from "../lib/histogram";

interface ErrorHistogramProps {
  errors: readonly number[];
  bufferP90: number | null;
}

const kmw = (v: number) => `${(v / 1000).toFixed(1)}k`;

export function ErrorHistogram({ errors, bufferP90 }: ErrorHistogramProps) {
  const bins = useMemo(() => histogram(errors), [errors]);
  const rows = bins.map((b) => ({ ...b, label: kmw(b.mid) }));
  const bufferBin =
    bufferP90 === null ? undefined : rows.find((b) => bufferP90 >= b.from && bufferP90 < b.to);

  return (
    <div className="h-64 w-full" role="img" aria-label="Distribution of signed forecast error">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 16, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis dataKey="label" stroke={COLORS.axis} tick={{ fontSize: 11 }} minTickGap={12} />
          <YAxis stroke={COLORS.axis} tick={{ fontSize: 11 }} width={32} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: "#1e293b" }}
            contentStyle={{ background: "#020617", border: "1px solid #334155", fontSize: 12 }}
            labelFormatter={(_, payload) => {
              const bin = payload?.[0]?.payload as { from: number; to: number } | undefined;
              return bin ? `${formatSignedMw(bin.from)} to ${formatSignedMw(bin.to)}` : "";
            }}
            formatter={(v) => [String(v), "slots"]}
          />
          {bufferBin && (
            <ReferenceLine
              x={bufferBin.label}
              stroke={COLORS.forecast}
              strokeDasharray="4 3"
              label={{ value: "P90 buffer", fill: COLORS.forecast, fontSize: 10, position: "top" }}
            />
          )}
          <Bar dataKey="count" isAnimationActive={false}>
            {rows.map((b) => (
              <Cell key={b.from} fill={b.mid > 0 ? COLORS.over : COLORS.under} fillOpacity={0.75} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
