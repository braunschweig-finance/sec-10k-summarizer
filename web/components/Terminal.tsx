"use client";

import { useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Report } from "@/lib/types";
import { API_URL, fetchGovernance, fetchPayEfficiency, fetchReport, fetchRisks, fetchTrends } from "@/lib/api";
import { Tick } from "./fx";
import { SAMPLE_CAT } from "@/lib/sample";
import { GovernancePanel, MemoPanel, RatiosPanel, StatementsPanel } from "./panels";
import { ComparePanel, ExportButtons, TrendsPanel } from "./features";
import { SummaryPanel } from "./summary";
import { AskFilingPanel, EarningsTonePanel } from "./ai_tools";
import { FairValuePanel } from "./valuation";
import { GradePanel } from "./grade";
import { AlertsPanel } from "./alerts";
import { QUICK } from "@/lib/tickers";

const TABS = [
  { id: "ratios", label: "Ratios" },
  { id: "grade", label: "Grade" },
  { id: "value", label: "Fair Value" },
  { id: "trends", label: "Trends" },
  { id: "compare", label: "Compare" },
  { id: "summary", label: "10-K Summary" },
  { id: "statements", label: "Statements" },
  { id: "governance", label: "Governance" },
  { id: "alerts", label: "Red Flags & Insiders" },
  { id: "tone", label: "Earnings Tone" },
  { id: "ask", label: "Ask the 10-K" },
  { id: "memo", label: "AI Memo" },
] as const;
type TabId = (typeof TABS)[number]["id"];


export default function Terminal() {
  const [ticker, setTicker] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("ratios");
  const [slow, setSlow] = useState(false);
  const current = useRef("");

  async function load(sym: string) {
    const t = sym.toUpperCase().trim();
    if (!t) return;
    setTicker(t);
    setLoading(true);
    setError(null);
    // A company's first read of its filings from SEC can take up to a minute
    const slowTimer = setTimeout(() => setSlow(true), 5000);
    current.current = t;
    try {
      const r = await fetchReport(t);
      setReport(r);
      setTab("ratios");
      // The proxy statement loads after the ratios are already on screen
      if (!r.governance) {
        fetchGovernance(t)
          .then((g) => current.current === t && setReport((prev) => (prev && prev.ticker === t ? { ...prev, governance: g } : prev)))
          .catch((e) =>
            current.current === t &&
            setReport((prev) => (prev && prev.ticker === t ? { ...prev, governanceError: (e as Error).message } : prev))
          );
      }
      const update = (patch: Partial<Report>) =>
        current.current === t && setReport((prev) => (prev && prev.ticker === t ? { ...prev, ...patch } : prev));
      if (!r.payEfficiency) {
        // Trends start after Pay Efficiency, so the API reads SEC's companyfacts file once for both
        fetchPayEfficiency(t)
          .then((p) => update({ payEfficiency: p }))
          .catch((e) => update({ payEfficiencyError: (e as Error).message }))
          .finally(() =>
            fetchTrends(t)
              .then((tr) => update({ trends: tr }))
              .catch((e) => update({ trendsError: (e as Error).message }))
              // Risk factors last: the API reads one company's filings at a time, so this doesn't slow the others
              .finally(() =>
                fetchRisks(t)
                  .then((rk) => update({ risks: rk }))
                  .catch((e) => update({ risksError: (e as Error).message }))
              )
          );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      clearTimeout(slowTimer);
      setSlow(false);
      setLoading(false);
    }
  }

  const sheet = report ?? SAMPLE_CAT;

  return (
    <main className="min-h-screen">
      {/* MASTHEAD */}
      <header className="double-rule bg-sheet">
        <div className="gutter mx-auto flex max-w-6xl flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-3">
          <span className="text-lg font-extrabold tracking-tight">SEC Filing Terminal</span>
          <span className="flex items-center gap-2 text-sm text-muted">
            <span className={`h-2 w-2 rounded-full ${API_URL ? "bg-pass" : "bg-input"}`} aria-hidden />
            {API_URL ? "Reading live from SEC EDGAR" : "Sample data only (no data server set)"}
          </span>
        </div>
      </header>

      {/* LOOKUP + WORKING PAPER */}
      <section className="gutter mx-auto grid max-w-6xl items-start gap-10 pt-12 pb-12 sm:pt-16 lg:grid-cols-[1fr_minmax(0,25rem)] lg:gap-16">
        <div className="flex flex-col gap-6">
          <h1 className="max-w-2xl text-4xl leading-[1.05] font-extrabold sm:text-6xl">Look up a company. Check every number against its filings.</h1>
          <p className="max-w-xl text-lg leading-relaxed text-muted">
            Ratios, governance checks and red flags from SEC 10-K and proxy filings. Figures in blue are copied as filed, and each one is tied to
            the line item or sentence it came from.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              load(ticker);
            }}
            className="flex max-w-xl flex-col gap-3"
          >
            <label htmlFor="ticker" className="text-sm font-semibold">
              Ticker symbol
            </label>
            <div className="flex gap-2">
              <input
                id="ticker"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="AAPL"
                autoComplete="off"
                spellCheck={false}
                className="min-w-0 flex-1 rounded-sm border-2 border-ink bg-sheet px-4 py-3 figures text-xl font-semibold tracking-wide uppercase outline-none placeholder:font-normal placeholder:text-muted/50 focus:border-input"
              />
              <button type="submit" disabled={loading} className="rounded-sm bg-ink px-6 py-3 font-semibold text-sheet hover:bg-input disabled:opacity-70">
                {loading ? "Reading filings…" : "Look up"}
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
              <span className="text-muted">Examples:</span>
              {QUICK.map((q) => (
                <button key={q} type="button" onClick={() => load(q)} className="figures font-semibold text-input underline decoration-rule underline-offset-4 hover:decoration-input">
                  {q}
                </button>
              ))}
            </div>
          </form>

          <AnimatePresence>
            {loading && slow && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="max-w-xl text-sm text-muted"
                role="status"
              >
                Reading {ticker}&apos;s 10-K and proxy from SEC EDGAR. A company&apos;s first lookup can take up to a minute; after that it&apos;s quick.
              </motion.p>
            )}
            {error && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="max-w-xl rounded-sm border-l-4 border-flag bg-sheet px-4 py-3 text-sm text-flag"
                role="alert"
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>
        </div>

        <WorkingPaper report={sheet} example={!report} />
      </section>

      {/* TERMINAL */}
      <section className="gutter mx-auto flex max-w-6xl flex-col gap-8 pb-16">
        <AnimatePresence mode="wait">
          {report && (
            <motion.div
              key={report.ticker}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="flex flex-col gap-6"
            >
              <div className="flex flex-wrap items-end justify-between gap-4 border-t-2 border-ink pt-6">
                <h2 className="text-3xl font-extrabold sm:text-4xl">
                  {report.name} <span className="figures text-xl font-semibold text-muted">{report.ticker}</span>
                </h2>
                <div className="flex flex-wrap justify-end gap-2">
                  <ExportButtons ticker={report.ticker} />
                  {report.tenk_url && (
                    <a href={report.tenk_url} target="_blank" rel="noreferrer" className="rounded-sm border border-rule bg-sheet px-4 py-2 text-sm hover:border-input">
                      10-K on EDGAR ↗
                    </a>
                  )}
                  {report.governance?.proxy_url && (
                    <a
                      href={report.governance.proxy_url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-sm border border-rule bg-sheet px-4 py-2 text-sm hover:border-input"
                    >
                      Proxy (DEF 14A) on EDGAR ↗
                    </a>
                  )}
                </div>
              </div>

              {report.sample && <p className="rounded-sm border-l-4 border-input bg-sheet px-4 py-3 text-sm">{report.sample.note}</p>}

              <div role="tablist" aria-label="Views" className="flex gap-1 overflow-x-auto border-b border-rule">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    role="tab"
                    aria-selected={tab === t.id}
                    onClick={() => setTab(t.id)}
                    className={`-mb-px border-b-[3px] px-3 py-2.5 text-sm whitespace-nowrap ${
                      tab === t.id ? "border-ink font-semibold text-ink" : "border-transparent text-muted hover:border-rule hover:text-ink"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              <AnimatePresence mode="wait">
                <motion.div key={tab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
                  {tab === "ratios" && <RatiosPanel report={report} />}
                  {tab === "grade" && <GradePanel report={report} />}
                  {tab === "value" && <FairValuePanel report={report} />}
                  {tab === "trends" && <TrendsPanel report={report} />}
                  {tab === "compare" && <ComparePanel report={report} />}
                  {tab === "summary" && <SummaryPanel report={report} />}
                  {tab === "statements" && <StatementsPanel report={report} />}
                  {tab === "governance" && <GovernancePanel report={report} />}
                  {tab === "alerts" && <AlertsPanel report={report} />}
                  {tab === "tone" && <EarningsTonePanel report={report} />}
                  {tab === "ask" && <AskFilingPanel report={report} />}
                  {tab === "memo" && <MemoPanel report={report} />}
                </motion.div>
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <Pipeline />

      <footer className="gutter mx-auto flex max-w-6xl flex-wrap justify-between gap-4 py-8 text-sm text-muted">
        <span>Built by Jacob Braunschweig. Data from SEC EDGAR.</span>
        <span>Numbers are computed in Python; only the memo and tone text come from Gemini.</span>
      </footer>
    </main>
  );
}

const fmtFiled = (n: number) => Math.round(n).toLocaleString("en-US");

/**
 * The hero: one ratio worked out the way an auditor would on a working paper. Two filed figures (blue, ticked "a"),
 * the computed margin (black, ticked "b"), and the legend. Shows the company being looked at, or the Caterpillar example.
 */
function WorkingPaper({ report, example }: { report: Report; example: boolean }) {
  const op = report.inputs["Operating Income"];
  const rev = report.inputs.Revenue;
  const margin = report.ratios["Operating Margin"] ?? "N/A";
  const period = rev?.period || op?.period || "";
  const rows = [
    { label: op?.label || "Operating income", value: op ? fmtFiled(op.value_m) : "Not reported", filed: !!op },
    { label: rev?.label || "Total revenue", value: rev ? fmtFiled(rev.value_m) : "Not reported", filed: !!rev },
  ];
  return (
    <figure className="relative rounded-sm border border-rule bg-sheet shadow-[0_1px_0_var(--color-rule),0_10px_24px_-18px_rgb(23_36_29/0.45)]">
      {/* columnar-pad ruling: a red margin line and pale column rules */}
      <div aria-hidden className="pointer-events-none absolute inset-y-0 left-7 w-px bg-flag/40" />
      <figcaption className="flex items-baseline justify-between gap-3 border-b border-rule py-3 pr-4 pl-10 text-sm">
        <span className="font-semibold">{example ? `Example: ${report.name}` : report.name}</span>
        <span className="figures text-muted">{period} 10-K</span>
      </figcaption>
      <dl key={report.ticker} className="flex flex-col py-2 pr-4 pl-10">
        {rows.map((r, i) => (
          <div key={r.label} className="flex items-baseline justify-between gap-4 border-b border-rule/60 py-2.5">
            <dt className="text-sm">{r.label}</dt>
            <dd className={`flex items-start gap-1 figures text-lg font-semibold ${r.filed ? "text-input" : "text-muted"}`}>
              {r.value}
              {r.filed && <Tick letter="a" delay={0.3 + i * 0.25} />}
            </dd>
          </div>
        ))}
        <div className="flex items-baseline justify-between gap-4 border-t-2 border-ink py-3">
          <dt className="text-sm font-semibold">Operating margin</dt>
          <dd className="flex items-start gap-1 figures text-3xl font-extrabold">
            {margin}
            {margin !== "N/A" && <Tick letter="b" delay={0.85} className="text-ink" />}
          </dd>
        </div>
      </dl>
      <div className="flex flex-col gap-1 border-t border-rule py-3 pr-4 pl-10 text-xs leading-relaxed text-muted">
        <span>
          <Tick letter="a" className="text-input" /> Agreed to the 10-K as filed ($ millions)
        </span>
        <span>
          <Tick letter="b" className="text-ink" /> Recalculated: operating income ÷ revenue
        </span>
      </div>
    </figure>
  );
}

const STEPS = [
  { form: "10-K", title: "Pull the filing", body: "edgartools reads the latest annual report's XBRL straight from SEC EDGAR." },
  { form: "XBRL", title: "Match exact line items", body: "Each ratio input comes from a named XBRL concept in the latest fiscal year, never a guess." },
  { form: "Python", title: "Compute the ratios", body: "Plain Python does the math, so the same filing always gives the same answer." },
  { form: "DEF 14A", title: "Read the proxy", body: "The proxy text is searched for board, pay and clawback topics, with the sentence quoted as proof." },
  { form: "Gemini", title: "Write the memo", body: "AI only writes prose, from the numbers and quotes above. It never produces a figure." },
];

/** How the numbers are made. A real sequence (the order the API runs in), so the steps are numbered. */
function Pipeline() {
  return (
    <section className="border-t-2 border-ink bg-sheet">
      <div className="gutter mx-auto flex max-w-6xl flex-col gap-8 py-14">
        <h2 className="text-2xl font-extrabold sm:text-3xl">How the numbers are made</h2>
        <ol className="grid gap-x-8 gap-y-6 md:grid-cols-5">
          {STEPS.map((s, i) => (
            <li key={s.title} className="flex flex-col gap-2 border-t border-rule pt-3">
              <span className="figures text-sm text-muted">
                Step {i + 1}, {s.form}
              </span>
              <h3 className="text-base font-bold">{s.title}</h3>
              <p className="text-sm leading-relaxed text-muted">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
