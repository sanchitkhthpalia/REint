// Chart palette on slate-900. Actual/forecast are a blue/amber pair (distinguishable with
// common colour-vision deficiencies); error shading uses rose for over-forecast (shortfall
// risk) and teal for under-forecast. All line colours exceed 4.5:1 against the panel.
export const COLORS = {
  actual: "#38bdf8", // sky-400
  forecast: "#fbbf24", // amber-400
  over: "#f43f5e", // rose-500: forecast > actual -> wind shortfall
  under: "#2dd4bf", // teal-400: forecast < actual -> surplus
  mae: "#a78bfa", // violet-400
  p90: "#f472b6", // pink-400
  grid: "#1e293b", // slate-800
  axis: "#94a3b8", // slate-400
  reference: "#e2e8f0", // slate-200
} as const;
