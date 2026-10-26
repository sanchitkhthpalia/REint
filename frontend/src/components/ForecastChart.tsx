import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { SeriesPoint } from "../api/types";
import { COLORS } from "../lib/colors";
import {
  formatHours,
  formatMw,
  formatSignedMw,
  formatUkDateTime,
  formatUkDay,
  formatUkDayHour,
} from "../lib/format";
import { timeTicks } from "../lib/timeTicks";

interface Row {
  t: number;
  point: SeriesPoint;
  actual: number | null;
  forecast: number | null;
  over: [number, number] | null; // forecast above actual: shortfall band
  under: [number, number] | null; // forecast below actual: surplus band
}

function toChartRows(points: readonly SeriesPoint[]): Row[] {
  return points.map((p) => {
    const { actual_mw: a, forecast_mw: f } = p;
    const both = a !== null && f !== null;
    return {
      t: Date.parse(p.target_time_utc),
      point: p,
      actual: a,
      forecast: f,
      over: both && f > a ? [a, f] : null,
      under: both && f < a ? [f, a] : null,
    };
  });
}

function ForecastTooltip({ active, row }: { active?: boolean; row?: Row }) {
  if (!active || !row) return null;
  const p = row.point;
  const error = p.error_mw;
  return (
    <div className="rounded border border-slate-700 bg-slate-950/95 px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-slate-100">{formatUkDateTime(p.target_time_utc)} (UK)</p>
      <dl className="num grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5">
        <dt className="text-slate-400">Actual</dt>
        <dd style={{ color: COLORS.actual }}>{formatMw(p.actual_mw)}</dd>
        <dt className="text-slate-400">Forecast</dt>
        <dd style={{ color: COLORS.forecast }}>{formatMw(p.forecast_mw)}</dd>
        <dt className="text-slate-400">Error</dt>
        <dd
          style={{
            color: error === null ? undefined : error > 0 ? COLORS.over : COLORS.under,
          }}
        >
          {formatSignedMw(error)}
        </dd>
        <dt className="text-slate-400">Published</dt>
        <dd className="text-slate-200">
          {p.publish_time_utc ? formatUkDateTime(p.publish_time_utc) : "no forecast before cutoff"}
        </dd>
        <dt className="text-slate-400">Lead time</dt>
        <dd className="text-slate-200">{formatHours(p.lead_time_hours)}</dd>
      </dl>
    </div>
  );
}

export function ForecastChart({ points }: { points: readonly SeriesPoint[] }) {
  const rows = useMemo(() => toChartRows(points), [points]);
  const { ticks, showHour } = useMemo(() => timeTicks(rows.map((r) => r.t)), [rows]);
  return (
    <div className="h-80 w-full" role="img" aria-label="Actual and forecast wind generation over time">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
          <CartesianGrid stroke={COLORS.grid} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            ticks={ticks}
            tickFormatter={showHour ? formatUkDayHour : formatUkDay}
            stroke={COLORS.axis}
            tick={{ fontSize: 11 }}
            minTickGap={24}
          />
          <YAxis
            stroke={COLORS.axis}
            tick={{ fontSize: 11 }}
            tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
            width={40}
            label={{ value: "MW", angle: -90, position: "insideLeft", fill: COLORS.axis, fontSize: 11 }}
          />
          <Tooltip
            content={({ active, payload }) => (
              <ForecastTooltip active={active} row={payload?.[0]?.payload as Row | undefined} />
            )}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area
            dataKey="over"
            name="Over-forecast (shortfall)"
            stroke="none"
            fill={COLORS.over}
            fillOpacity={0.3}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Area
            dataKey="under"
            name="Under-forecast (surplus)"
            stroke="none"
            fill={COLORS.under}
            fillOpacity={0.3}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            dataKey="actual"
            name="Actual (FUELHH)"
            stroke={COLORS.actual}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            dataKey="forecast"
            name="Forecast at decision time (WINDFOR)"
            stroke={COLORS.forecast}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
