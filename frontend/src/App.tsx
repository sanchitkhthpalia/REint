import { useMemo } from "react";

import { useByHorizon, useByHour, useMeta, useMetrics, useSeries } from "./api/hooks";
import type { MetaResponse, SeriesResponse } from "./api/types";
import { Controls } from "./components/Controls";
import { ErrorHistogram } from "./components/ErrorHistogram";
import { ForecastChart } from "./components/ForecastChart";
import { Header } from "./components/Header";
import { HourOfDayChart } from "./components/HourOfDayChart";
import { HowToRead, Methodology } from "./components/InfoPanels";
import { KpiCards } from "./components/KpiCards";
import { LeadTimeChart } from "./components/LeadTimeChart";
import { Panel, QueryState } from "./components/Panel";
import { Summary } from "./components/Summary";
import { WorstMissesTable } from "./components/WorstMissesTable";
import { P90, bufferLevel } from "./lib/buffer";
import { defaultsFromMeta, toAnalysisQuery, toRangeQuery } from "./lib/filters";
import { formatDay } from "./lib/format";
import { useDebounced } from "./lib/useDebounced";
import { useUrlFilters } from "./lib/useUrlFilters";

export default function App() {
  const meta = useMeta();
  return (
    <div className="mx-auto max-w-[1600px] px-4 py-4 lg:px-6">
      {meta.isPending && (
        <p role="status" className="py-24 text-center text-sm text-slate-400">
          Loading dataset…
        </p>
      )}
      {meta.isError && (
        <div role="alert" className="mx-auto mt-24 max-w-md text-center text-sm text-rose-200">
          <p className="mb-3">Could not load the dataset: {meta.error.message}</p>
          <button
            type="button"
            onClick={() => void meta.refetch()}
            className="rounded border border-rose-700 px-3 py-1 hover:bg-rose-900/50"
          >
            Retry
          </button>
        </div>
      )}
      {meta.data && <Dashboard meta={meta.data} />}
    </div>
  );
}

// Wait for the filters to settle so dragging the horizon slider sends one request, not 48.
const FETCH_DEBOUNCE_MS = 250;

const noPairs = (d: { coverage: { paired: number } }) => d.coverage.paired === 0;

function dayAheadLeadRange(series: SeriesResponse | undefined): [number, number] | null {
  const leads = series?.points.flatMap((p) => (p.lead_time_hours === null ? [] : [p.lead_time_hours]));
  return leads && leads.length > 0 ? [Math.min(...leads), Math.max(...leads)] : null;
}

function Dashboard({ meta }: { meta: MetaResponse }) {
  const { defaults, bounds } = useMemo(() => defaultsFromMeta(meta), [meta]);
  const { filters, update, reset } = useUrlFilters(defaults, bounds);

  const settled = useDebounced(filters, FETCH_DEBOUNCE_MS);
  const analysis = useMemo(() => toAnalysisQuery(settled), [settled]);
  const range = useMemo(() => toRangeQuery(settled), [settled]);

  const series = useSeries(analysis);
  const metrics = useMetrics(analysis);
  const byHour = useByHour(analysis);
  const byHorizon = useByHorizon(range);

  const errors = useMemo(
    () => series.data?.points.flatMap((p) => (p.error_mw === null ? [] : [p.error_mw])) ?? [],
    [series.data],
  );
  const bufferP90 = metrics.data ? (bufferLevel(metrics.data.buffer, P90)?.buffer_mw ?? null) : null;
  const period = `${formatDay(settled.start)} – ${formatDay(settled.end)}`;
  const emptyMessage = "No slots with both a forecast and an actual for this selection.";

  return (
    <div className="flex flex-col gap-4">
      <Header meta={meta} />
      <Controls filters={filters} bounds={bounds} onChange={update} onReset={reset} />

      <QueryState query={metrics} height={170} isEmpty={noPairs} emptyMessage={emptyMessage}>
        {(data) => (
          <div className="flex flex-col gap-3">
            <Summary metrics={data} />
            <KpiCards metrics={data} />
          </div>
        )}
      </QueryState>

      <Panel
        title="Actual vs forecast available at decision time"
        subtitle={metrics.data?.query.cutoff_rule ?? period}
      >
        <QueryState query={series} height={320} isEmpty={noPairs} emptyMessage={emptyMessage}>
          {(data) => <ForecastChart points={data.points} />}
        </QueryState>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="The earlier you decide, the bigger the miss" subtitle="Error by hours ahead">
          <QueryState query={byHorizon} height={256}>
            {(data) => (
              <LeadTimeChart
                points={data.points}
                mode={settled.mode}
                horizonH={settled.horizonH}
                dayAheadLeads={settled.mode === "day_ahead" ? dayAheadLeadRange(series.data) : null}
              />
            )}
          </QueryState>
        </Panel>
        <Panel title="When in the day it misses most" subtitle="UK time · bars: typical miss · line: bias">
          <QueryState
            query={byHour}
            height={256}
            isEmpty={(d) => d.hours.every((h) => h.stats.n === 0)}
            emptyMessage={emptyMessage}
          >
            {(data) => <HourOfDayChart hours={data.hours} />}
          </QueryState>
        </Panel>
        <Panel title="How big the misses were" subtitle="Hours by forecast − actual · red: too high">
          <QueryState query={series} height={256} isEmpty={noPairs} emptyMessage={emptyMessage}>
            {() => <ErrorHistogram errors={errors} bufferP90={bufferP90} />}
          </QueryState>
        </Panel>
      </div>

      <Panel title="Worst 10 forecast misses" subtitle={period}>
        <QueryState query={metrics} height={200} isEmpty={noPairs} emptyMessage={emptyMessage}>
          {(data) => <WorstMissesTable rows={data.worst_slots} />}
        </QueryState>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <HowToRead />
        <Methodology cutoffRule={metrics.data?.query.cutoff_rule} />
      </div>

      <footer className="pb-4 text-center text-xs text-slate-500">
        Data: Elexon BMRS (FUELHH, WINDFOR). Times in UK local time.
      </footer>
    </div>
  );
}
