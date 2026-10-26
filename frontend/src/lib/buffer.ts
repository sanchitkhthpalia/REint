import type { ProcurementBuffer } from "../api/types";

export const P90 = 0.9;
export const P95 = 0.95;

type Level = ProcurementBuffer["levels"][number];

/** The buffer level for a coverage target (compared with a tolerance, not float equality). */
export function bufferLevel(buffer: ProcurementBuffer, coverage: number): Level | undefined {
  return buffer.levels.find((l) => Math.abs(l.coverage - coverage) < 1e-9);
}
