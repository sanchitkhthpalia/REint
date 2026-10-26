import { describe, expect, it } from "vitest";

import { histogram, niceBinWidth } from "./histogram";

describe("histogram", () => {
  it("is empty for no values", () => {
    expect(histogram([])).toEqual([]);
  });

  it("picks a nice bin width", () => {
    expect(niceBinWidth(-1000, 7000, 24)).toBe(500); // 333 -> 500
    expect(niceBinWidth(0, 1000, 24)).toBe(50);
  });

  it("aligns bins to zero so over- and under-forecasts never share a bin", () => {
    const bins = histogram([-150, -50, 0, 49, 50, 120], 6); // range 270 / 6 = 45 -> width 50

    expect(bins.map((b) => [b.from, b.count])).toEqual([
      [-150, 1],
      [-100, 0],
      [-50, 1],
      [0, 2],
      [50, 1],
      [100, 1],
    ]);
    expect(bins.reduce((n, b) => n + b.count, 0)).toBe(6);
  });

  it("handles all-equal values", () => {
    expect(histogram([100, 100, 100]).map((b) => b.count)).toEqual([3]);
  });
});
