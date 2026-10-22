"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import type { Report } from "@/lib/types";
import { API_URL, fetchGovernance, fetchPayEfficiency, fetchReport, fetchRisks, fetchTrends } from "@/lib/api";
import { Pipeline, TracedRatio } from "./landing";
import { GovernancePanel, MemoPanel, RatiosPanel, StatementsPanel } from "./panels";
import { ComparePanel, ExportButtons, TrendsPanel } from "./features";
import { SummaryPanel } from "./summary";
import { AskFilingPanel, EarningsTonePanel } from "./ai_tools";
import { FairValuePanel } from "./valuation";
import { GradePanel } from "./grade";
import { AlertsPanel } from "./alerts";
import { QUICK } from "@/lib/tickers";

// Names for the example tickers, so the suggestion reads as a sentence
const NAMES: Record<string, string> = { AAPL: "Apple", MSFT: "Microsoft", NVDA: "Nvidia", BE: "Bloom Energy" };
const EXAMPLES = QUICK.map((t) => [t, NAMES[t] ?? t] as const);

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
  const results = useRef<HTMLElement>(null);

  // Bring the report into view when a new company loads, so the answer to "Pull filings" is on screen
  useEffect(() => {
    if (!report) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    results.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  }, [report?.ticker]); // eslint-disable-line react-hooks/exhaustive-deps

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

  return (
    <MotionConfig reducedMotion="user">
      <main className="min-h-screen">
        <header className="border-b border-rule">
          <div className="gutter mx-auto flex max-w-6xl flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-4">
            <span className="font-display text-lg font-semibold">SEC Financial &amp; Corporate Governance Terminal</span>
            <span className="caption">{API_URL ? "Reading live from SEC EDGAR" : "Preview: Caterpillar sample data only"}</span>
          </div>
        </header>

        {/* HERO: what the app does, shown on a real filing rather than described */}
        <section className="gutter mx-auto grid max-w-6xl gap-12 pt-12 pb-16 sm:pt-16 lg:grid-cols-12 lg:gap-10">
          <div className="flex flex-col gap-6 lg:col-span-5">
            <h1 className="text-[2.5rem] leading-[1.05] font-extrabold sm:text-6xl">See the line in the 10‑K behind every ratio.</h1>
            <p className="max-w-[34rem] text-lg leading-relaxed text-muted">
              Type a ticker. The app pulls the company&apos;s latest 10‑K and proxy statement from SEC EDGAR, works out the ratios in plain
              Python, and shows the filed line item each one came from. Gemini writes a memo at the end, but AI never produces a figure.
            </p>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                load(ticker);
              }}
              className="flex flex-col gap-3"
            >
              <label htmlFor="ticker" className="text-sm font-medium">
                Ticker symbol
              </label>
              <div className="flex max-w-md items-stretch border-2 border-ink focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-ink">
                <input
                  id="ticker"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder={API_URL ? "AAPL" : "CAT"}
                  autoComplete="off"
                  spellCheck={false}
                  className="min-w-0 flex-1 bg-page px-4 py-3 text-xl font-semibold tracking-wide uppercase outline-none placeholder:font-normal placeholder:text-muted/50"
                />
                <button
                  type="submit"
                  disabled={loading}
                  className="bg-ink px-5 font-medium text-page transition-colors duration-150 hover:bg-blue focus-visible:outline-offset-[-4px] focus-visible:outline-page disabled:opacity-70"
                >
                  {loading ? "Pulling…" : "Pull filings"}
                </button>
              </div>
              <p className="text-sm text-muted">
                {API_URL ? "Or try " : "The preview has one company: "}
                {(API_URL ? EXAMPLES : [["CAT", "Caterpillar"]]).map(([sym, name], n, all) => (
                  <span key={sym}>
                    <button type="button" onClick={() => load(sym)} className="text-ink underline decoration-rule decoration-2 underline-offset-4 transition-colors duration-150 hover:decoration-mark">
                      {name} ({sym})
                    </button>
                    {n < all.length - 2 ? ", " : n === all.length - 2 ? " or " : "."}
                  </span>
                ))}
              </p>
            </form>

            <AnimatePresence>
              {loading && slow && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                  className="max-w-md text-sm text-muted"
                  role="status"
                >
                  Pulling {ticker}&apos;s 10-K and proxy from SEC EDGAR. A company&apos;s first search reads its filings from SEC and can take up to a
                  minute; repeat searches are quick.
                </motion.p>
              )}
              {error && (
                <motion.p
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                  className="max-w-md border-l-4 border-red bg-red/5 px-4 py-3 text-sm text-red"
                  role="alert"
                >
                  {error}
                </motion.p>
              )}
            </AnimatePresence>
          </div>

          <div className="lg:col-span-7 lg:pt-2">
            <TracedRatio />
          </div>
        </section>

        {/* REPORT */}
        <AnimatePresence mode="wait">
          {report && (
            <motion.section
              ref={results}
              key={report.ticker}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="scroll-mt-4 border-t-2 border-ink"
            >
              <div className="gutter mx-auto flex max-w-6xl flex-col gap-8 py-10">
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <h2 className="text-4xl font-extrabold sm:text-5xl">
                    {report.name} <span className="font-sans text-2xl font-normal text-muted">{report.ticker}</span>
                  </h2>
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
                    <ExportButtons ticker={report.ticker} />
                    {report.tenk_url && (
                      <a href={report.tenk_url} target="_blank" rel="noreferrer" className="link">
                        10-K on EDGAR
                      </a>
                    )}
                    {report.governance?.proxy_url && (
                      <a href={report.governance.proxy_url} target="_blank" rel="noreferrer" className="link">
                        DEF 14A on EDGAR
                      </a>
                    )}
                  </div>
                </div>

                {report.sample && <p className="border-l-4 border-mark bg-sheet px-4 py-3 text-sm">{report.sample.note}</p>}

                <div role="tablist" aria-label="Report sections" className="-mx-4 flex overflow-x-auto border-b border-rule px-4 sm:mx-0 sm:px-0">
                  {TABS.map((t) => (
                    <button
                      key={t.id}
                      role="tab"
                      aria-selected={tab === t.id}
                      onClick={() => setTab(t.id)}
                      className={`relative shrink-0 px-3 pt-2 pb-3 text-sm whitespace-nowrap transition-colors duration-150 ${tab === t.id ? "font-semibold text-ink" : "text-muted hover:text-ink"}`}
                    >
                      {tab === t.id && (
                        <motion.span layoutId="tab-mark" aria-hidden className="absolute inset-x-1 bottom-0 h-[5px] bg-mark" transition={{ duration: 0.22, ease: [0.3, 0.7, 0.2, 1] }} />
                      )}
                      <span className="relative">{t.label}</span>
                    </button>
                  ))}
                </div>

                <AnimatePresence mode="wait">
                  <motion.div key={tab} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
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
              </div>
            </motion.section>
          )}
        </AnimatePresence>

        <Pipeline />

        <footer className="gutter mx-auto flex max-w-6xl flex-wrap justify-between gap-x-8 gap-y-2 border-t border-rule py-8 text-sm text-muted">
          <span>Built by Jacob Braunschweig. Data from SEC EDGAR.</span>
          <span>Numbers: Python. Memo: Gemini.</span>
        </footer>
      </main>
    </MotionConfig>
  );
}
