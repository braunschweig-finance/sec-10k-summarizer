"use client";

import { useState } from "react";
import { AnimatePresence, motion, type Variants } from "motion/react";
import type { Benchmark, GovernanceMetrics, PayEfficiency, Report, Statement } from "@/lib/types";
import { API_URL, downloadDocx, fetchMemo, saveBlob } from "@/lib/api";
import { CountUp, onSpotlightMove } from "./fx";
import { PeerRank } from "./features";
import { BenchLine } from "./bench";

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
              <BenchLine bench={report.benchmark} metric={name} value={value} />
            </motion.div>
          );
        })}
      </motion.div>

      {report.benchmark && (
        <p className="-mt-4 text-xs text-muted">
          Medians: {report.benchmark.is_sector ? `${report.benchmark.group} companies in the Russell 1000` : "all Russell 1000 companies"}, each from its
          own latest 10-K. Sector comes from SEC&apos;s industry code for the company
          {report.benchmark.sic ? ` (SIC ${report.benchmark.sic}${report.industry ? `, ${report.industry}` : ""})` : ""}, so it can differ from
          other classifications. {report.benchmark.note}
        </p>
      )}

      <PayEfficiencyCard pe={report.payEfficiency} error={report.payEfficiencyError} bench={report.benchmark} />

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

const fmtPay = (m: number) => `$${m.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}M`;

function SourceLine({ label, value, concept, href, linkText }: { label: string; value: string; concept: string; href: string; linkText: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-line bg-ink/40 p-4">
      <span className="eyebrow">{label}</span>
      <span className="tnum font-mono text-lg text-paper">{value}</span>
      <span className="font-mono text-xs text-muted">{concept}</span>
      {href && (
        <a href={href} target="_blank" rel="noreferrer" className="text-xs text-teal underline-offset-4 hover:underline">
          {linkText} ↗
        </a>
      )}
    </div>
  );
}

// The project's own metric: how much of a year's operating income went to the CEO, by the SEC's "actually paid" measure
function PayEfficiencyCard({ pe, error, bench }: { pe: PayEfficiency | null; error?: string; bench?: Benchmark | null }) {
  if (error) return <p className="rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose">Pay Efficiency: {error}</p>;
  if (!pe)
    return (
      <div className="flex animate-pulse items-center gap-3 rounded-2xl border border-line bg-panel p-5 text-sm text-muted">
        <span className="h-2 w-2 rounded-full bg-violet" /> Reading CEO pay from the proxy&apos;s Pay Versus Performance table…
      </div>
    );
  if (!pe.available)
    return (
      <div className="rounded-2xl border border-line bg-panel p-5 text-sm text-muted">
        <span className="eyebrow mr-2">Pay Efficiency</span>
        {pe.reason}
      </div>
    );
  const fy = `FY${pe.fy_end.slice(0, 4)}`;
  const pct = pe.value.endsWith("%") ? parseFloat(pe.value) : null;
  return (
    <motion.div
      variants={rise}
      initial="hidden"
      animate="show"
      onMouseMove={onSpotlightMove}
      className="spotlight relative flex flex-col gap-5 overflow-hidden rounded-2xl border border-violet/40 bg-panel p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="eyebrow">Pay Efficiency · {fy}</span>
            <span className="rounded-full border border-violet/50 bg-violet/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-violet">
              Original metric
            </span>
          </div>
          <CountUp value={pe.value} className="font-display text-5xl font-bold text-violet" />
          {pct !== null && (
            <div className="h-1.5 w-56 overflow-hidden rounded-full bg-line">
              {/* scaled so 5% fills the bar; most large companies sit well under it */}
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-violet to-brass"
                initial={{ width: 0 }}
                animate={{ width: `${Math.min(100, (pct / 5) * 100)}%` }}
                transition={{ duration: 1.2, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
              />
            </div>
          )}
        </div>
        <p className="max-w-md text-sm leading-relaxed text-muted">
          CEO compensation actually paid, as a share of {pe.denominator === "pretax" ? "pretax income" : "operating income"}. Lower means the
          company keeps more of its operating profit for every dollar the CEO is paid.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <SourceLine
          label={`CEO compensation actually paid${pe.ceo_count > 1 ? ` (${pe.ceo_count} CEOs: ${pe.ceos.join(" + ")})` : ""}`}
          value={fmtPay(pe.ceo_pay_m)}
          concept={pe.pay_concept}
          href={pe.proxy_url}
          linkText={`DEF 14A filed ${pe.proxy_date}, Pay Versus Performance table`}
        />
        <SourceLine
          label={pe.denominator === "pretax" ? "Pretax income (no operating income tag)" : "Operating income"}
          value={pe.op_income_m === null ? "Not reported" : `${fmtM(pe.op_income_m)}M`}
          concept={pe.op_concept}
          href={pe.tenk_url}
          linkText={pe.tenk_accn ? `10-K, accession ${pe.tenk_accn}` : `${fy} 10-K`}
        />
      </div>

      <div className="tnum font-mono text-xs text-muted">
        {fmtPay(pe.ceo_pay_m)} ÷ {pe.op_income_m === null ? "?" : `${fmtM(pe.op_income_m)}M`} = {pe.value}
        {pe.sct_total_m !== null && <> · Summary Compensation Table total: {fmtPay(pe.sct_total_m)}</>}
      </div>
      <BenchLine bench={bench} metric="Pay Efficiency" value={pe.value} lowerIsBetter />
      <PeerRank pe={pe} />
      {pe.flags.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-brass">
          {pe.flags.map((f) => (
            <li key={f}>⚑ {f}</li>
          ))}
        </ul>
      )}
    </motion.div>
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

  if (!g) {
    return report.governanceError ? (
      <p className="rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose">{report.governanceError}</p>
    ) : (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted">Reading the latest DEF 14A proxy statement. It&apos;s a long document, so this part can take a minute.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <motion.div
              key={i}
              className="h-28 rounded-2xl border border-line bg-panel"
              animate={{ opacity: [0.4, 0.9, 0.4] }}
              transition={{ duration: 1.6, repeat: Infinity, delay: i * 0.15 }}
            />
          ))}
        </div>
      </div>
    );
  }
  const sections = Object.entries(g.sections);

  if (!g.proxy_url) return <p className="text-muted">No DEF 14A proxy statement was found for this ticker.</p>;

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-muted">
        Latest DEF 14A filed <span className="font-mono text-paper">{g.proxy_date}</span>, with{" "}
        <span className="tnum font-mono text-paper">{g.proxy_chars.toLocaleString("en-US")}</span> characters read from {g.proxy_source}. Each tile
        says whether the proxy discusses the topic; the quote underneath is the proof.
      </p>
      {g.metrics && <GovernanceNumbers m={g.metrics} bench={report.benchmark} proxyUrl={g.proxy_url} />}
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

/** CEO pay ratio, board independence and say-on-pay support, each with the proxy sentence it came from. */
function GovernanceNumbers({ m, bench, proxyUrl }: { m: GovernanceMetrics; bench?: Benchmark | null; proxyUrl: string }) {
  const ratio = m["CEO Pay Ratio"];
  const board = m["Board Independence"];
  const sop = m["Say-on-Pay Support"];
  const cards = [
    {
      name: "CEO Pay Ratio",
      value: ratio ? `${ratio.value.toLocaleString("en-US")} : 1` : "Not found",
      sub: "CEO's total pay to the median employee's",
      evidence: ratio?.evidence,
    },
    {
      name: "Board Independence",
      value: board ? (board.total ? `${board.independent} of ${board.total}` : `${board.pct.toFixed(0)}%`) : "Not found",
      sub: board?.total ? `${board.pct.toFixed(0)}% of directors are independent` : "Share of directors who are independent",
      evidence: board?.evidence,
      compare: board ? `${board.pct}%` : "N/A",
    },
    {
      name: "Say-on-Pay Support",
      value: sop ? `${sop.approximate ? "≈" : ""}${sop.pct}%` : "Not found",
      sub: sop?.meeting_year ? `Votes for executive pay at the ${sop.meeting_year} annual meeting` : "Votes for executive pay at the last annual meeting",
      evidence: sop?.evidence,
    },
  ];
  return (
    <div className="flex flex-col gap-3">
      <motion.div variants={stagger} initial="hidden" animate="show" className="grid gap-4 md:grid-cols-3">
        {cards.map((c) => (
          <motion.div key={c.name} variants={rise} onMouseMove={onSpotlightMove} className="spotlight flex flex-col gap-2 rounded-2xl border border-line bg-panel p-5">
            <span className="eyebrow">{c.name}</span>
            <span className={`tnum font-display text-4xl font-bold ${c.evidence ? "text-brass" : "text-muted"}`}>{c.value}</span>
            <span className="text-sm text-muted">{c.sub}</span>
            <BenchLine bench={bench} metric={c.name} value={"compare" in c ? c.compare! : c.evidence ? c.value : "N/A"} />
            {c.evidence ? (
              <details className="text-xs leading-relaxed text-muted">
                <summary className="cursor-pointer text-teal">Quote from the proxy</summary>
                <p className="mt-2">&ldquo;{c.evidence}&rdquo;</p>
              </details>
            ) : (
              <p className="text-xs text-muted">No sentence stating this number was found in the proxy text; check the filing directly.</p>
            )}
          </motion.div>
        ))}
      </motion.div>
      <p className="text-xs text-muted">
        Read from sentences in the{" "}
        <a href={proxyUrl} target="_blank" rel="noreferrer" className="text-teal hover:underline">
          proxy statement ↗
        </a>
        . These aren&apos;t tagged in XBRL, so each number is only taken from a sentence that states it plainly, and that sentence is quoted.
      </p>
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
