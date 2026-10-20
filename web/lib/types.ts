export type Statement = { periods: string[]; rows: { label: string; values: string[] }[] };

export type SourceInput = { value_m: number; label: string; concept: string; period: string } | null;

// Numbers read from a sentence in the proxy; the sentence is kept as evidence
export type GovernanceMetrics = {
  "CEO Pay Ratio": { value: number; text: string; evidence: string } | null;
  "Board Independence": { independent: number | null; total: number | null; pct: number; evidence: string } | null;
  "Say-on-Pay Support": { pct: number; approximate: boolean; meeting_year: number | null; evidence: string } | null;
};

export type Governance = {
  checks: Record<string, string | null>;
  sections: Record<string, string>;
  metrics?: GovernanceMetrics;
  proxy_url: string;
  proxy_date: string;
  proxy_chars: number;
  proxy_source: string;
};

// One fiscal year of Pay Efficiency, from the same proxy's Pay Versus Performance table
export type PayEfficiencyYear = {
  fy_end: string;
  value: string;
  pct: number | null;
  ceo_pay_m: number;
  op_income_m: number | null;
  op_concept: string;
  denominator: "operating" | "pretax" | "";
  tenk_accn: string;
  // Pay Versus Performance table: value of $100 invested at the start of the table's first year
  tsr?: number | null;
  peer_tsr?: number | null;
};

// Where the company sits in the fixed research sample of S&P 500 companies (lower Pay Efficiency is better)
export type PeerRank = {
  fiscal_year: number;
  peer_year: number;
  count: number;
  higher_count: number;
  lower_than_pct: number;
  median: number;
  p25: number;
  p75: number;
  values: number[];
  notes: string[];
  source: string;
};

// CEO compensation actually paid (proxy Pay Versus Performance table) / operating income (10-K)
export type PayEfficiency =
  | { available: false; reason: string }
  | {
      available: true;
      value: string;
      fy_end: string;
      ceo_pay_m: number;
      ceo_count: number;
      ceos: string[];
      sct_total_m: number | null;
      pay_concept: string;
      proxy_url: string;
      proxy_date: string;
      proxy_accn: string;
      op_income_m: number | null;
      op_concept: string;
      denominator: "operating" | "pretax" | "";
      tenk_accn: string;
      tenk_url: string;
      flags: string[];
      pct?: number | null;
      history?: PayEfficiencyYear[];
      peers?: PeerRank | null;
    };

export type TrendLine = { value_m: number; concept: string; accn: string; url: string } | null;

export type TrendYear = {
  fy_end: string;
  fiscal_year: number;
  lines: Record<"Revenue" | "Cost of Revenue" | "Gross Profit" | "Operating Income" | "Net Income", TrendLine>;
  margins: Record<"Gross Margin" | "Operating Margin" | "Net Margin", number | null>;
};

export type YearEndPrices =
  | { available: true; source: string; years: { fy_end: string; date: string | null; close: number | null }[] }
  | { available: false; reason: string; source: string };

export type Trends = { ticker: string; years: TrendYear[]; prices?: YearEndPrices };

// Median of the company's sector (or the whole Russell 1000) for each benchmarked number
export type BenchStat = { median: number; p25: number; p75: number; n: number } | null;
export type Benchmark = {
  group: string;
  is_sector: boolean;
  companies: number;
  metrics: Record<string, BenchStat>;
  source: string;
  built_at?: string;
  sic?: string;
  note?: string;
};

export type RiskItem = { title: string; category: string | null; status?: "new" | "reworded" | "unchanged"; prior_title?: string };

// Item 1A risk factor headings of the latest 10-K, compared with the prior 10-K
export type RiskSummary =
  | { available: false; reason: string; tenk_url: string; tenk_date: string; period: string }
  | {
      available: true;
      tenk_url: string;
      tenk_date: string;
      period: string;
      count: number;
      words: number;
      categories: string[];
      risks: RiskItem[];
      prior: { tenk_url: string; tenk_date: string; period: string; count: number; words: number } | null;
      removed: string[];
      changes: { new: number; reworded: number; unchanged: number } | null;
    };

export type Report = {
  ticker: string;
  name: string;
  tenk_url: string;
  statements: { income: Statement | null; balance: Statement | null; cashflow: Statement | null };
  ratios: Record<string, string>;
  inputs: Record<string, SourceInput>;
  sic?: string;
  industry?: string;
  benchmark?: Benchmark | null;
  // Loaded separately from the 10-K (null until it arrives), since reading the proxy is the slow part
  governance: Governance | null;
  governanceError?: string;
  payEfficiency: PayEfficiency | null;
  payEfficiencyError?: string;
  // Loaded after Pay Efficiency, which reads the same SEC companyfacts file
  trends?: Trends | null;
  trendsError?: string;
  risks?: RiskSummary | null;
  risksError?: string;
  // Set only on the built-in sample, which has numbers but no filing text
  sample?: { note: string; revenueHistory: { period: string; value_m: number }[] };
};
