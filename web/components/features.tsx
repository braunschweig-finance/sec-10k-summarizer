"use client";

import { useState } from "react";
import { motion } from "motion/react";
import type { PayEfficiency, Report, TrendYear } from "@/lib/types";
import { API_URL, downloadExport, fetchPayEfficiency, fetchReport } from "@/lib/api";
import { BarChart, DotStrip, LineChart, SERIES } from "./charts";
import { QUICK } from "@/lib/tickers";

const fmtM = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;
const fmtPct = (d: number) => (v: number) => `${v.toFixed(d)}%`;
const fyLabel = (fyEnd: string) => `FY${fyEnd.slice(0, 4)}`;

function Card({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-line bg-panel p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-bold">{title}</h3>
        {note && <span className="eyebrow">{note}</span>}
      </div>
      {children}
    </div>
  );
}

function Loading({ text }: { text: string }) {
  return (
    <div className="flex animate-pulse items-center gap-3 rounded-2xl border border-line bg-panel p-5 text-sm text-muted">
      <span className="h-2 w-2 rounded-full bg-violet" /> {text}
    </div>
  );
}

function ErrorNote({ text }: { text: string }) {
  return <p className="rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose">{text}</p>;
}

// ---------- Trends tab ----------

export function TrendsPanel({ report }: { report: Report }) {
  if (report.sample) {
    const h = report.sample.revenueHistory;
    return (
      <div className="flex flex-col gap-5">
        <Card title="Total sales and revenues" note="$ millions · sample">
          <BarChart labels={h.map((x) => x.period)} values={h.map((x) => x.value_m)} format={fmtM} ariaLabel="Revenue" />
        </Card>
        <p className="text-sm text-muted">Five-year margins and the Pay Efficiency trend load from each year&apos;s 10-K once the API is online.</p>
      </div>
    );
  }
  if (report.trendsError) return <ErrorNote text={`Trends: ${report.trendsError}`} />;
  if (!report.trends) return <Loading text="Reading five years of 10-K figures from SEC EDGAR…" />;

  const years = report.trends.years;
  if (!years.length) return <p className="text-sm text-muted">SEC has no full-year 10-K figures for this company.</p>;
  const labels = years.map((y) => `FY${y.fiscal_year}`);
  const line = (y: TrendYear, k: keyof TrendYear["lines"]) => y.lines[k]?.value_m ?? null;
  const pe = report.payEfficiency?.available ? report.payEfficiency.history ?? [] : [];

  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-3xl text-sm text-muted">
        The last {years.length} fiscal years, each as first reported in that year&apos;s 10-K (later restatements aren&apos;t applied). The table
        under the charts lists every value and the filing it came from.
      </p>
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Revenue" note="$ millions · bars start at zero">
          <BarChart labels={labels} values={years.map((y) => line(y, "Revenue"))} format={fmtM} ariaLabel="Revenue" />
        </Card>
        <Card title="Margins" note="% of revenue">
          <LineChart
            labels={labels}
            ariaLabel="Gross, operating and net margin by year"
            format={fmtPct(1)}
            series={[
              { name: "Gross", color: SERIES.gold, values: years.map((y) => y.margins["Gross Margin"]) },
              { name: "Operating", color: SERIES.teal, values: years.map((y) => y.margins["Operating Margin"]) },
              { name: "Net", color: SERIES.violet, values: years.map((y) => y.margins["Net Margin"]) },
            ]}
          />
          <div className="flex flex-wrap gap-4 text-xs text-muted">
            {[
              ["Gross margin", SERIES.gold],
              ["Operating margin", SERIES.teal],
              ["Net margin", SERIES.violet],
            ].map(([n, c]) => (
              <span key={n} className="flex items-center gap-2">
                <span className="h-0.5 w-4 rounded" style={{ background: c }} />
                {n}
              </span>
            ))}
          </div>
        </Card>
      </div>
      {pe.length > 0 && (
        <Card title="Pay Efficiency" note="CEO pay actually paid ÷ operating income">
          <LineChart
            labels={pe.map((p) => fyLabel(p.fy_end))}
            ariaLabel="Pay Efficiency"
            format={fmtPct(2)}
            height={220}
            series={[{ name: "Pay Efficiency", color: SERIES.violet, values: pe.map((p) => p.pct) }]}
          />
          <p className="text-xs text-muted">
            Every year in the latest proxy&apos;s Pay Versus Performance table. A gap means an operating loss that year, where the ratio isn&apos;t
            meaningful.
          </p>
        </Card>
      )}

      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="bg-panel text-muted">
            <tr>
              {["Fiscal year", "Revenue", "Gross profit", "Operating income", "Net income", "Gross m.", "Op. m.", "Net m.", "10-K"].map((h, i) => (
                <th key={h} className={`px-4 py-3 font-medium ${i === 0 || i === 8 ? "text-left" : "text-right"}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((y) => (
              <tr key={y.fy_end} className="border-t border-line hover:bg-panel/70">
                <td className="px-4 py-2.5 font-mono text-xs">
                  FY{y.fiscal_year} <span className="text-muted">({y.fy_end})</span>
                </td>
                {(["Revenue", "Gross Profit", "Operating Income", "Net Income"] as const).map((k) => (
                  <td key={k} className="tnum px-4 py-2.5 text-right font-mono" title={y.lines[k]?.concept}>
                    {y.lines[k] ? fmtM(y.lines[k]!.value_m) : "N/A"}
                  </td>
                ))}
                {(["Gross Margin", "Operating Margin", "Net Margin"] as const).map((k) => (
                  <td key={k} className="tnum px-4 py-2.5 text-right font-mono text-muted">
                    {y.margins[k] === null ? "N/A" : `${y.margins[k]!.toFixed(1)}%`}
                  </td>
                ))}
                <td className="px-4 py-2.5 font-mono text-xs">
                  {y.lines.Revenue?.url ? (
                    <a href={y.lines.Revenue.url} target="_blank" rel="noreferrer" className="text-teal hover:underline">
                      {y.lines.Revenue.accn} ↗
                    </a>
                  ) : (
                    ""
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        $ millions. Hover a value to see its XBRL concept. Derived values (gross profit = revenue - cost of revenue when no gross profit line is
        filed) say so in the concept.
      </p>
    </div>
  );
}

// ---------- Peer ranking (inside the Pay Efficiency card) ----------

export function PeerRank({ pe }: { pe: Extract<PayEfficiency, { available: true }> }) {
  const p = pe.peers;
  if (!p || pe.pct === null || pe.pct === undefined) return null;
  const lower = Math.round(p.lower_than_pct);
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-line bg-ink/40 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="eyebrow">Peer ranking · fiscal {p.peer_year}</span>
        <span className="text-xs text-muted">
          Median {p.median.toFixed(2)}% · middle half {p.p25.toFixed(2)}% to {p.p75.toFixed(2)}%
        </span>
      </div>
      <p className="text-sm">
        {p.higher_count === 0 ? (
          <>
            <span className="font-display text-2xl font-bold text-violet">Highest</span>{" "}
            <span className="text-muted">
              of {p.count} S&amp;P 500 companies (none of them paid their CEO a bigger share of operating income).
            </span>
          </>
        ) : (
          <>
            <span className="font-display text-2xl font-bold text-violet">Lower than {lower}%</span>{" "}
            <span className="text-muted">
              of {p.count} S&amp;P 500 companies ({p.higher_count} of them paid their CEO a bigger share of operating income).
            </span>
          </>
        )}
      </p>
      <DotStrip values={p.values} mark={pe.pct} markLabel={`${fyLabel(pe.fy_end)} Pay Efficiency`} median={p.median} />
      <p className="text-xs text-muted">
        Violet dot: this company. Gray dots: the research sample ({p.source}).
        {p.notes.map((n) => ` ${n}`)}
      </p>
    </div>
  );
}

// ---------- Compare tab ----------

type Side = { report: Report; pe: PayEfficiency | null; peError?: string };

const ROWS: { label: string; get: (s: Side) => { text: string; num: number | null; source?: string } }[] = [
  {
    label: "Revenue ($M)",
    get: ({ report }) => {
      const h = report.inputs.Revenue;
      return { text: h ? fmtM(h.value_m) : "N/A", num: h?.value_m ?? null, source: h ? `${h.concept} · ${h.period}` : undefined };
    },
  },
  {
    label: "Operating income ($M)",
    get: ({ report }) => {
      const h = report.inputs["Operating Income"];
      return { text: h ? fmtM(h.value_m) : "N/A", num: h?.value_m ?? null, source: h ? `${h.concept} · ${h.period}` : undefined };
    },
  },
  ...["Gross Margin", "Operating Margin", "Current Ratio", "Total Liabilities-to-Equity"].map((name) => ({
    label: name,
    get: ({ report }: Side) => {
      const v = report.ratios[name] ?? "N/A";
      const n = parseFloat(v);
      return { text: v, num: /^-?[\d.]+(%|x)$/.test(v) ? n : null };
    },
  })),
  {
    label: "Pay Efficiency",
    get: ({ pe, peError }) => {
      if (peError) return { text: "Couldn't load", num: null };
      if (!pe) return { text: "Loading…", num: null };
      if (!pe.available) return { text: "Not available", num: null, source: pe.reason };
      return { text: `${pe.value} (${fyLabel(pe.fy_end)})`, num: pe.pct ?? null, source: `${pe.pay_concept} ÷ ${pe.op_concept}` };
    },
  },
];

export function ComparePanel({ report }: { report: Report }) {
  const [input, setInput] = useState("");
  const [other, setOther] = useState<Side | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const quick = QUICK.filter((t) => t !== report.ticker).slice(0, 4);

  async function compare(sym: string) {
    const t = sym.toUpperCase().trim();
    if (!t) return;
    setInput(t);
    setLoading(true);
    setError(null);
    setOther(null);
    try {
      const r = await fetchReport(t);
      setOther({ report: r, pe: r.payEfficiency });
      if (!r.payEfficiency) {
        fetchPayEfficiency(t)
          .then((pe) => setOther((prev) => (prev && prev.report.ticker === t ? { ...prev, pe } : prev)))
          .catch((e) => setOther((prev) => (prev && prev.report.ticker === t ? { ...prev, peError: (e as Error).message } : prev)));
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const sides: Side[] = [{ report, pe: report.payEfficiency, peError: report.payEfficiencyError }, ...(other ? [other] : [])];

  return (
    <div className="flex flex-col gap-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          compare(input);
        }}
        className="flex flex-wrap items-center gap-2"
      >
        <span className="text-sm text-muted">Compare {report.ticker} with</span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value.toUpperCase())}
          aria-label="Ticker to compare"
          placeholder="e.g. MSFT"
          spellCheck={false}
          autoComplete="off"
          className="w-28 rounded-xl border border-line bg-ink px-3 py-2 font-mono tracking-wider uppercase outline-none focus:border-brass"
        />
        <button type="submit" className="rounded-xl bg-paper px-4 py-2 text-sm font-medium text-ink disabled:opacity-60" disabled={loading}>
          {loading ? "Pulling…" : "Compare"}
        </button>
        {quick.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => compare(q)}
            className="rounded-full border border-line px-3 py-1 font-mono text-xs text-muted transition-colors hover:border-brass hover:text-paper"
          >
            {q}
          </button>
        ))}
      </form>
      {error && <ErrorNote text={error} />}
      {loading && <Loading text={`Pulling ${input}'s latest 10-K from SEC EDGAR…`} />}
      {!other && !loading && !error && (
        <p className="text-sm text-muted">Pick a second company to line up its latest 10-K ratios and Pay Efficiency next to {report.ticker}&apos;s.</p>
      )}

      {other && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-3">
          <div className="overflow-x-auto rounded-2xl border border-line">
            <table className="w-full min-w-[600px] text-sm">
              <thead className="bg-panel">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-muted">Metric</th>
                  {sides.map((s, i) => (
                    <th key={s.report.ticker} className="px-4 py-3 text-right font-medium">
                      <span className={i === 0 ? "text-brass" : "text-teal"}>{s.report.ticker}</span>{" "}
                      <span className="text-xs font-normal text-muted">{s.report.name}</span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr className="border-t border-line">
                  <td className="px-4 py-2.5 text-muted">Latest fiscal year</td>
                  {sides.map((s) => (
                    <td key={s.report.ticker} className="px-4 py-2.5 text-right font-mono text-xs text-muted">
                      {s.report.inputs.Revenue?.period ?? "N/A"}
                    </td>
                  ))}
                </tr>
                {ROWS.map((row) => {
                  const cells = sides.map((s) => row.get(s));
                  const max = Math.max(...cells.map((c) => Math.abs(c.num ?? 0)));
                  return (
                    <tr key={row.label} className="border-t border-line hover:bg-panel/70">
                      <td className="px-4 py-3 font-medium">{row.label}</td>
                      {cells.map((c, i) => (
                        <td key={i} className="px-4 py-3 text-right" title={c.source}>
                          <div className="tnum font-mono">{c.text}</div>
                          {c.num !== null && max > 0 && (
                            <div className="mt-1.5 ml-auto h-1 w-32 overflow-hidden rounded-full bg-line">
                              <motion.div
                                className={`ml-auto h-full rounded-full ${i === 0 ? "bg-brass" : "bg-teal"}`}
                                initial={{ width: 0 }}
                                animate={{ width: `${(Math.abs(c.num) / max) * 100}%` }}
                                transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
                              />
                            </div>
                          )}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">
            Each column is that company&apos;s own latest 10-K and proxy, so fiscal years can differ (check the first row). Bars compare the two
            values on each row. Hover a value to see the XBRL concept it came from.
          </p>
        </motion.div>
      )}
    </div>
  );
}

// ---------- Export buttons ----------

export function ExportButtons({ ticker }: { ticker: string }) {
  const [busy, setBusy] = useState<"xlsx" | "pdf" | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!API_URL) return null;

  async function run(kind: "xlsx" | "pdf") {
    setBusy(kind);
    setError(null);
    try {
      await downloadExport(ticker, kind);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {(["xlsx", "pdf"] as const).map((k) => (
        <button
          key={k}
          onClick={() => run(k)}
          disabled={busy !== null}
          className="rounded-full border border-brass/60 bg-brass/10 px-4 py-2 text-sm text-brass hover:bg-brass/20 disabled:opacity-60"
        >
          {busy === k ? "Building…" : k === "xlsx" ? "Download Excel ↓" : "Download PDF ↓"}
        </button>
      ))}
      {error && <p className="basis-full text-right text-xs text-rose">{error}</p>}
    </>
  );
}
