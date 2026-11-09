const SAFE_TICKER = /^[A-Z0-9][A-Z0-9.-]{0,14}$/;

function normalizeTickers(values: readonly string[]): string[] {
  const tickers: string[] = [];
  for (const value of values) {
    const ticker = value.trim().toUpperCase();
    if (SAFE_TICKER.test(ticker) && !tickers.includes(ticker)) {
      tickers.push(ticker);
      if (tickers.length === 4) break;
    }
  }
  return tickers;
}

/** Parse query state; first values win and literal fragments are excluded. */
export function parseComparisonUrl(search: string): { tickers: string[]; open: boolean } {
  const params = new URLSearchParams(search.split("#", 1)[0]);
  const raw = params.get("compare") ?? "";
  const tickers = raw.length <= 128 ? normalizeTickers(raw.split(",")) : [];
  return { tickers, open: params.get("comparison") === "1" && tickers.length >= 2 };
}

/** Return a copy, replacing only comparison-owned query parameters. */
export function writeComparisonParams(
  params: URLSearchParams,
  tickers: readonly string[],
  open: boolean,
): URLSearchParams {
  const result = new URLSearchParams(params);
  result.delete("compare");
  result.delete("comparison");
  const normalized = normalizeTickers(tickers);
  if (normalized.length) result.set("compare", normalized.join(","));
  if (open && normalized.length >= 2) result.set("comparison", "1");
  return result;
}
