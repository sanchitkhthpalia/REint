import { Panel } from "./Panel";

export function HowToRead() {
  return (
    <Panel title="How to read this">
      <ul className="list-disc space-y-1.5 pl-4 text-sm leading-relaxed text-slate-300">
        <li>
          <strong className="text-slate-100">Amber line</strong>: the wind forecast you would
          actually have had when making the decision. <strong className="text-slate-100">Blue
          line</strong>: what the wind farms then generated.
        </li>
        <li>
          <strong className="text-rose-300">Red shading</strong>: the forecast was too high, so
          wind fell short and extra power had to be bought.{" "}
          <strong className="text-teal-300">Teal shading</strong>: the forecast was too low
          (surplus).
        </li>
        <li>
          <strong className="text-slate-100">P90 buffer</strong>: holding this much extra
          capacity above the forecast-implied need would have covered the wind shortfall in 90% of
          slots in the selected period.
        </li>
        <li>
          <strong className="text-slate-100">Error vs horizon</strong>: how accuracy degrades the
          further ahead the forecast was made. Use it to judge how much an earlier decision costs.
        </li>
      </ul>
    </Panel>
  );
}

export function Methodology({ cutoffRule }: { cutoffRule: string | undefined }) {
  return (
    <Panel title="Methodology">
      <div className="space-y-2 text-sm leading-relaxed text-slate-300">
        <p>
          <strong className="text-slate-100">Available at decision time.</strong> For each slot we
          use the most recent forecast whose publish time is at or before the decision cutoff.
          Forecasts published later are never used, so the error reflects what a trader could
          actually have known (no lookahead).
          {cutoffRule && <span className="text-slate-100"> Current rule: {cutoffRule}</span>}
        </p>
        <p>
          <strong className="text-slate-100">Data.</strong> Actuals: Elexon BMRS FUELHH,
          fuelType WIND (half-hourly). Forecasts: Elexon BMRS WINDFOR (hourly, published about 8
          times a day). Errors are measured on the hourly grid where both exist: forecast minus
          actual, so positive means over-forecast. Times are shown in UK time.
        </p>
        <p>
          <strong className="text-slate-100">Gate time.</strong> The 09:00 default is an
          assumption, set just before the GB day-ahead auctions close (EPEX about 09:20, N2EX
          09:50). Set it to your desk&apos;s real deadline.
        </p>
        <p>
          <strong className="text-slate-100">Caveat.</strong> Forecasts sit above actuals most of
          the time. Part of this bias may come from the two datasets covering different sets of
          wind farms, rather than from forecast skill alone, so treat the buffer as an upper-bound
          estimate until that is confirmed.
        </p>
      </div>
    </Panel>
  );
}
