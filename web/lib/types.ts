export type Statement = { periods: string[]; rows: { label: string; values: string[] }[] };

export type SourceInput = { value_m: number; label: string; concept: string; period: string } | null;

export type Governance = {
  checks: Record<string, string | null>;
  sections: Record<string, string>;
  proxy_url: string;
  proxy_date: string;
  proxy_chars: number;
  proxy_source: string;
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
    };

export type Report = {
  ticker: string;
  name: string;
  tenk_url: string;
  statements: { income: Statement | null; balance: Statement | null; cashflow: Statement | null };
  ratios: Record<string, string>;
  inputs: Record<string, SourceInput>;
  // Loaded separately from the 10-K (null until it arrives), since reading the proxy is the slow part
  governance: Governance | null;
  governanceError?: string;
  payEfficiency: PayEfficiency | null;
  payEfficiencyError?: string;
  // Set only on the built-in sample, which has numbers but no filing text
  sample?: { note: string; revenueHistory: { period: string; value_m: number }[] };
};
