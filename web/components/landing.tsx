"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, animate, motion, useReducedMotion, useScroll, useSpring } from "motion/react";

// Caterpillar FY2025, $ millions, the same figures as lib/sample.ts (10-K read by the live app on Oct 17-18, 2026).
// Labels are the line names in Caterpillar's statements; tags are the us-gaap concepts the API matches first.
const LINES = {
  rev: { label: "Total sales and revenues", value: "67,589", tag: "us-gaap:Revenues" },
  cogs: { label: "Cost of goods sold", value: "44,752", tag: "us-gaap:CostOfGoodsAndServicesSold" },
  op: { label: "Operating profit", value: "11,151", tag: "us-gaap:OperatingIncomeLoss" },
  ca: { label: "Total current assets", value: "52,485", tag: "us-gaap:AssetsCurrent" },
  cl: { label: "Total current liabilities", value: "36,558", tag: "us-gaap:LiabilitiesCurrent" },
} as const;
type LineId = keyof typeof LINES;

type Part = string | { line: LineId };
// Results checked by hand: 22,837 / 67,589 = 0.3379; 11,151 / 67,589 = 0.1650; 52,485 / 36,558 = 1.4357
const RATIOS: { name: string; uses: LineId[]; formula: Part[]; result: number; decimals: number; unit: string }[] = [
  { name: "Gross margin", uses: ["rev", "cogs"], formula: ["(", { line: "rev" }, " − ", { line: "cogs" }, ") ÷ ", { line: "rev" }], result: 33.8, decimals: 1, unit: "%" },
  { name: "Operating margin", uses: ["op", "rev"], formula: [{ line: "op" }, " ÷ ", { line: "rev" }], result: 16.5, decimals: 1, unit: "%" },
  { name: "Current ratio", uses: ["ca", "cl"], formula: [{ line: "ca" }, " ÷ ", { line: "cl" }], result: 1.44, decimals: 2, unit: "x" },
];

const HOLD_MS = 5200;

/** The hero exhibit: an excerpt of Caterpillar's 10-K with one ratio at a time traced back to the lines it uses. */
export function TracedRatio() {
  const reduce = useReducedMotion();
  const [i, setI] = useState(0);
  const [auto, setAuto] = useState(true);
  const [paused, setPaused] = useState(false);
  const r = RATIOS[i];

  useEffect(() => {
    if (reduce || !auto || paused) return;
    const t = setTimeout(() => setI((n) => (n + 1) % RATIOS.length), HOLD_MS);
    return () => clearTimeout(t);
  }, [i, auto, paused, reduce]);

  const row = (id: LineId) => {
    const on = r.uses.includes(id);
    const order = r.uses.indexOf(id);
    return (
      <div key={id} className="relative grid grid-cols-[1fr_auto] items-baseline gap-x-6 border-t border-rule px-4 py-2 sm:px-5">
        {/* the highlighter stroke, drawn left to right */}
        <motion.span
          aria-hidden
          className="absolute inset-x-2 inset-y-1 origin-left bg-mark"
          initial={false}
          animate={{ scaleX: on ? 1 : 0, opacity: on ? 1 : 0 }}
          transition={{ duration: 0.32, delay: on ? 0.15 + order * 0.35 : 0, ease: [0.3, 0.7, 0.2, 1] }}
        />
        <span className="relative">
          {LINES[id].label}
          <motion.span
            className="ml-3 inline-block font-code text-[11px] text-muted"
            initial={false}
            animate={{ opacity: on ? 1 : 0 }}
            transition={{ duration: 0.2, delay: on ? 0.35 + order * 0.35 : 0 }}
          >
            {LINES[id].tag}
          </motion.span>
        </span>
        <span className="tnum relative text-right">{LINES[id].value}</span>
      </div>
    );
  };

  return (
    <figure
      className="border border-rule bg-page"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 px-4 pt-4 pb-3 sm:px-5">
        <span className="font-display font-semibold">Caterpillar Inc.</span>
        <span className="caption">Form 10-K, fiscal 2025. Dollars in millions</span>
      </div>
      <div className="font-display text-[15px]">
        <div className="border-t border-rule bg-sheet px-4 py-1.5 text-sm italic text-muted sm:px-5">Results of operations</div>
        {(["rev", "cogs", "op"] as const).map(row)}
        <div className="border-t border-rule bg-sheet px-4 py-1.5 text-sm italic text-muted sm:px-5">Financial position at December 31, 2025</div>
        {(["ca", "cl"] as const).map(row)}
      </div>

      <div className="border-t-2 border-ink px-4 pt-3 pb-4 sm:px-5">
        <div role="tablist" aria-label="Ratio to trace" className="-mx-1 flex flex-wrap gap-x-1">
          {RATIOS.map((x, n) => (
            <button
              key={x.name}
              role="tab"
              aria-selected={n === i}
              onClick={() => {
                setI(n);
                setAuto(false);
              }}
              className={`px-1 py-1 text-sm transition-colors duration-150 ${n === i ? "font-semibold text-ink" : "text-muted hover:text-ink"}`}
            >
              <span className={n === i ? "marked" : ""}>{x.name}</span>
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={r.name}
            className="mt-2 flex flex-wrap items-baseline gap-x-3 gap-y-1"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
          >
            <motion.span
              className="tnum text-lg"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: reduce ? 0 : 0.2 + r.uses.length * 0.35, duration: 0.25 }}
            >
              {r.formula.map((p, n) =>
                typeof p === "string" ? (
                  <span key={n} className="text-muted">
                    {p}
                  </span>
                ) : (
                  <span key={n} className="text-blue">
                    {LINES[p.line].value}
                  </span>
                )
              )}
              <span className="text-muted"> =</span>
            </motion.span>
            <Result key={r.name} to={r.result} decimals={r.decimals} unit={r.unit} delay={reduce ? 0 : 0.35 + r.uses.length * 0.35} />
          </motion.div>
        </AnimatePresence>
        <p className="caption mt-2">Blue figures are copied from the filing above. The result is calculated in Python.</p>
      </div>
    </figure>
  );
}

function Result({ to, decimals, unit, delay }: { to: number; decimals: number; unit: string; delay: number }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? to : 0);
  useEffect(() => {
    if (reduce) return setN(to);
    const c = animate(0, to, { delay, duration: 0.8, ease: [0.16, 1, 0.3, 1], onUpdate: setN });
    return () => c.stop();
  }, [to, delay, reduce]);
  return (
    <span className="tnum font-display text-4xl font-extrabold" aria-live="polite">
      {n.toFixed(decimals)}
      {unit}
    </span>
  );
}

// ---------- How it works: the five steps, each with what that step actually produces for Caterpillar ----------

const STEPS: { form: string; title: string; body: string; out: React.ReactNode }[] = [
  {
    form: "10-K",
    title: "Pull the filing",
    body: "edgartools reads the latest annual report's XBRL straight from SEC EDGAR.",
    out: (
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
        <dt className="text-muted">Company</dt>
        <dd>Caterpillar Inc., CIK 18230</dd>
        <dt className="text-muted">Annual report</dt>
        <dd>
          <Swipe>Form 10-K</Swipe> for the year ended December 31, 2025
        </dd>
        <dt className="text-muted">Proxy</dt>
        <dd>Form DEF 14A, filed April 30, 2026</dd>
      </dl>
    ),
  },
  {
    form: "XBRL",
    title: "Match exact line items",
    body: "Each ratio input comes from a named XBRL concept in the latest fiscal year, never a guess.",
    out: (
      <div className="flex flex-col">
        {(["rev", "cogs", "op"] as const).map((id, n) => (
          <div key={id} className={`grid grid-cols-[1fr_auto] gap-x-6 py-1 ${n ? "border-t border-rule" : ""}`}>
            <span className="font-code text-[13px] break-all">{LINES[id].tag}</span>
            <span className="tnum text-blue">{n === 0 ? <Swipe>{LINES[id].value}</Swipe> : LINES[id].value}</span>
          </div>
        ))}
      </div>
    ),
  },
  {
    form: "Python",
    title: "Compute the ratios",
    body: "Plain Python does the math, so the same filing always gives the same answer.",
    // 22,837 / 67,589 = 33.8%; 11,151 / 67,589 = 16.5%; 52,485 / 36,558 = 1.44x; 77,267 / 21,318 = 3.62x
    out: (
      <div className="flex flex-col">
        {[
          ["Gross margin", "22,837 ÷ 67,589", "33.8%"],
          ["Operating margin", "11,151 ÷ 67,589", "16.5%"],
          ["Current ratio", "52,485 ÷ 36,558", "1.44x"],
          ["Liabilities to equity", "77,267 ÷ 21,318", "3.62x"],
        ].map(([name, math, res], n) => (
          <div key={name} className={`grid grid-cols-[1fr_4.5rem] gap-x-4 py-1 sm:grid-cols-[1fr_auto_4.5rem] ${n ? "border-t border-rule" : ""}`}>
            <span>
              {name}
              <span className="tnum block text-blue sm:hidden">{math}</span>
            </span>
            <span className="tnum hidden text-blue sm:block">{math}</span>
            <span className="tnum text-right font-semibold">{n === 0 ? <Swipe>{res}</Swipe> : res}</span>
          </div>
        ))}
      </div>
    ),
  },
  {
    form: "DEF 14A",
    title: "Read the proxy",
    body: "The proxy text is searched for board, pay and clawback topics, with the sentence quoted as proof.",
    out: (
      <div className="flex flex-col">
        {["Lead independent director", "Clawback policy", "Anti-hedging policy", "Say-on-pay vote"].map((topic, n) => (
          <div key={topic} className={`grid grid-cols-[1fr_auto] gap-x-6 py-1 ${n ? "border-t border-rule" : ""}`}>
            <span>{topic}</span>
            <span className="text-green">{n === 0 ? <Swipe>Discussed</Swipe> : "Discussed"}</span>
          </div>
        ))}
        <p className="caption mt-2">In the live app each topic carries the sentence it was found in.</p>
      </div>
    ),
  },
  {
    form: "Gemini",
    title: "Write the memo",
    body: "AI only writes prose, from the numbers and quotes above. It never produces a figure.",
    out: (
      <div className="flex flex-col gap-2">
        <p>
          <span className="text-muted">Gemini is handed: </span>
          <span className="tnum">33.8%, 16.5%, 1.44x, 3.62x</span>
          <span className="text-muted"> and four proxy passages.</span>
        </p>
        <p>
          <span className="text-muted">It hands back: </span>
          <Swipe>prose</Swipe>
          <span className="text-muted">. It doesn&apos;t calculate or look up a single figure.</span>
        </p>
      </div>
    ),
  },
];

/** Highlighter stroke that draws once when it scrolls into view. */
function Swipe({ children }: { children: React.ReactNode }) {
  return (
    <span className="relative inline-block px-[0.15em] -mx-[0.15em]">
      <motion.span
        aria-hidden
        className="absolute inset-x-0 inset-y-[12%] origin-left bg-mark"
        initial={{ scaleX: 0 }}
        whileInView={{ scaleX: 1 }}
        viewport={{ once: true, amount: 1 }}
        transition={{ duration: 0.35, delay: 0.3, ease: [0.3, 0.7, 0.2, 1] }}
      />
      <span className="relative">{children}</span>
    </span>
  );
}

export function Pipeline() {
  const list = useRef<HTMLOListElement>(null);
  const { scrollYProgress } = useScroll({ target: list, offset: ["start 80%", "end 95%"] });
  const drawn = useSpring(scrollYProgress, { stiffness: 140, damping: 30 });
  const reduce = useReducedMotion();

  return (
    <section className="border-t border-rule">
      <div className="gutter mx-auto max-w-6xl py-16 sm:py-20">
        <div className="grid gap-4 md:grid-cols-12">
          <h2 className="text-3xl font-extrabold sm:text-4xl md:col-span-7">How a ticker becomes a report</h2>
          <p className="max-w-prose text-muted md:col-span-5 md:pt-2">
            Five steps, in the order the app runs them. On the right is what each step produced for Caterpillar&apos;s fiscal 2025 filings.
          </p>
        </div>

        <ol ref={list} className="relative mt-12">
          {/* the rule that runs down the steps, drawn as you scroll */}
          <motion.span
            aria-hidden
            className="absolute top-2 bottom-2 left-[0.65rem] w-px origin-top bg-ink"
            style={{ scaleY: reduce ? 1 : drawn }}
          />
          <span aria-hidden className="absolute top-2 bottom-2 left-[0.65rem] w-px bg-rule" style={{ zIndex: -1 }} />
          {STEPS.map((s, n) => (
            <motion.li
              key={s.title}
              className="relative grid gap-x-8 gap-y-4 pb-12 pl-12 last:pb-0 md:grid-cols-12"
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.35, ease: [0.2, 0.7, 0.2, 1] }}
            >
              <span className="absolute top-0 left-0 flex h-[1.4rem] w-[1.4rem] items-center justify-center border border-ink bg-page font-display text-sm font-semibold">
                {n + 1}
              </span>
              <div className="flex flex-col gap-1 md:col-span-5">
                <span className="caption">{s.form}</span>
                <h3 className="text-xl font-semibold">{s.title}</h3>
                <p className="max-w-prose text-muted">{s.body}</p>
              </div>
              <div className="border-l-2 border-rule pl-4 text-[15px] md:col-span-7 md:mt-6">{s.out}</div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
