// Isolated client for the cached screener snapshot (GET /api/screener, see docs/SCREENER_CONTRACT.md).
// Kept in its own file on purpose: the screener work must not touch lib/api.ts or the API.
// The endpoint only reads the prebuilt snapshot on the server — no live SEC, price or AI calls.

import { API_URL, callApi, errorText } from "./api";

export type ScreenerRow = {
  ticker: string;
  name: string;
  sector: string | null;
  fy_end: string | null;
  pay_efficiency_pct: number | null;
  grade: "A" | "B" | "C" | "D" | "F" | null;
  grade_score: number | null;
  upside_pct: number | null;
  price_date: string | null;
  valuation_confidence: "normal" | "low" | null;
  sources: {
    financials_url: string | null;
    proxy_url: string | null;
    valuation_source: string | null;
  };
  missing: string[];
};

export type ScreenerData = {
  available: boolean;
  built_at: string | null;
  total: number;
  matched: number;
  limit: number;
  offset: number;
  sectors: string[];
  coverage: { pay_efficiency_pct: number; grade: number; upside_pct: number };
  rows: ScreenerRow[];
  warnings: string[];
};

export type ScreenerQuery = {
  search?: string;
  sector?: string;
  grade?: "A" | "B" | "C" | "D" | "F";
  max_pay_efficiency_pct?: number;
  min_upside_pct?: number;
  sort?: "ticker" | "name" | "sector" | "pay_efficiency_pct" | "grade_score" | "upside_pct";
  order?: "asc" | "desc";
  limit?: number;
  offset?: number;
};

export const SCREENER_GRADES = ["A", "B", "C", "D", "F"] as const;
export const SCREENER_SORTS = ["ticker", "name", "sector", "pay_efficiency_pct", "grade_score", "upside_pct"] as const;
export const PAGE_SIZES = [25, 50, 100, 200] as const;

export function screenerParams(q: ScreenerQuery): URLSearchParams {
  const p = new URLSearchParams();
  if (q.search) p.set("search", q.search);
  if (q.sector) p.set("sector", q.sector);
  if (q.grade) p.set("grade", q.grade);
  if (q.max_pay_efficiency_pct !== undefined && Number.isFinite(q.max_pay_efficiency_pct))
    p.set("max_pay_efficiency_pct", String(q.max_pay_efficiency_pct));
  if (q.min_upside_pct !== undefined && Number.isFinite(q.min_upside_pct))
    p.set("min_upside_pct", String(q.min_upside_pct));
  if (q.sort) p.set("sort", q.sort);
  if (q.order) p.set("order", q.order);
  if (q.limit !== undefined) p.set("limit", String(Math.min(200, Math.max(1, Math.trunc(q.limit)))));
  if (q.offset !== undefined) p.set("offset", String(Math.max(0, Math.trunc(q.offset))));
  return p;
}

export async function fetchScreener(q: ScreenerQuery): Promise<ScreenerData> {
  if (!API_URL)
    throw new Error("The screener reads the cached research snapshot, so it turns on once the data API is online.");
  const query = screenerParams(q).toString();
  const res = await callApi(`/api/screener${query ? `?${query}` : ""}`);
  if (!res.ok) throw new Error(await errorText(res, "the screener"));
  return res.json();
}
