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
  // Set only on the built-in sample, which has numbers but no filing text
  sample?: { note: string; revenueHistory: { period: string; value_m: number }[] };
};
