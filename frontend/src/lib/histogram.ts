export interface Bin {
  from: number; // inclusive, MW
  to: number; // exclusive, MW
  mid: number;
  count: number;
}

const NICE_STEPS = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000];

/** Smallest "nice" bin width giving at most `targetBins` bins over the range. */
export function niceBinWidth(min: number, max: number, targetBins = 24): number {
  const raw = (max - min) / targetBins;
  return NICE_STEPS.find((step) => step >= raw) ?? NICE_STEPS[NICE_STEPS.length - 1]!;
}

/**
 * Histogram of signed errors with bins aligned to multiples of the width, so that 0 MW is
 * always a bin edge and over-/under-forecast bins never mix.
 */
export function histogram(values: readonly number[], targetBins = 24): Bin[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = niceBinWidth(min, max, targetBins);
  const first = Math.floor(min / width) * width;
  const count = Math.max(1, Math.floor((max - first) / width) + 1);
  const bins: Bin[] = Array.from({ length: count }, (_, i) => ({
    from: first + i * width,
    to: first + (i + 1) * width,
    mid: first + (i + 0.5) * width,
    count: 0,
  }));
  for (const v of values) {
    const index = Math.min(count - 1, Math.floor((v - first) / width));
    bins[index]!.count += 1;
  }
  return bins;
}
