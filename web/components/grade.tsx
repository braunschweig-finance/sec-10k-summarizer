"use client";

import { useEffect, useState } from "react";
import type { Grade, GradeComponent, Report } from "@/lib/types";
import { fetchGrade } from "@/lib/api";

// One overall grade from governance, red flags, insider trading and value vs peers (api/grade.py). Plain on purpose:
// the letter, each part's score and the numbers behind it.

const cache = new Map<string, Grade>();
const pct = (n: number | null | undefined, d = 1) => (n === null || n === undefined ? "N/A" : `${n.toFixed(d)}%`);
const usdM = (n: number | null | undefined) => (n === null || n === undefined ? "N/A" : `$${(n / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 })}M`);

const LETTER_STYLE: Record<string, string> = {
  A: "border-pass/50 text-pass",
  B: "border-pass/30 text-pass",
  C: "border-rule text-ink",
  D: "border-flag/30 text-flag",
  F: "border-flag/50 text-flag",
};

export function GradePanel({ report }: { report: Report }) {
  const [data, setData] = useState<Grade | null>(cache.get(report.ticker) ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cache.has(report.ticker) || report.sample) return;
    let live = true;
    fetchGrade(report.ticker)
      .then((g) => {
        cache.set(report.ticker, g);
        if (live) setData(g);
      })
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [report.ticker, report.sample]);

  if (report.sample) return <p className="text-sm text-muted">The overall grade turns on once the API is online.</p>;
  if (error) return <p className="rounded-sm border-l-4 border-flag bg-sheet px-4 py-3 text-sm text-flag">Grade: {error}</p>;
  if (!data)
    return (
      <div className="flex animate-pulse items-center gap-3 rounded border border-rule bg-sheet p-5 text-sm text-muted">
        <span className="h-2 w-2 rounded-full bg-orig" /> Reading governance, red flags, insider trades and peer value… (a first look at a company can take a minute)
      </div>
    );

  return (
    <div className="flex flex-col gap-5">
      <div className="grid gap-5 rounded border border-rule bg-sheet p-5 md:grid-cols-[auto_1fr]">
        {data.available ? (
          <div className={`flex h-28 w-28 flex-col items-center justify-center rounded border-2 ${LETTER_STYLE[data.letter!]}`}>
            <span className="figures text-5xl font-bold">{data.letter}</span>
            <span className="tnum figures text-xs text-muted">{data.score!.toFixed(0)} / 100</span>
          </div>
        ) : (
          <p className="text-sm text-muted">{data.reason}</p>
        )}
        <div className="flex flex-col gap-2">
          <h3 className="text-lg font-bold">Overall grade for {data.name}</h3>
          <p className="text-sm text-muted">
            Four things read from SEC filings, each scored 0-100 with 50 as typical: governance (35%), red flags (35%), insider trading (15%) and
            value vs peers (15%). A: 80+, B: 65+, C: 50+, D: 35+, F: below.
          </p>
          <p className="text-xs text-note">{data.disclaimer}</p>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {data.components.map((c) => <Part key={c.part} c={c} />)}
      </div>

      {data.missing.length > 0 && (
        <div className="rounded border border-rule bg-sheet p-5 text-sm text-muted">
          <p className="mb-2 font-medium text-ink">Left out (the other parts&apos; weights were scaled up):</p>
          <ul className="list-disc pl-5">
            {data.missing.map((m) => <li key={m.part}>{m.name}: {m.why}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function Part({ c }: { c: GradeComponent }) {
  const d = c.details;
  return (
    <div className="flex flex-col gap-3 rounded border border-rule bg-sheet p-5">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-lg font-bold">{c.name}</h3>
        <span className="eyebrow">weight {c.used_weight.toFixed(0)}%</span>
      </div>
      <div className="flex items-baseline gap-3">
        <span className={`figures text-3xl font-bold ${LETTER_STYLE[c.letter].split(" ").pop()}`}>{c.letter}</span>
        <span className="tnum figures text-muted">{c.score.toFixed(0)} / 100</span>
      </div>
      {c.part === "governance" && (
        <table className="w-full text-sm">
          <thead className="text-muted">
            <tr>
              {["Number", "Company", "Sector median", "Score"].map((h, i) => (
                <th key={h} className={`py-1 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {d.items.map((i: any) => (
              <tr key={i.metric} className="border-t border-rule" title={i.note || undefined}>
                <td className="py-1.5">{i.metric}{i.lower_is_better ? <span className="text-xs text-muted"> (lower is better)</span> : null}</td>
                <td className="tnum py-1.5 text-right figures">{fmtGov(i.metric, i.value)}</td>
                <td className="tnum py-1.5 text-right figures text-muted">{fmtGov(i.metric, i.sector_median)}</td>
                <td className="tnum py-1.5 text-right figures">{i.score.toFixed(0)}{i.note ? " *" : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {c.part === "governance" && <p className="text-xs text-muted">Sector: Russell 1000 {d.group ?? "companies"}. Score 25 = sector 25th percentile, 50 = median, 75 = 75th.</p>}
      {c.part === "governance" && d.items.some((i: any) => i.note) && (
        <p className="text-xs text-flag">* Say-on-pay {d.items.find((i: any) => i.note).note}, so it scores at most 20.</p>
      )}
      {c.part === "red_flags" && (
        <div className="text-sm">
          <p className="text-muted">
            Since {d.since}: {d.high} high, {d.medium} medium and {d.low} low flags (−35, −12 and −4 points each).
          </p>
          <ul className="mt-2 flex flex-col gap-1">
            {d.flags.slice(0, 8).map((f: any, i: number) => (
              <li key={i} className="flex justify-between gap-3 border-t border-rule pt-1">
                <span>{f.flag} <span className="text-xs text-muted">({f.severity})</span></span>
                <a href={f.url} target="_blank" rel="noreferrer" className="figures text-xs text-input hover:underline">{f.form} {f.filed} ↗</a>
              </li>
            ))}
          </ul>
          {d.flags.length > 8 && <p className="mt-1 text-xs text-muted">…and {d.flags.length - 8} more on the Red Flags tab.</p>}
        </div>
      )}
      {c.part === "insiders" && (
        <div className="text-sm text-muted">
          <p className="text-ink">Why: {d.why}.</p>
          <p>
            {d.from} to {d.to}: bought {usdM(d.buys_value)}, sold {usdM(d.sells_value)} (of which {usdM(d.planned_sells_value)} under 10b5-1 plans).
            {d.net_unplanned_pct_of_market_cap !== null ? ` Net outside plans: ${pct(d.net_unplanned_pct_of_market_cap, 3)} of market value.` : ""}
          </p>
          <p className="text-xs">From SEC Form 4 filings, open-market trades only.</p>
        </div>
      )}
      {c.part === "valuation" && (
        <p className="text-sm text-muted">
          Fair value ${d.fair_value.toFixed(2)} vs price ${d.price.toFixed(2)}: {d.upside_pct >= 0 ? "+" : ""}
          {d.upside_pct.toFixed(1)}% ({d.verdict}). Details and the back-test are on the Fair Value tab.
        </p>
      )}
    </div>
  );
}

function fmtGov(metric: string, v: number | null) {
  if (v === null || v === undefined) return "N/A";
  if (metric === "CEO Pay Ratio") return `${Math.round(v).toLocaleString("en-US")}:1`;
  if (metric === "Pay Efficiency") return `${v.toFixed(2)}%`;
  return `${v.toFixed(1)}%`;
}
