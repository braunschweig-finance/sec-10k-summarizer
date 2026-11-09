/** Filter, ordering, and pagination state persisted in a screener query string. */
export type ScreenerUrlState = {
  search: string;
  sector: string;
  grade: string;
  maxPay: string;
  minUpside: string;
  sort: "ticker" | "name" | "sector" | "pay_efficiency_pct" | "grade_score" | "upside_pct";
  order: "asc" | "desc";
  limit: number;
  offset: number;
};

/** Defaults used for absent or invalid values; default values are omitted from URLs. */
export const DEFAULT_SCREENER_STATE: ScreenerUrlState = Object.freeze({
  search: "",
  sector: "",
  grade: "",
  maxPay: "",
  minUpside: "",
  sort: "ticker",
  order: "asc",
  limit: 50,
  offset: 0,
});

function finiteNumber(value: string): number | undefined {
  if (!value || /\s/.test(value)) return undefined;
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function threshold(value: string): string {
  const number = finiteNumber(value);
  return number === undefined ? "" : String(number);
}

/**
 * Parse a query with or without its leading `?`. Unknown keys are ignored and
 * the first occurrence of each key wins. Invalid values fall back to defaults.
 * Thresholds require a complete, finite Number value without whitespace.
 */
export function parseScreenerUrl(search: string): ScreenerUrlState {
  const params = new URLSearchParams(search);
  const get = (key: string): string => params.get(key) ?? "";
  const sort = get("sort");
  const order = get("order");
  const grade = get("grade");
  const limit = finiteNumber(get("limit"));
  const offset = finiteNumber(get("offset"));

  return {
    search: get("search").trim().slice(0, 100),
    sector: get("sector").trim().slice(0, 100),
    grade: ["A", "B", "C", "D", "F"].includes(grade) ? grade : "",
    maxPay: threshold(get("max_pay_efficiency_pct")),
    minUpside: threshold(get("min_upside_pct")),
    sort: sort === "ticker" || sort === "name" || sort === "sector" ||
      sort === "pay_efficiency_pct" || sort === "grade_score" || sort === "upside_pct"
      ? sort : "ticker",
    order: order === "asc" || order === "desc" ? order : "asc",
    limit: limit === 25 || limit === 50 || limit === 100 || limit === 200 ? limit : 50,
    offset: offset !== undefined && Number.isSafeInteger(offset) && offset >= 0 && offset <= 1_000_000
      ? offset : 0,
  };
}

/**
 * Serialize validated, canonical state in contract key order, without `?`.
 * Applies the parser's normalization and omits all default and empty values.
 */
export function serializeScreenerUrl(state: ScreenerUrlState): string {
  const raw = new URLSearchParams({
    search: state.search,
    sector: state.sector,
    grade: state.grade,
    max_pay_efficiency_pct: state.maxPay,
    min_upside_pct: state.minUpside,
    sort: state.sort,
    order: state.order,
    limit: String(state.limit),
    offset: String(state.offset),
  });
  const normalized = parseScreenerUrl(raw.toString());
  const params = new URLSearchParams();
  const fields = [
    ["search", "search"],
    ["sector", "sector"],
    ["grade", "grade"],
    ["max_pay_efficiency_pct", "maxPay"],
    ["min_upside_pct", "minUpside"],
    ["sort", "sort"],
    ["order", "order"],
    ["limit", "limit"],
    ["offset", "offset"],
  ] as const;
  for (const [queryKey, stateKey] of fields) {
    if (normalized[stateKey] !== DEFAULT_SCREENER_STATE[stateKey]) {
      params.set(queryKey, String(normalized[stateKey]));
    }
  }
  return params.toString();
}
