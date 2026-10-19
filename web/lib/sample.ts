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
  sample: {
    note: "Sample data: Caterpillar FY2025 10-K and 2026 proxy, as read by the live app on Oct 17–18, 2026.",
    revenueHistory: [
      { period: "FY2023", value_m: 67060 },
      { period: "FY2024", value_m: 64809 },
      { period: "FY2025", value_m: 67589 },
    ],
  },
};
