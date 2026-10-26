// Friendly aliases over the types generated from the backend OpenAPI schema (schema.ts).
// Regenerate schema.ts with: python scripts/export_openapi.py && npm run gen:api
import type { components, paths } from "./schema";

type Schemas = components["schemas"];

export type Mode = Schemas["Mode"];
export type MetaResponse = Schemas["MetaResponse"];
export type SeriesResponse = Schemas["SeriesResponse"];
export type SeriesPoint = Schemas["SeriesPoint"];
export type MetricsResponse = Schemas["MetricsResponse"];
export type ByHourResponse = Schemas["ByHourResponse"];
export type ByHorizonResponse = Schemas["ByHorizonResponse"];
export type LeadTimePoint = Schemas["LeadTimePoint"];
export type HourOfDayStats = Schemas["HourOfDayStats"];
export type WorstSlot = Schemas["WorstSlot"];
export type ProcurementBuffer = Schemas["ProcurementBuffer"];
export type ValidationErrorItem = Schemas["ValidationError"];

export type AnalysisQuery = NonNullable<paths["/api/series"]["get"]["parameters"]["query"]>;
export type RangeQuery = NonNullable<
  paths["/api/metrics/by-horizon"]["get"]["parameters"]["query"]
>;
