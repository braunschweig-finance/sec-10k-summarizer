"use client";

import { useRef, useState } from "react";
import { AnimatePresence, motion, useInView } from "motion/react";
import type { Report } from "@/lib/types";
import { API_URL, fetchGovernance, fetchPayEfficiency, fetchReport, fetchRisks, fetchTrends } from "@/lib/api";
import { Aurora, TickerTape, WordReveal } from "./fx";
import { GovernancePanel, MemoPanel, RatiosPanel, StatementsPanel } from "./panels";
import { ComparePanel, ExportButtons, TrendsPanel } from "./features";
import { SummaryPanel } from "./summary";
import { AlertsPanel } from "./alerts";
import { QUICK } from "@/lib/tickers";

const TABS = [
  { id: "ratios", label: "Ratios" },
  { id: "trends", label: "Trends" },
  { id: "compare", label: "Compare" },
  { id: "summary", label: "10-K Summary" },
  { id: "statements", label: "Statements" },
  { id: "governance", label: "Governance" },
  { id: "alerts", label: "Red Flags & Insiders" },
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

  return (
    <main className="min-h-screen">
      {/* HERO */}
      <section className="relative overflow-hidden">
        <Aurora />
        <div className="gutter relative mx-auto flex max-w-6xl flex-col gap-8 pt-16 pb-12 sm:pt-24">
          <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="flex flex-wrap items-center gap-3">
            <span className="flex items-center gap-2 rounded-full border border-line bg-panel/70 px-3 py-1 font-mono text-xs text-muted backdrop-blur">
              <span className="relative flex h-2 w-2">
                <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${API_URL ? "bg-teal" : "bg-brass"} opacity-60`} />
                <span className={`relative inline-flex h-2 w-2 rounded-full ${API_URL ? "bg-teal" : "bg-brass"}`} />
              </span>
              {API_URL ? "Live · SEC EDGAR" : "Preview · sample data"}
            </span>
            <span className="eyebrow">Form 10-K · Form DEF 14A · XBRL</span>
          </motion.div>

          <h1 className="max-w-4xl text-5xl leading-[0.95] font-extrabold tracking-tight sm:text-7xl">
            <WordReveal text="Read any company's filings like an analyst." accent="analyst." />
          </h1>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 }}
            className="max-w-xl text-lg leading-relaxed text-muted"
          >
            Audited statements, ratios you can trace to the exact filed line, and governance checks quoted straight from the proxy statement.
          </motion.p>

          <motion.form
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.75 }}
            onSubmit={(e) => {
              e.preventDefault();
              load(ticker);
            }}
            className="flex max-w-xl flex-col gap-3"
          >
            <div className="group relative rounded-2xl p-px">
              <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-brass via-violet to-teal opacity-50 blur-sm transition-opacity group-focus-within:opacity-100" />
              <div className="relative flex items-center gap-2 rounded-2xl bg-ink p-2">
                <label htmlFor="ticker" className="pl-3 font-mono text-sm text-muted">
                  $
                </label>
                <input
                  id="ticker"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value.toUpperCase())}
                  placeholder="Type a ticker, e.g. AAPL"
                  autoComplete="off"
                  spellCheck={false}
                  className="min-w-0 flex-1 bg-transparent py-2 font-mono text-lg tracking-wider uppercase outline-none placeholder:text-muted/60"
                />
                <motion.button
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.96 }}
                  type="submit"
                  className="rounded-xl bg-paper px-5 py-2.5 font-medium text-ink"
                >
                  {loading ? "Pulling…" : "Analyze"}
                </motion.button>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted">Try</span>
              {QUICK.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => load(q)}
                  className="rounded-full border border-line px-3 py-1 font-mono text-xs text-muted transition-colors hover:border-brass hover:text-paper"
                >
                  {q}
                </button>
              ))}
            </div>
          </motion.form>

          <AnimatePresence>
            {loading && slow && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="max-w-xl text-sm text-muted"
                role="status"
              >
                Pulling {ticker}&apos;s 10-K and proxy from SEC EDGAR. A company's first search reads its filings from SEC and can take up to a minute; repeat searches are quick.
              </motion.p>
            )}
            {error && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="max-w-xl rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose"
                role="alert"
              >
                {error}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </section>

      <TickerTape />

      {/* TERMINAL */}
      <section className="gutter mx-auto flex max-w-6xl flex-col gap-8 py-14">
        <AnimatePresence mode="wait">
          {report && (
            <motion.div
              key={report.ticker}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.5 }}
              className="flex flex-col gap-8"
            >
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div className="flex flex-col gap-2">
                  <span className="eyebrow">Now analyzing</span>
                  <h2 className="text-4xl font-extrabold tracking-tight sm:text-5xl">
                    {report.name} <span className="font-mono text-2xl font-normal text-brass">{report.ticker}</span>
                  </h2>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <ExportButtons ticker={report.ticker} />
                  {report.tenk_url && (
                    <a href={report.tenk_url} target="_blank" rel="noreferrer" className="rounded-full border border-line px-4 py-2 text-sm hover:border-brass">
                      10-K on EDGAR ↗
                    </a>
                  )}
                  {report.governance?.proxy_url && (
                    <a
                      href={report.governance.proxy_url}
                      target="_blank"
                      rel="noreferrer"
                      className="rounded-full border border-line px-4 py-2 text-sm hover:border-brass"
                    >
                      DEF 14A on EDGAR ↗
                    </a>
                  )}
                </div>
              </div>

              {report.sample && (
                <p className="rounded-xl border border-brass/30 bg-brass/10 px-4 py-3 text-sm text-brass">{report.sample.note}</p>
              )}

              <div role="tablist" className="flex gap-1 overflow-x-auto rounded-2xl border border-line bg-panel p-1">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    role="tab"
                    aria-selected={tab === t.id}
                    onClick={() => setTab(t.id)}
                    className={`relative flex-1 rounded-xl px-4 py-2.5 text-sm whitespace-nowrap transition-colors ${tab === t.id ? "text-ink" : "text-muted hover:text-paper"}`}
                  >
                    {tab === t.id && (
                      <motion.span layoutId="tab-pill" className="absolute inset-0 rounded-xl bg-brass" transition={{ type: "spring", bounce: 0.2, duration: 0.5 }} />
                    )}
                    <span className="relative font-medium">{t.label}</span>
                  </button>
                ))}
              </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={tab}
                  initial={{ opacity: 0, x: 16 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -16 }}
                  transition={{ duration: 0.25 }}
                >
                  {tab === "ratios" && <RatiosPanel report={report} />}
                  {tab === "trends" && <TrendsPanel report={report} />}
                  {tab === "compare" && <ComparePanel report={report} />}
                  {tab === "summary" && <SummaryPanel report={report} />}
                  {tab === "statements" && <StatementsPanel report={report} />}
                  {tab === "governance" && <GovernancePanel report={report} />}
                  {tab === "alerts" && <AlertsPanel report={report} />}
                  {tab === "memo" && <MemoPanel report={report} />}
                </motion.div>
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <Pipeline />

      <footer className="gutter mx-auto flex max-w-6xl flex-wrap justify-between gap-4 border-t border-line py-8 text-sm text-muted">
        <span>Built by Jacob Braunschweig · Data from SEC EDGAR</span>
        <span className="font-mono text-xs">Numbers: Python · Memo: Gemini</span>
      </footer>
    </main>
  );
}

const STEPS = [
  { form: "10-K", title: "Pull the filing", body: "edgartools reads the latest annual report's XBRL straight from SEC EDGAR." },
  { form: "XBRL", title: "Match exact line items", body: "Each ratio input comes from a named XBRL concept in the latest fiscal year, never a guess." },
  { form: "Python", title: "Compute the ratios", body: "Plain Python does the math, so the same filing always gives the same answer." },
  { form: "DEF 14A", title: "Read the proxy", body: "The proxy text is searched for board, pay and clawback topics, with the sentence quoted as proof." },
  { form: "Gemini", title: "Write the memo", body: "AI only writes prose, from the numbers and quotes above. It never produces a figure." },
];

/** "How it works": the order is the real pipeline order, and the line draws as you scroll. */
function Pipeline() {
  const ref = useRef<HTMLOListElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  return (
    <section className="border-t border-line bg-panel/40">
      <div className="gutter mx-auto flex max-w-6xl flex-col gap-8 py-14">
        <div className="flex flex-col gap-2">
          <span className="eyebrow">How it works</span>
          <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">From filing to finding, in five steps</h2>
        </div>
        <ol ref={ref} className="relative grid gap-6 md:grid-cols-5">
          <motion.div
            aria-hidden
            className="absolute top-4 left-4 hidden h-px origin-left bg-gradient-to-r from-brass via-violet to-teal md:block"
            style={{ right: "1rem" }}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: inView ? 1 : 0 }}
            transition={{ duration: 1.6, ease: [0.16, 1, 0.3, 1] }}
          />
          {STEPS.map((s, i) => (
            <li key={s.title} className="relative flex flex-col gap-3">
              <motion.span
                className="relative z-10 flex h-8 w-8 items-center justify-center rounded-full border border-line bg-ink font-mono text-xs text-brass"
                animate={inView ? { scale: [1, 1.25, 1] } : undefined}
                transition={{ delay: 0.25 * i + 0.2, duration: 0.5 }}
              >
                {i + 1}
              </motion.span>
              <span className="font-mono text-xs text-muted">{s.form}</span>
              <h3 className="text-lg font-bold">{s.title}</h3>
              <p className="text-sm leading-relaxed text-muted">{s.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
