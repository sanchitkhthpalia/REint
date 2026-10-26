import { ukHour } from "./format";

const SHORT_RANGE_MS = 3 * 24 * 3600 * 1000;

/** X-axis ticks on UK local midnights, or every 6 h when the range is three days or less. */
export function timeTicks(times: readonly number[]): { ticks: number[]; showHour: boolean } {
  const span = times.length > 1 ? times[times.length - 1]! - times[0]! : 0;
  const showHour = span <= SHORT_RANGE_MS;
  const ticks = times.filter((t) => (showHour ? ukHour(t) % 6 === 0 : ukHour(t) === 0));
  return { ticks, showHour };
}
