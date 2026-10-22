"use client";

import { useState } from "react";
import { motion } from "motion/react";
import type { Report } from "@/lib/types";
import { API_URL, callApi, errorText } from "@/lib/api";

// ---------- API shapes (kept here so other features' type files stay untouched) ----------

type WordCheck = { words: number; confident_per_1000: number; cautious_per_1000: number };
type Release = { accession: string; filed: string; period: string; url: string | null; filing_url: string; word_check: WordCheck };
type Quoted = { latest_quote: string; prior_quote: string; latest_verified: boolean | null; prior_verified: boolean | null; verified: boolean };
type Shift = Quoted & { topic: string; direction: "more confident" | "less confident" | "about the same"; why: string };
type Tone = {
  ticker: string;
  latest: Release | null;
  prior: Release | null;
  available: boolean;
  reason?: string;
  overall?: "more confident" | "less confident" | "about the same";
  summary?: string;
  guidance?: Quoted & { change: string; detail: string };
  shifts?: Shift[];
  model?: string;
  cached?: boolean;
};
type Answer = {
  question: string;
  found: boolean;
  answer: string;
  quote: string;
  verified: boolean;
  tenk_url: string;
  tenk_date: string;
  period: string;
  excerpts: string[];
  model: string | null;
  cached?: boolean;
};

async function fetchTone(ticker: string): Promise<Tone> {
  const res = await callApi(`/api/earnings-tone/${encodeURIComponent(ticker)}`);
  if (!res.ok) throw new Error(await errorText(res, "the earnings releases"));
  return res.json();
}

async function askFiling(ticker: string, question: string): Promise<Answer> {
  const res = await callApi(`/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, question }),
  });
  if (!res.ok) throw new Error(await errorText(res, "the answer"));
  return res.json();
}

// ---------- Small shared pieces ----------

function ErrorNote({ text }: { text: string }) {
  return <p className="rounded-xl border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">{text}</p>;
}

function Pulse({ text }: { text: string }) {
  return (
    <div className="flex animate-pulse items-center gap-3 rounded-2xl border border-rule bg-sheet p-5 text-sm text-muted">
      <span className="h-2 w-2 rounded-[3px] bg-ink" /> {text}
    </div>
  );
}

/** Green when the quote was found word for word in the filing, red when it wasn't. */
function Check({ ok }: { ok: boolean | null }) {
  if (ok === null) return null;
  return (
    <span className={`ml-2 rounded-[3px] px-2 py-0.5 font-figures text-[10px] whitespace-nowrap ${ok ? "bg-green/15 text-green" : "bg-red/15 text-red"}`}>
      {ok ? "✓ in filing" : "✗ not found in filing"}
    </span>
  );
}

function Quote({ label, text, ok }: { label: string; text: string; ok: boolean | null }) {
  if (!text) return null;
  return (
    <p className={`text-sm leading-relaxed ${ok === false ? "text-muted/60" : "text-muted"}`}>
      <span className="font-figures text-xs text-ink">{label}</span> “{text}”
      <Check ok={ok} />
    </p>
  );
}

const TONE_STYLE: Record<string, { text: string; cls: string; arrow: string }> = {
  "more confident": { text: "More confident", cls: "bg-green/15 text-green", arrow: "▲" },
  "less confident": { text: "Less confident", cls: "bg-red/15 text-red", arrow: "▼" },
  "about the same": { text: "About the same", cls: "bg-blue/15 text-blue", arrow: "●" },
};

const GUIDANCE_STYLE: Record<string, string> = {
  raised: "bg-green/15 text-green",
  introduced: "bg-green/15 text-green",
  maintained: "bg-blue/15 text-blue",
  mixed: "bg-blue/15 text-blue",
  lowered: "bg-red/15 text-red",
  withdrawn: "bg-red/15 text-red",
  "not given": "bg-rule text-muted",
};

function Badge({ cls, children }: { cls: string; children: React.ReactNode }) {
  return <span className={`rounded-[3px] px-3 py-1 font-figures text-xs ${cls}`}>{children}</span>;
}

function OnlineOnly({ what }: { what: string }) {
  return <p className="text-sm text-muted">{what} reads filings from SEC with the AI, so it turns on once the API is online.</p>;
}

// ---------- Earnings tone tab ----------

export function EarningsTonePanel({ report }: { report: Report }) {
  const [state, setState] = useState<{ loading: boolean; error?: string; tone?: Tone }>({ loading: false });
  if (!API_URL || report.sample) return <OnlineOnly what="Earnings tone" />;

  async function run() {
    setState({ loading: true });
    try {
      setState({ loading: false, tone: await fetchTone(report.ticker) });
    } catch (e) {
      setState({ loading: false, error: (e as Error).message });
    }
  }

  const t = state.tone?.ticker === report.ticker ? state.tone : undefined;
  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-2xl text-sm text-muted">
        Compares the latest quarterly earnings press release (8-K, Exhibit 99.1) with the one before it: does management sound more or less
        confident, and did guidance change? Every quote is checked word for word against the release it came from.
      </p>
      {!t && (
        <div>
          <button
            onClick={run}
            disabled={state.loading}
            className="rounded-[3px] bg-blue px-6 py-3 font-medium text-page disabled:opacity-60"
          >
            {state.loading ? "Reading both releases…" : "Compare the last two earnings releases"}
          </button>
        </div>
      )}
      {state.loading && <Pulse text="Finding both press releases on SEC EDGAR, then the AI compares them. Usually under a minute." />}
      {state.error && <ErrorNote text={state.error} />}
      {t && <ToneResult t={t} />}
    </div>
  );
}

function ReleaseLink({ label, r }: { label: string; r: Release | null }) {
  if (!r) return null;
  return (
    <a href={r.url || r.filing_url} target="_blank" rel="noreferrer" className="rounded-[3px] border border-rule px-3 py-1.5 text-xs hover:border-blue">
      {label}: filed <span className="font-figures">{r.filed}</span> ↗
    </a>
  );
}

function ToneResult({ t }: { t: Tone }) {
  const links = (
    <div className="flex flex-wrap gap-2">
      <ReleaseLink label="Latest release" r={t.latest} />
      <ReleaseLink label="Prior release" r={t.prior} />
    </div>
  );
  if (!t.available) {
    return (
      <div className="flex flex-col gap-3">
        <p className="text-sm text-muted">{t.reason}</p>
        {links}
      </div>
    );
  }
  const style = TONE_STYLE[t.overall || "about the same"];
  const g = t.guidance!;
  const wl = t.latest!.word_check;
  const wp = t.prior!.word_check;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-5">
      <div className="flex flex-col gap-3 rounded-2xl border border-rule bg-sheet p-5">
        <div className="flex flex-wrap items-center gap-3">
          <span className="caption">Management tone vs last quarter</span>
          <Badge cls={style.cls}>
            {style.arrow} {style.text}
          </Badge>
        </div>
        {t.summary && <p className="leading-relaxed">{t.summary}</p>}
        {links}
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-rule bg-sheet p-5">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-lg font-bold">Guidance</h3>
          <Badge cls={GUIDANCE_STYLE[g.change] || GUIDANCE_STYLE["not given"]}>{g.change}</Badge>
        </div>
        {g.detail && <p className="text-sm leading-relaxed">{g.detail}</p>}
        <Quote label="Now:" text={g.latest_quote} ok={g.latest_verified} />
        <Quote label="Before:" text={g.prior_quote} ok={g.prior_verified} />
      </div>

      {(t.shifts?.length ?? 0) > 0 && (
        <div className="flex flex-col divide-y divide-rule rounded-2xl border border-rule">
          {t.shifts!.map((s, i) => {
            const st = TONE_STYLE[s.direction];
            return (
              <div key={i} className={`flex flex-col gap-2 p-5 ${s.verified ? "" : "opacity-70"}`}>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-medium capitalize">{s.topic}</span>
                  <span className={`font-figures text-xs ${st.cls.split(" ")[1]}`}>
                    {st.arrow} {st.text}
                  </span>
                  {!s.verified && <span className="font-figures text-xs text-red">quote not confirmed, don&apos;t rely on this one</span>}
                </div>
                {s.why && <p className="text-sm">{s.why}</p>}
                <Quote label="Now:" text={s.latest_quote} ok={s.latest_verified} />
                <Quote label="Before:" text={s.prior_quote} ok={s.prior_verified} />
              </div>
            );
          })}
        </div>
      )}

      <p className="text-xs leading-relaxed text-muted">
        Word check (plain count, no AI), per 1,000 words of narrative text: confident words{" "}
        <span className="tnum font-figures text-ink">
          {wp.confident_per_1000} → {wl.confident_per_1000}
        </span>
        , cautious words{" "}
        <span className="tnum font-figures text-ink">
          {wp.cautious_per_1000} → {wl.cautious_per_1000}
        </span>{" "}
        (prior → latest). AI reading by {t.model}
        {t.cached ? " (saved result)" : ""}. Tables, safe-harbor and webcast text are left out before reading.
      </p>
    </motion.div>
  );
}

// ---------- Ask a filing tab ----------

const SUGGESTED = [
  "How much debt is due next year?",
  "How many employees does the company have?",
  "Who are the main competitors?",
  "How much did the company spend on share buybacks?",
];

export function AskFilingPanel({ report }: { report: Report }) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<{ ticker: string; a: Answer }[]>([]);
  if (!API_URL || report.sample) return <OnlineOnly what="Ask a filing" />;

  async function ask(q: string) {
    const text = q.trim();
    if (!text || busy) return;
    setQuestion(text);
    setBusy(true);
    setError(null);
    try {
      const a = await askFiling(report.ticker, text);
      setAnswers((prev) => [{ ticker: report.ticker, a }, ...prev.filter((x) => x.a.question !== a.question || x.ticker !== report.ticker)]);
      setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const mine = answers.filter((x) => x.ticker === report.ticker).map((x) => x.a);
  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-2xl text-sm text-muted">
        Ask a question about {report.name}&apos;s latest 10-K. The answer comes only from the filing, with the sentence it used. A green check
        means that sentence was found word for word in the 10-K.
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="flex flex-col gap-3 sm:flex-row"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={300}
          placeholder="e.g. How much debt is due next year?"
          className="min-w-0 flex-1 rounded-xl border border-rule bg-sheet px-4 py-3 outline-none focus:border-blue"
        />
        <button
          type="submit"
          disabled={busy || question.trim().length < 5}
          className="rounded-xl bg-blue px-6 py-3 font-medium text-page disabled:opacity-60"
        >
          {busy ? "Reading the 10-K…" : "Ask"}
        </button>
      </form>
      <div className="flex flex-wrap gap-2">
        {SUGGESTED.map((q) => (
          <button
            key={q}
            type="button"
            disabled={busy}
            onClick={() => ask(q)}
            className="rounded-[3px] border border-rule px-3 py-1 text-xs text-muted transition-colors hover:border-blue hover:text-ink disabled:opacity-50"
          >
            {q}
          </button>
        ))}
      </div>
      {busy && <Pulse text="Searching the 10-K for the matching passages, then the AI answers from them. The first question for a company takes longest." />}
      {error && <ErrorNote text={error} />}
      {mine.map((a) => (
        <AnswerCard key={a.question} a={a} />
      ))}
    </div>
  );
}

function AnswerCard({ a }: { a: Answer }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col gap-3 rounded-2xl border border-rule bg-sheet p-5">
      <span className="font-figures text-xs text-blue">Q: {a.question}</span>
      <p className="leading-relaxed">{a.answer}</p>
      {a.quote ? (
        <p className={`border-l-2 pl-3 text-sm leading-relaxed ${a.verified ? "border-green text-muted" : "border-red text-muted/70"}`}>
          “{a.quote}”
          <Check ok={a.verified} />
        </p>
      ) : (
        a.found === false && <p className="text-xs text-muted">No supporting quote: the 10-K passages searched don&apos;t answer this.</p>
      )}
      {a.quote && !a.verified && (
        <p className="text-xs text-red">The AI&apos;s quote wasn&apos;t found in the 10-K, so check the filing before relying on this answer.</p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
        <a href={a.tenk_url} target="_blank" rel="noreferrer" className="rounded-[3px] border border-rule px-3 py-1 hover:border-blue">
          10-K filed {a.tenk_date} ↗
        </a>
        {a.model && (
          <span>
            Answered by {a.model}
            {a.cached ? " (saved answer)" : ""}
          </span>
        )}
      </div>
      {a.excerpts.length > 0 && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer hover:text-ink">The {a.excerpts.length} 10-K passages the AI read</summary>
          <div className="mt-2 flex max-h-72 flex-col gap-2 overflow-auto">
            {a.excerpts.map((e, i) => (
              <p key={i} className="rounded-lg bg-page/60 p-2 leading-relaxed">
                [{i + 1}] {e}
              </p>
            ))}
          </div>
        </details>
      )}
    </motion.div>
  );
}
