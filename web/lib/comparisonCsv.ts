import type {ScreenerRow} from "./screener";

const HEADERS = [
  "Ticker", "Company", "Sector", "Fiscal year end", "Pay Efficiency (% of operating income)",
  "Company Grade", "Grade score (0-100)", "Upside vs peers (%)", "Valuation confidence",
  "Cached price date", "Snapshot built", "10-K filing URL", "Proxy filing URL", "Valuation source",
  "Data notes", "Interpretation",
];

const INTERPRETATION = "Percentage fields use percentage points: 1.18 means 1.18%, not 118%. "
  + "Missing values are blank, not zero. Fiscal periods and cached price dates can differ. "
  + "Negative compensation actually paid is not superior efficiency. Company Grade is descriptive; "
  + "low-confidence valuation is not a reliable investment signal. Snapshot rebuilds do not update quotes.";

function cell(value: string | number | null | undefined): string {
  let text: string;
  if (typeof value === "number") text = Number.isFinite(value) ? String(value) : "";
  else {
    text = value ?? "";
    // Protect text cells, including citations and notes, without changing numeric signs.
    if (/^[\t\r\n]/.test(text) || /^[\s\u0000-\u001f\u007f-\u009f]*[=+\-@]/u.test(text)) text = "'" + text;
  }
  return '"' + text.replaceAll('"', '""') + '"';
}

/** Excel-friendly UTF-8 CSV over the exact selected snapshot rows; no lookups or financial math. */
export function comparisonCsv(rows: readonly ScreenerRow[], builtAt: string | null): string {
  const ids = rows.map(row => row.ticker.trim().toUpperCase());
  if (ids.length < 2 || ids.length > 4 || ids.some(id => !id) || new Set(ids).size !== ids.length)
    throw new Error("Select two to four distinct companies before exporting.");
  const lines: (string | number | null | undefined)[][] = [HEADERS];
  for (const row of rows) lines.push([
    row.ticker, row.name, row.sector, row.fy_end, row.pay_efficiency_pct,
    row.grade, row.grade_score, row.upside_pct, row.valuation_confidence,
    row.price_date, builtAt, row.sources.financials_url, row.sources.proxy_url,
    row.sources.valuation_source, row.missing.join("\n"), INTERPRETATION,
  ]);
  return "\uFEFF" + lines.map(line => line.map(cell).join(",")).join("\r\n") + "\r\n";
}
