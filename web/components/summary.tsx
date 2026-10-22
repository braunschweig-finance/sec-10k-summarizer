"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { Report, RiskItem, RiskSummary } from "@/lib/types";

const n = (v: number) => v.toLocaleString("en-US");
const plural = (k: number, one: string, many = `${one}s`) => `${n(k)} ${k === 1 ? one : many}`;

const STATUS: Record<NonNullable<RiskItem["status"]>, { label: string; cls: string }> = {
  new: { label: "New", cls: "bg-pass/15 text-pass" },
  reworded: { label: "Reworded", cls: "bg-note/15 text-note" },
  unchanged: { label: "Same as last year", cls: "bg-rule text-muted" },
};

function Stat({ label, value, tone = "text-ink" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded border border-rule bg-sheet p-4">
      <span className="eyebrow">{label}</span>
      <span className={`tnum font-display text-3xl font-bold ${tone}`}>{value}</span>
    </div>
  );
}

/** One plain-English paragraph, built only from counts of the filed headings. */
function Lead({ name, r }: { name: string; r: Extract<RiskSummary, { available: true }> }) {
  const p = r.prior;
  const wordChange = p && p.words > 0 ? ((r.words - p.words) / p.words) * 100 : null;
  return (
    <p className="max-w-3xl text-lg leading-relaxed">
      {name}&apos;s latest 10-K{r.period ? ` (fiscal year ended ${r.period})` : ""} lists{" "}
      <strong>{plural(r.count, "risk factor")}</strong>
      {p ? `, compared with ${n(p.count)} in the prior year's 10-K` : ""}.{" "}
      {r.changes && (
        <>
          <strong className="text-pass">{n(r.changes.new)}</strong> {r.changes.new === 1 ? "is" : "are"} new this year,{" "}
          <strong className="text-note">{n(r.changes.reworded)}</strong> {r.changes.reworded === 1 ? "was" : "were"} reworded, and{" "}
          <strong className="text-flag">{n(r.removed.length)}</strong> {r.removed.length === 1 ? "was" : "were"} dropped.{" "}
        </>
      )}
      The risk factors section runs {n(r.words)} words
      {wordChange !== null && ` (${wordChange >= 0 ? "+" : ""}${wordChange.toFixed(0)}% versus last year)`}.
    </p>
  );
}

function RiskList({ items, tone }: { items: string[]; tone: string }) {
  return (
    <ul className="flex flex-col gap-2">
      {items.map((t, i) => (
        <motion.li
          key={i}
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: Math.min(i, 10) * 0.04 }}
          className={`rounded-sm border-l-2 bg-page/40 px-4 py-2.5 text-sm leading-relaxed ${tone}`}
        >
          {t}
        </motion.li>
      ))}
    </ul>
  );
}

export function SummaryPanel({ report }: { report: Report }) {
  const r = report.risks;
  const [onlyChanges, setOnlyChanges] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  if (report.sample) return <p className="text-sm text-muted">The 10-K summary reads each year&apos;s risk factors from SEC once the API is online.</p>;
  if (report.risksError) return <p className="rounded-sm border-l-4 border-flag bg-sheet px-4 py-3 text-sm text-flag">10-K summary: {report.risksError}</p>;
  if (!r)
    return (
      <div className="flex animate-pulse items-center gap-3 rounded border border-rule bg-sheet p-5 text-sm text-muted">
        <span className="h-2 w-2 rounded-full bg-orig" /> Reading the risk factors in this year&apos;s and last year&apos;s 10-K…
      </div>
    );
  if (!r.available)
    return (
      <div className="flex flex-col gap-2 rounded border border-rule bg-sheet p-5 text-sm text-muted">
        <span>{r.reason}</span>
        <a href={r.tenk_url} target="_blank" rel="noreferrer" className="text-input hover:underline">
          Read the 10-K on EDGAR ↗
        </a>
      </div>
    );

  const added = r.risks.filter((x) => x.status === "new").map((x) => x.title);
  const reworded = r.risks.filter((x) => x.status === "reworded");
  const shown = onlyChanges ? r.risks.filter((x) => x.status && x.status !== "unchanged") : r.risks;
  // Group in filing order under each category heading the company used
  const groups: { category: string | null; items: { item: RiskItem; index: number }[] }[] = [];
  shown.forEach((item) => {
    const index = r.risks.indexOf(item);
    const last = groups[groups.length - 1];
    if (last && last.category === item.category) last.items.push({ item, index });
    else groups.push({ category: item.category, items: [{ item, index }] });
  });

  return (
    <div className="flex flex-col gap-6">
      <Lead name={report.name} r={r} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Risk factors" value={n(r.count)} />
        <Stat label="New this year" value={r.changes ? n(r.changes.new) : "N/A"} tone="text-pass" />
        <Stat label="Reworded" value={r.changes ? n(r.changes.reworded) : "N/A"} tone="text-note" />
        <Stat label="Dropped" value={r.changes ? n(r.removed.length) : "N/A"} tone="text-flag" />
      </div>

      {r.changes && (
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="flex flex-col gap-3 rounded border border-rule bg-sheet p-5">
            <h3 className="text-lg font-bold">New this year</h3>
            {added.length ? <RiskList items={added} tone="border-pass" /> : <p className="text-sm text-muted">No new risk factor headings.</p>}
          </div>
          <div className="flex flex-col gap-3 rounded border border-rule bg-sheet p-5">
            <h3 className="text-lg font-bold">Dropped since last year</h3>
            {r.removed.length ? (
              <RiskList items={r.removed} tone="border-flag" />
            ) : (
              <p className="text-sm text-muted">Every heading from last year&apos;s 10-K is still there.</p>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h3 className="text-xl font-bold">Every risk factor, in the company&apos;s words</h3>
          {r.changes && (
            <label className="flex cursor-pointer items-center gap-2 text-sm text-muted">
              <input type="checkbox" checked={onlyChanges} onChange={(e) => setOnlyChanges(e.target.checked)} className="accent-[var(--color-input)]" />
              Only new and reworded
            </label>
          )}
        </div>
        <div className="flex flex-col gap-5 rounded border border-rule p-5">
          {groups.map((g, gi) => (
            <div key={gi} className="flex flex-col gap-2">
              {g.category && <span className="eyebrow">{g.category}</span>}
              <ol className="flex flex-col gap-1.5">
                {g.items.map(({ item, index }) => {
                  const st = item.status ? STATUS[item.status] : null;
                  return (
                    <li key={index} className="flex flex-col gap-1">
                      <div className="flex items-start gap-3 text-sm leading-relaxed">
                        <span className="tnum w-7 shrink-0 pt-0.5 text-right figures text-xs text-muted">{index + 1}.</span>
                        <span className="flex-1">{item.title}</span>
                        {st && (
                          <button
                            type="button"
                            disabled={item.status !== "reworded"}
                            onClick={() => setOpen(open === index ? null : index)}
                            className={`shrink-0 rounded-sm px-2 py-0.5 figures text-[10px] whitespace-nowrap ${st.cls} ${item.status === "reworded" ? "cursor-pointer hover:opacity-80" : "cursor-default"}`}
                            aria-expanded={item.status === "reworded" ? open === index : undefined}
                          >
                            {st.label}
                            {item.status === "reworded" && (open === index ? " ▴" : " ▾")}
                          </button>
                        )}
                      </div>
                      <AnimatePresence initial={false}>
                        {open === index && item.prior_title && (
                          <motion.p
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            className="ml-10 overflow-hidden border-l-2 border-input/50 pl-3 text-xs leading-relaxed text-muted"
                          >
                            Last year: {item.prior_title}
                          </motion.p>
                        )}
                      </AnimatePresence>
                    </li>
                  );
                })}
              </ol>
            </div>
          ))}
          {!shown.length && <p className="text-sm text-muted">No new or reworded headings this year.</p>}
        </div>
      </div>

      <p className="text-xs leading-relaxed text-muted">
        Read from Item 1A (Risk Factors) of the{" "}
        <a href={r.tenk_url} target="_blank" rel="noreferrer" className="text-input hover:underline">
          10-K filed {r.tenk_date} ↗
        </a>
        {r.prior && (
          <>
            {" "}
            and the{" "}
            <a href={r.prior.tenk_url} target="_blank" rel="noreferrer" className="text-input hover:underline">
              10-K filed {r.prior.tenk_date} ↗
            </a>
          </>
        )}
        . Each line is a bold or italic risk heading exactly as the company wrote it; no AI is used. Headings at least 98% the same as last
        year&apos;s count as the same, 75 to 98% as reworded{reworded.length ? " (click the tag to see last year's wording)" : ""}, and anything
        else as new or dropped.
      </p>
    </div>
  );
}
