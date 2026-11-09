/**
 * Return unique, nonempty reasons for an exact, trimmed field prefix before
 * the first colon, preserving input order. Ignore messages without a prefix.
 * Grade includes grade_score and grade.*; upside_pct includes
 * valuation_confidence and price_date. Other metric prefixes are excluded.
 */
export function fieldReasons(reasons: readonly string[], field: string): string[] {
  const result = new Set<string>();
  for (const message of reasons) {
    const colon = message.indexOf(":");
    if (colon < 0) continue;
    const prefix = message.slice(0, colon).trim();
    if (!prefix) continue;
    const matches = prefix === field
      || (field === "grade" && (prefix === "grade_score" || prefix.startsWith("grade.")))
      || (field === "upside_pct" && (prefix === "valuation_confidence" || prefix === "price_date"));
    if (!matches) continue;
    const reason = message.slice(colon + 1).trim();
    if (reason) result.add(reason);
  }
  return [...result];
}

/**
 * Return elapsed UTC calendar days from a strict YYYY-MM-DD (UTC midnight)
 * or ISO timestamp with explicit Z or +/-HH:mm offset to `now` (epoch ms).
 * Timestamps use HH:mm, optional :ss and fractional seconds. Invalid calendar
 * or time components, missing values, nonfinite now, and future instants
 * return null. Crossing a UTC midnight counts as a day; today returns zero.
 */
export function dataAgeDays(value: string | null, now: number): number | null {
  if (!value || !Number.isFinite(now)) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?(Z|[+-]\d{2}:\d{2}))?$/.exec(value);
  if (!match) return null;

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4] ?? 0);
  const minute = Number(match[5] ?? 0);
  const second = Number(match[6] ?? 0);
  const milliseconds = Number(`0.${match[7] ?? "0"}`) * 1000;
  if (month < 1 || month > 12 || day < 1 || day > 31
    || hour > 23 || minute > 59 || second > 59) return null;

  // setUTCFullYear handles years 0000–0099 without Date.UTC's 1900 offset.
  const date = new Date(0);
  date.setUTCFullYear(year, month - 1, day);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1
    || date.getUTCDate() !== day) return null;
  date.setUTCHours(hour, minute, second, 0);

  let offsetMinutes = 0;
  const zone = match[8];
  if (zone && zone !== "Z") {
    const offsetHours = Number(zone.slice(1, 3));
    const offsetRemainder = Number(zone.slice(4, 6));
    if (offsetHours > 23 || offsetRemainder > 59) return null;
    offsetMinutes = (offsetHours * 60 + offsetRemainder) * (zone[0] === "+" ? 1 : -1);
  }
  const timestamp = date.getTime() + milliseconds - offsetMinutes * 60_000;
  if (!Number.isFinite(timestamp) || timestamp > now) return null;
  return Math.floor(now / 86_400_000) - Math.floor(timestamp / 86_400_000);
}
