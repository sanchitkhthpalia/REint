import type { Mode } from "../api/types";
import { type Bounds, type Filters, GATE_TIME_OPTIONS } from "../lib/filters";

interface ControlsProps {
  filters: Filters;
  bounds: Bounds;
  onChange: (patch: Partial<Filters>) => void;
  onReset: () => void;
}

const MODES: { value: Mode; label: string; hint: string }[] = [
  {
    value: "day_ahead",
    label: "Day-ahead decision",
    hint: "Forecast available at the gate time on the day before delivery",
  },
  {
    value: "horizon",
    label: "Custom horizon",
    hint: "Forecast published at least H hours before each slot",
  },
];

const label = "text-[11px] font-medium uppercase tracking-wider text-slate-400";
const input =
  "rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-100 focus:border-sky-500 focus:outline-none focus:ring-1 focus:ring-sky-500";

export function Controls({ filters, bounds, onChange, onReset }: ControlsProps) {
  const gateOptions = GATE_TIME_OPTIONS.some((o) => o.value === filters.gateTime)
    ? GATE_TIME_OPTIONS
    : [...GATE_TIME_OPTIONS, { value: filters.gateTime, label: filters.gateTime }];

  // Browsers allow typing dates outside min/max; only accept in-range, ordered values.
  const setStart = (value: string) => {
    if (value && value >= bounds.min && value <= filters.end) onChange({ start: value });
  };
  const setEnd = (value: string) => {
    if (value && value <= bounds.max && value >= filters.start) onChange({ end: value });
  };

  return (
    <div
      role="group"
      aria-label="Filters"
      className="flex flex-wrap items-end gap-x-6 gap-y-3 rounded-lg border border-slate-800 bg-slate-900/80 px-4 py-3"
    >
      <fieldset className="flex flex-col gap-1">
        <legend className={label}>Delivery days (UK)</legend>
        <div className="flex items-center gap-2">
          <input
            type="date"
            aria-label="Start date"
            className={input}
            min={bounds.min}
            max={filters.end}
            value={filters.start}
            onChange={(e) => setStart(e.target.value)}
          />
          <span className="text-slate-500" aria-hidden>
            →
          </span>
          <input
            type="date"
            aria-label="End date"
            className={input}
            min={filters.start}
            max={bounds.max}
            value={filters.end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
      </fieldset>

      <div className="flex flex-col gap-1">
        <span className={label} id="mode-label">
          Decision rule
        </span>
        <div
          role="radiogroup"
          aria-labelledby="mode-label"
          className="inline-flex rounded border border-slate-700 bg-slate-950 p-0.5"
        >
          {MODES.map((m) => {
            const selected = filters.mode === m.value;
            return (
              <button
                key={m.value}
                type="button"
                role="radio"
                aria-checked={selected}
                title={m.hint}
                onClick={() => onChange({ mode: m.value })}
                className={`rounded px-3 py-1 text-sm transition-colors ${
                  selected ? "bg-sky-600 text-white" : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                {m.label}
              </button>
            );
          })}
        </div>
      </div>

      {filters.mode === "day_ahead" ? (
        <label className="flex flex-col gap-1">
          <span className={label}>Gate time (UK, D-1)</span>
          <select
            aria-label="Gate time"
            className={input}
            value={filters.gateTime}
            onChange={(e) => onChange({ gateTime: e.target.value })}
          >
            {gateOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label className="flex min-w-56 flex-col gap-1">
          <span className={label}>
            Horizon: <span className="num text-slate-100">{filters.horizonH} h</span> before slot
          </span>
          <input
            type="range"
            aria-label="Forecast horizon in hours"
            className="accent-sky-500"
            min={bounds.horizonMin}
            max={bounds.horizonMax}
            step={1}
            value={filters.horizonH}
            onChange={(e) => onChange({ horizonH: Number(e.target.value) })}
          />
        </label>
      )}

      <button
        type="button"
        onClick={onReset}
        className="ml-auto rounded border border-slate-700 px-3 py-1 text-sm text-slate-300 hover:bg-slate-800"
      >
        Reset
      </button>
    </div>
  );
}
