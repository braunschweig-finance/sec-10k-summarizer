"use client";

import { useState } from "react";
import { AnimatePresence, motion, type Variants } from "motion/react";
import type { Report, Statement } from "@/lib/types";
import { API_URL, downloadDocx, fetchMemo, saveBlob } from "@/lib/api";
import { CountUp, onSpotlightMove } from "./fx";

const fmtM = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;

const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
};
const rise: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: [0.2, 0.7, 0.2, 1] as const } },
};

// What each ratio divides, so every card can show its own arithmetic
const RATIO_MATH: Record<string, { num: string; den: string; blurb: string }> = {
  "Gross Margin": { num: "Gross Profit", den: "Revenue", blurb: "Share of each sales dollar left after the cost of making the product." },
  "Operating Margin": { num: "Operating Income", den: "Revenue", blurb: "Share of sales left after running the business, before interest and tax." },
  "Current Ratio": { num: "Current Assets", den: "Current Liabilities", blurb: "Short-term assets for every dollar due within a year." },
  "Total Liabilities-to-Equity": {
    num: "Total Liabilities",
    den: "Shareholders' Equity",
    blurb: "All liabilities (not only debt) per dollar of shareholders' equity.",
  },
};

export function RatiosPanel({ report }: { report: Report }) {
  return (
    <div className="flex flex-col gap-8">
      <motion.div variants={stagger} initial="hidden" animate="show" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(report.ratios).map(([name, value]) => {
          const math = RATIO_MATH[name];
          const num = math && report.inputs[math.num];
          const den = math && report.inputs[math.den];
          const pct = value.endsWith("%") ? Math.max(0, Math.min(100, parseFloat(value))) : null;
          return (
            <motion.div
              key={name}
              variants={rise}
              whileHover={{ y: -4 }}
              onMouseMove={onSpotlightMove}
              className="spotlight flex flex-col gap-3 rounded-2xl border border-line bg-panel p-5"
            >
              <div className="eyebrow">{name}</div>
              <CountUp value={value} className="font-display text-4xl font-bold text-brass" />
              {pct !== null && (
                <div className="h-1.5 overflow-hidden rounded-full bg-line">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-brass to-teal"
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 1.2, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              )}
              {num && den && (
                <div className="tnum font-mono text-xs text-muted">
                  {fmtM(num.value_m)} ÷ {fmtM(den.value_m)} ($M)
                </div>
              )}
              <p className="text-sm leading-relaxed text-muted">{math?.blurb}</p>
            </motion.div>
          );
        })}
      </motion.div>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-xl font-bold">Where every number comes from</h3>
          <span className="eyebrow">Latest fiscal year · $ millions</span>
        </div>
        <div className="overflow-x-auto rounded-2xl border border-line">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-panel text-muted">
              <tr>
                {["Input", "Value ($M)", "Filed line item", "XBRL concept", "Period"].map((h) => (
                  <th key={h} className="px-4 py-3 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <motion.tbody variants={stagger} initial="hidden" animate="show">
              {Object.entries(report.inputs).map(([name, hit]) => (
                <motion.tr key={name} variants={rise} className="border-t border-line hover:bg-panel/70">
                  <td className="px-4 py-3 font-medium">{name}</td>
                  <td className="tnum px-4 py-3 font-mono text-brass">{hit ? fmtM(hit.value_m).slice(1) : "Not reported"}</td>
                  <td className="px-4 py-3 text-muted">{hit?.label || (report.sample ? "Shown when live" : "")}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted">{hit?.concept || (report.sample ? "Shown when live" : "")}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted">{hit?.period}</td>
                </motion.tr>
              ))}
            </motion.tbody>
          </table>
        </div>
        <p className="text-sm text-muted">
          N/A means the filing doesn&apos;t report that line on the face of its statements (banks have no gross profit or current assets, for
          example). Derived inputs say so in the concept column.
        </p>
      </div>
    </div>
  );
}

function StatementTable({ st }: { st: Statement }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-line">
      <table className="w-full min-w-[560px] text-sm">
        <thead className="bg-panel text-muted">
          <tr>
            <th className="px-4 py-3 text-left font-medium">Line item</th>
            {st.periods.map((p) => (
              <th key={p} className="px-4 py-3 text-right font-mono text-xs font-medium">
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <motion.tbody variants={stagger} initial="hidden" animate="show">
          {st.rows.map((r, i) => (
            <motion.tr key={i} variants={rise} className="border-t border-line hover:bg-panel/70">
              <td className="px-4 py-2.5">{r.label}</td>
              {r.values.map((v, j) => (
                <td key={j} className="tnum px-4 py-2.5 text-right font-mono">
                  {v}
                </td>
              ))}
            </motion.tr>
          ))}
        </motion.tbody>
      </table>
    </div>
  );
}

function RevenueBars({ history }: { history: { period: string; value_m: number }[] }) {
  const max = Math.max(...history.map((h) => h.value_m));
  return (
    <div className="rounded-2xl border border-line bg-panel p-5">
      <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-bold">Total sales and revenues</h3>
        <span className="eyebrow">$ millions · bars start at zero</span>
      </div>
      <div className="flex h-56 items-end gap-4 sm:gap-8">
        {history.map((h, i) => (
          <div key={h.period} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
            <CountUp value={fmtM(h.value_m)} className="font-mono text-sm text-paper" />
            <motion.div
              className={`w-full max-w-28 rounded-t-lg ${i === history.length - 1 ? "bg-gradient-to-t from-brass/60 to-brass" : "bg-line"}`}
              initial={{ height: 0 }}
              animate={{ height: `${(h.value_m / max) * 80}%` }}
              transition={{ duration: 1, delay: 0.15 * i, ease: [0.16, 1, 0.3, 1] }}
            />
            <span className="font-mono text-xs text-muted">{h.period}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function StatementsPanel({ report }: { report: Report }) {
  const views = [
    ["income", "Income Statement"],
    ["balance", "Balance Sheet"],
    ["cashflow", "Cash Flow"],
  ] as const;
  const [view, setView] = useState<(typeof views)[number][0]>("income");
  const st = report.statements[view];

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-2">
        {views.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setView(key)}
            className={`relative rounded-full px-4 py-1.5 text-sm transition-colors ${view === key ? "text-ink" : "text-muted hover:text-paper"}`}
          >
            {view === key && (
              <motion.span layoutId="stmt-pill" className="absolute inset-0 rounded-full bg-paper" transition={{ type: "spring", bounce: 0.25, duration: 0.5 }} />
            )}
            <span className="relative">{label}</span>
          </button>
        ))}
      </div>
      <p className="text-sm text-muted">Dollar figures in $ millions; per-share amounts in $; share counts in millions. No AI is used for these numbers.</p>
      {st ? (
        <StatementTable st={st} />
      ) : report.sample ? (
        <div className="flex flex-col gap-3">
          {view === "income" && <RevenueBars history={report.sample.revenueHistory} />}
          <p className="text-sm text-muted">The full {views.find((v) => v[0] === view)?.[1].toLowerCase()} loads straight from the 10-K once the API is online.</p>
        </div>
      ) : (
        <p className="text-sm text-muted">This filing has no XBRL table for this statement.</p>
      )}
    </div>
  );
}

export function GovernancePanel({ report }: { report: Report }) {
  const g = report.governance;
  const [open, setOpen] = useState<string | null>(null);
  const sections = Object.entries(g.sections);

  if (!g.proxy_url) return <p className="text-muted">No DEF 14A proxy statement was found for this ticker.</p>;

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-muted">
        Latest DEF 14A filed <span className="font-mono text-paper">{g.proxy_date}</span>, with{" "}
        <span className="tnum font-mono text-paper">{g.proxy_chars.toLocaleString("en-US")}</span> characters read from {g.proxy_source}. Each tile
        says whether the proxy discusses the topic; the quote underneath is the proof.
      </p>
      <motion.div variants={stagger} initial="hidden" animate="show" className="grid gap-4 sm:grid-cols-2">
        {Object.entries(g.checks).map(([check, evidence]) => {
          const found = evidence !== null;
          return (
            <motion.div
              key={check}
              variants={rise}
              onMouseMove={onSpotlightMove}
              className="spotlight flex flex-col gap-3 rounded-2xl border border-line bg-panel p-5"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium">{check}</span>
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 14, delay: 0.4 }}
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 font-mono text-xs ${found ? "bg-teal/15 text-teal" : "bg-rose/15 text-rose"}`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${found ? "bg-teal" : "bg-rose"}`} />
                  {found ? "Discussed" : "Not found"}
                </motion.span>
              </div>
              <p className="text-sm leading-relaxed text-muted">
                {evidence
                  ? `“${evidence}”`
                  : found
                    ? "The quoted sentence from the proxy appears here once the API is online."
                    : "No matching text found in the proxy."}
              </p>
            </motion.div>
          );
        })}
      </motion.div>

      {sections.length > 0 && (
        <div className="flex flex-col divide-y divide-line rounded-2xl border border-line">
          {sections.map(([heading, body]) => (
            <div key={heading}>
              <button
                onClick={() => setOpen(open === heading ? null : heading)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-panel/70"
                aria-expanded={open === heading}
              >
                <span className="font-medium">{heading}</span>
                <motion.span animate={{ rotate: open === heading ? 45 : 0 }} className="text-xl text-brass">
                  +
                </motion.span>
              </button>
              <AnimatePresence initial={false}>
                {open === heading && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <p className="max-w-3xl px-5 pb-5 text-sm leading-relaxed text-muted">{body}</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      )}
      {report.sample && <p className="text-sm text-muted">The four proxy passages (board leadership, pay, voting items, clawback and risk) also load once the API is online.</p>}
    </div>
  );
}

export function MemoPanel({ report }: { report: Report }) {
  const [state, setState] = useState<{ loading: boolean; error?: string; text?: string; usage?: { input: number; output: number } | null }>({
    loading: false,
  });

  async function generate() {
    setState({ loading: true });
    try {
      const memo = await fetchMemo(report.ticker);
      setState({ loading: false, text: memo.text, usage: memo.usage });
    } catch (e) {
      setState({ loading: false, error: (e as Error).message });
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-2xl text-sm text-muted">
        Gemini writes an investment committee memo from the ratios and proxy passages above, and only from those. Download it as a Word or text
        file.
      </p>
      <div>
        <motion.button
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          onClick={generate}
          disabled={state.loading}
          className="rounded-full bg-brass px-6 py-3 font-medium text-ink disabled:opacity-60"
        >
          {state.loading ? "Writing the memo…" : "Generate research memo"}
        </motion.button>
      </div>
      {state.loading && (
        <div className="flex flex-col gap-2">
          {[92, 80, 86, 60].map((w, i) => (
            <motion.div
              key={i}
              className="h-3 rounded bg-line"
              style={{ width: `${w}%` }}
              animate={{ opacity: [0.35, 0.8, 0.35] }}
              transition={{ duration: 1.4, repeat: Infinity, delay: i * 0.15 }}
            />
          ))}
        </div>
      )}
      {state.error && <p className="rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose">{state.error}</p>}
      {state.text && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-4">
          <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-2xl border border-line bg-panel p-5 font-sans text-sm leading-relaxed">
            {state.text}
          </pre>
          {state.usage && (
            <p className="font-mono text-xs text-muted">
              Tokens used: {state.usage.input} in, {state.usage.output} out
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <button
              className="rounded-full border border-line px-4 py-2 text-sm hover:border-brass"
              onClick={() => saveBlob(new Blob([state.text!], { type: "text/plain" }), `${report.ticker}_Institutional_Memo.txt`)}
            >
              Download .txt
            </button>
            {API_URL && (
              <button className="rounded-full border border-line px-4 py-2 text-sm hover:border-brass" onClick={() => downloadDocx(report.ticker, state.text!)}>
                Download .docx
              </button>
            )}
          </div>
        </motion.div>
      )}
    </div>
  );
}
