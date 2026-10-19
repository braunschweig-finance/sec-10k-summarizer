import type { Report } from "./types";

// Caterpillar FY2025, as read from the 10-K and 2026 DEF 14A by the live Streamlit app on 2026-10-17/18
// and recomputed by hand (see Finance Research CLAUDE.md, Log). Proxy quotes and statement tables are not
// stored here, so the sample shows them only once the API is connected.
const CAT_EDGAR = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000018230&type=10-K";
const CAT_PROXIES = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000018230&type=DEF+14A";

export const SAMPLE_CAT: Report = {
  ticker: "CAT",
  name: "Caterpillar Inc.",
  tenk_url: CAT_EDGAR,
  statements: { income: null, balance: null, cashflow: null },
  ratios: {
    "Gross Margin": "33.8%",
    "Operating Margin": "16.5%",
    "Current Ratio": "1.44x",
    "Total Liabilities-to-Equity": "3.62x",
  },
  inputs: {
    Revenue: { value_m: 67589, label: "Total sales and revenues", concept: "", period: "FY2025" },
    "Cost of Revenue": { value_m: 44752, label: "Cost of goods sold", concept: "", period: "FY2025" },
    "Gross Profit": { value_m: 22837, label: "Revenue - Cost of Revenue", concept: "Derived: Revenue - Cost of Revenue", period: "FY2025" },
    "Operating Income": { value_m: 11151, label: "Operating profit", concept: "", period: "FY2025" },
    "Current Assets": { value_m: 52485, label: "", concept: "", period: "FY2025" },
    "Current Liabilities": { value_m: 36558, label: "", concept: "", period: "FY2025" },
    "Total Liabilities": { value_m: 77267, label: "", concept: "", period: "FY2025" },
    "Shareholders' Equity": { value_m: 21318, label: "", concept: "", period: "FY2025" },
  },
  governance: {
    checks: {
      "Lead Independent Director": "",
      "Clawback Policy": "",
      "Anti-Hedging Policy": "",
      "Say-on-Pay Vote": "",
    },
    sections: {},
    proxy_url: CAT_PROXIES,
    proxy_date: "2026-04-30",
    proxy_chars: 282058,
    proxy_source: "the HTML documents in the filing",
  },
  // Proxy accession 0001308179-26-000358: two CEOs in FY2025 (Umpleby to Apr 30, Creed from May 1),
  // compensation actually paid $82,309,936 + $49,423,389 = $131,733,325; summary comp table $39,199,573.
  payEfficiency: {
    available: true,
    value: "1.18%",
    fy_end: "2025-12-31",
    ceo_pay_m: 131.733325,
    ceo_count: 2,
    ceos: ["Mr. Umpleby", "Mr. Creed"],
    sct_total_m: 39.199573,
    pay_concept: "ecd:PeoActuallyPaidCompAmt",
    proxy_url: "https://www.sec.gov/Archives/edgar/data/18230/000130817926000358/",
    proxy_date: "2026-04-30",
    proxy_accn: "0001308179-26-000358",
    op_income_m: 11151,
    op_concept: "us-gaap:OperatingIncomeLoss",
    denominator: "operating",
    tenk_accn: "",
    tenk_url: CAT_EDGAR,
    flags: ["2 people served as CEO this year; their pay is added together."],
  },
  sample: {
    note: "Sample data: Caterpillar FY2025 10-K and 2026 proxy, as read by the live app on Oct 17–18, 2026.",
    revenueHistory: [
      { period: "FY2023", value_m: 67060 },
      { period: "FY2024", value_m: 64809 },
      { period: "FY2025", value_m: 67589 },
    ],
  },
};
