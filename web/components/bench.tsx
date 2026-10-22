"use client";

import type { Benchmark } from "@/lib/types";

// How each benchmarked number is written, matching the company's own value on the card
const FORMAT: Record<string, (v: number) => string> = {
  "Gross Margin": (v) => `${v.toFixed(1)}%`,
  "Operating Margin": (v) => `${v.toFixed(1)}%`,
  "Current Ratio": (v) => `${v.toFixed(2)}x`,
  "Total Liabilities-to-Equity": (v) => `${v.toFixed(2)}x`,
  "Pay Efficiency": (v) => `${v.toFixed(2)}%`,
  "CEO Pay Ratio": (v) => `${Math.round(v).toLocaleString("en-US")} : 1`,
  "Board Independence": (v) => `${v.toFixed(0)}%`,
  "Say-on-Pay Support": (v) => `${v.toFixed(1)}%`,
};

/** "Industrials median 15.2% (middle half 9.8% to 21.0%, 71 companies)" under a metric, with a marker showing where the company sits. */
export function BenchLine({ bench, metric, value, lowerIsBetter }: { bench?: Benchmark | null; metric: string; value: string; lowerIsBetter?: boolean }) {
  const stat = bench?.metrics[metric];
  if (!bench || !stat) return null;
  const fmt = FORMAT[metric] ?? ((v: number) => v.toFixed(2));
  // Read the company's own number back from the card text ("33.8%", "1.44x", "389 : 1", "11 of 12" isn't comparable here)
  const own = /^[≈]?-?[\d,.]+\s?(%|x|: 1)?$/.test(value.trim()) ? parseFloat(value.replace(/[≈,]/g, "")) : null;
  const above = own !== null ? own > stat.median : null;
  return (
    <div className="flex flex-col gap-1.5 border-t border-rule pt-3 text-xs text-muted">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span>
          {bench.group} median <span className="tnum font-figures text-ink">{fmt(stat.median)}</span>
        </span>
        {above !== null && own !== stat.median && (
          <span className={lowerIsBetter ? (above ? "text-red" : "text-green") : ""}>{above ? "Above" : "Below"} median</span>
        )}
      </div>
      <span>
        Middle half {fmt(stat.p25)} to {fmt(stat.p75)} · {stat.n} companies
      </span>
    </div>
  );
}
