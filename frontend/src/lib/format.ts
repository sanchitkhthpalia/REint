// All timestamps arrive in UTC; everything shown to users is Europe/London (CLAUDE.md).
const UK = "Europe/London";

const dateTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK,
  weekday: "short",
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const dayMonth = new Intl.DateTimeFormat("en-GB", { timeZone: UK, day: "numeric", month: "short" });
const longDate = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK,
  day: "numeric",
  month: "short",
  year: "numeric",
});
const dayHour = new Intl.DateTimeFormat("en-GB", {
  timeZone: UK,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const hourOnly = new Intl.DateTimeFormat("en-GB", { timeZone: UK, hour: "numeric", hourCycle: "h23" });
const mw = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });

export const formatUkDateTime = (iso: string | number) => dateTime.format(new Date(iso));
export const formatUkDay = (iso: string | number) => dayMonth.format(new Date(iso));
export const formatUkDayHour = (iso: string | number) => dayHour.format(new Date(iso));
export const ukHour = (iso: string | number) => Number(hourOnly.format(new Date(iso)));
export const formatLongDate = (iso: string) => longDate.format(new Date(iso));

/** A YYYY-MM-DD calendar day, formatted without shifting it through a timezone. */
export const formatDay = (day: string) => longDate.format(new Date(`${day}T12:00:00Z`));

export function formatMw(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${mw.format(value)} MW`;
}

export function formatSignedMw(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${mw.format(Math.abs(value))} MW`;
}

export function formatPct(fraction: number | null | undefined, digits = 1): string {
  return fraction === null || fraction === undefined ? "–" : `${(fraction * 100).toFixed(digits)}%`;
}

export function formatHours(hours: number | null | undefined): string {
  return hours === null || hours === undefined ? "–" : `${hours.toFixed(1)} h`;
}

/** "~4,160": rounded to the nearest 10 MW, for plain-English recommendations. */
export function approxMw(value: number): string {
  return `~${mw.format(Math.round(value / 10) * 10)}`;
}

export function slotWord(slotMinutes: number | null | undefined): string {
  if (slotMinutes === 30) return "half-hours";
  if (slotMinutes === 60) return "hours";
  return "slots";
}
