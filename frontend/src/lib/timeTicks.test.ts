import { describe, expect, it } from "vitest";

import { timeTicks } from "./timeTicks";

const hourly = (startIso: string, hours: number) =>
  Array.from({ length: hours }, (_, i) => Date.parse(startIso) + i * 3600_000);

describe("timeTicks", () => {
  it("ticks once per UK day on long ranges", () => {
    const { ticks, showHour } = timeTicks(hourly("2026-01-10T00:00:00Z", 7 * 24));

    expect(showHour).toBe(false);
    expect(ticks).toHaveLength(7);
    expect(new Date(ticks[1]!).toISOString()).toBe("2026-01-11T00:00:00.000Z");
  });

  it("ticks every 6 h on short ranges", () => {
    const { ticks, showHour } = timeTicks(hourly("2026-01-10T00:00:00Z", 24));

    expect(showHour).toBe(true);
    expect(ticks.map((t) => new Date(t).getUTCHours())).toEqual([0, 6, 12, 18]);
  });

  it("uses UK midnight, not UTC midnight, in summer time", () => {
    const { ticks } = timeTicks(hourly("2026-06-14T00:00:00Z", 5 * 24));

    // 00:00 BST = 23:00 UTC the previous day
    expect(ticks.map((t) => new Date(t).toISOString())).toContain("2026-06-14T23:00:00.000Z");
    expect(ticks.map((t) => new Date(t).toISOString())).not.toContain("2026-06-15T00:00:00.000Z");
  });
});
