"use client";

import { useEffect, useState } from "react";
import type { Backtest, Report, Valuation, ValuationMethod } from "@/lib/types";
import { fetchValuation } from "@/lib/api";

// Fair value from comparable companies. Kept plain on purpose: one verdict, the numbers behind it, and how the method
// has done in the past.

const usd = (n: number | null | undefined, d = 2) => (n === null || n === undefined ? "N/A" : `$${n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })}`);
const usdM = (n: number | null | undefined) => (n === null || n === undefined ? "N/A" : `$${Math.round(n / 1e6).toLocaleString("en-US")}M`);
const mult = (n: number | null | undefined) => (n === null || n === undefined ? "–" : `${n.toFixed(1)}x`);
const pct = (n: number | null | undefined, d = 1) => (n === null || n === undefined ? "N/A" : `${(n * 100).toFixed(d)}%`);
const signed = (n: number | null | undefined, d = 1) => (n === null || n === undefined ? "N/A" : `${n >= 0 ? "+" : ""}${(n * 100).toFixed(d)}%`);

const cache = new Map<string, Valuation>();

const VERDICT_STYLE: Record<string, string> = {
  undervalued: "border-teal/40 bg-teal/10 text-teal",
  "fairly valued": "border-line bg-panel text-paper",
  overvalued: "border-rose/40 bg-rose/10 text-rose",
};

export function FairValuePanel({ report }: { report: Report }) {
  const [data, setData] = useState<Valuation | null>(cache.get(report.ticker) ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cache.has(report.ticker) || report.sample) return;
    let live = true;
    fetchValuation(report.ticker)
      .then((v) => {
        cache.set(report.ticker, v);
        if (live) setData(v);
      })
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [report.ticker, report.sample]);

  if (report.sample) return <p className="text-sm text-muted">The fair value estimate compares live prices across the Russell 1000, so it turns on once the API is online.</p>;
  if (error) return <p className="rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose">Fair value: {error}</p>;
  if (!data)
    return (
      <div className="flex animate-pulse items-center gap-3 rounded-2xl border border-line bg-panel p-5 text-sm text-muted">
        <span className="h-2 w-2 rounded-full bg-violet" /> Finding the closest peers and pricing the company like them…
      </div>
    );
  if (!data.available)
    return (
      <div className="flex flex-col gap-5">
        <p className="rounded-xl border border-line bg-panel px-4 py-3 text-sm text-muted">{data.reason}</p>
        {data.backtest && <BacktestCard bt={data.backtest} />}
      </div>
    );

  const c = data.company!;
  return (
    <div className="flex flex-col gap-5">
      <p className="max-w-3xl text-sm text-muted">
        What would {data.name} be worth if the market priced it like the companies most similar to it? Two identical houses should sell for about
        the same price. Here the peers are the 8 Russell 1000 companies in its sector ({c.sector ?? "whole index"}) closest in size, revenue
        growth, margins and leverage, and their valuation multiples are applied to {data.ticker}&apos;s own FY{c.fiscal_year} 10-K figures.
      </p>

      <Headline v={data} />
      {data.confidence_note && <p className="rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose">{data.confidence_note}</p>}
      {data.notes?.map((n) => (
        <p key={n} className="rounded-xl border border-brass/30 bg-brass/10 px-4 py-3 text-sm text-brass">{n}</p>
      ))}

      <Section title="How the value is built" note="median of the methods used">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-muted">
              <tr>
                {["Multiple", `${data.ticker} today`, "Peer median (25th–75th)", `${data.ticker} figure`, "Value per share (range)"].map((h, i) => (
                  <th key={h} className={`px-3 py-2 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.methods!.map((m) => <MethodRow key={m.method} m={m} />)}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted">
          EV (enterprise value) = market value of shares + debt − cash and short-term investments. EV multiples are turned back into a share price by
          subtracting {data.ticker}&apos;s debt ({usdM(c.debt)}) and adding its cash ({usdM(c.cash)}), then dividing by {(c.shares / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 })}M
          diluted shares. Financials and Real Estate use P/E and P/B only, since their debt is part of the business.
        </p>
      </Section>

      <Section title="The peers" note="closest first">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="text-muted">
              <tr>
                {["Company", "SEC industry", "Revenue", "Growth", "Margin", "Liab./assets", "EV/EBITDA", "EV/EBIT", "EV/Sales", "P/E", "P/B", "Distance"].map((h, i) => (
                  <th key={h} className={`px-3 py-2 font-medium ${i < 2 ? "text-left" : "text-right"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-line bg-brass/5">
                <td className="px-3 py-2 font-mono text-brass">{data.ticker}</td>
                <td className="px-3 py-2 text-xs text-muted">SIC {c.sic}</td>
                <FeatureCells f={c.features} revenue={c.figures.Revenue} />
                {["EV/EBITDA", "EV/EBIT", "EV/Sales", "P/E", "P/B"].map((k) => (
                  <td key={k} className="tnum px-3 py-2 text-right font-mono text-brass">{mult(c.multiples[k])}</td>
                ))}
                <td className="px-3 py-2 text-right text-xs text-muted">–</td>
              </tr>
              {data.peers!.map((p) => (
                <tr key={p.ticker} className="border-t border-line hover:bg-panel/70">
                  <td className="px-3 py-2">
                    <span className="font-mono">{p.ticker}</span> <span className="text-xs text-muted">{p.name}</span>
                  </td>
                  <td className="px-3 py-2 text-xs text-muted">
                    SIC {p.sic}
                    {p.sic === c.sic ? " (same)" : ""}
                  </td>
                  <FeatureCells f={p.features} revenue={p.figures.Revenue} />
                  {["EV/EBITDA", "EV/EBIT", "EV/Sales", "P/E", "P/B"].map((k) => (
                    <td key={k} className="tnum px-3 py-2 text-right font-mono">{mult(p.multiples[k])}</td>
                  ))}
                  <td className="tnum px-3 py-2 text-right font-mono text-muted">{p.distance.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted">
          Distance adds up how far each peer is on size, growth, margin and leverage (in units of the sector&apos;s spread), plus 0.5 for a different
          4-digit SEC industry code, 1.0 for a different 3-digit one and 1.5 for a different 2-digit one. Margin is operating margin (net margin for
          Financials and Real Estate). Peer prices are closes from the weekly data build ({data.peers_built_at?.slice(0, 10) ?? "N/A"}).
        </p>
      </Section>

      <Sources v={data} />
      {data.backtest && <BacktestCard bt={data.backtest} />}
    </div>
  );
}

function Headline({ v }: { v: Valuation }) {
  const lo = Math.min(v.low!, v.price!) * 0.85;
  const hi = Math.max(v.high!, v.price!) * 1.15;
  const at = (x: number) => `${((x - lo) / (hi - lo)) * 100}%`;
  return (
    <div className="grid gap-5 rounded-2xl border border-line bg-panel p-5 md:grid-cols-[1fr_1.4fr]">
      <div className="flex flex-col gap-3">
        <span className={`w-fit rounded-full border px-3 py-1 font-mono text-xs uppercase tracking-wider ${VERDICT_STYLE[v.verdict!]}`}>
          {v.verdict === "fairly valued" ? "Fairly valued vs peers" : `${v.verdict === "undervalued" ? "Undervalued" : "Overvalued"} vs peers`}
        </span>
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <div>
            <div className="eyebrow">Fair value</div>
            <div className="tnum font-mono text-4xl font-bold text-brass">{usd(v.fair_value)}</div>
            <div className="tnum font-mono text-xs text-muted">range {usd(v.low)} – {usd(v.high)}</div>
          </div>
          <div>
            <div className="eyebrow">Price</div>
            <div className="tnum font-mono text-2xl">{usd(v.price)}</div>
            <div className="font-mono text-xs text-muted">{v.company!.price_date}</div>
          </div>
          <div>
            <div className="eyebrow">Gap</div>
            <div className={`tnum font-mono text-2xl ${v.upside_pct! >= 0 ? "text-teal" : "text-rose"}`}>
              {v.upside_pct! >= 0 ? "+" : ""}
              {v.upside_pct!.toFixed(1)}%
            </div>
            <div className="text-xs text-muted">fair value vs price</div>
          </div>
        </div>
      </div>
      <div className="flex flex-col justify-center gap-2">
        <div className="relative h-10" aria-label={`Fair value range ${usd(v.low)} to ${usd(v.high)}, price ${usd(v.price)}`}>
          <div className="absolute top-4 h-2 w-full rounded-full bg-line" />
          <div className="absolute top-4 h-2 rounded-full bg-brass/50" style={{ left: at(v.low!), width: `calc(${at(v.high!)} - ${at(v.low!)})` }} />
          <div className="absolute top-2 h-6 w-0.5 bg-brass" style={{ left: at(v.fair_value!) }} />
          <div className="absolute top-1 h-8 w-1 -translate-x-1/2 rounded bg-paper" style={{ left: at(v.price!) }} />
        </div>
        <div className="flex flex-wrap gap-4 text-xs text-muted">
          <span className="flex items-center gap-2"><span className="h-2 w-4 rounded bg-brass/50" /> peer range</span>
          <span className="flex items-center gap-2"><span className="h-3 w-0.5 bg-brass" /> fair value</span>
          <span className="flex items-center gap-2"><span className="h-3 w-1 rounded bg-paper" /> price</span>
        </div>
        <p className="text-xs text-muted">{v.price_note}</p>
      </div>
    </div>
  );
}

function MethodRow({ m }: { m: ValuationMethod }) {
  if (!m.used)
    return (
      <tr className="border-t border-line text-muted">
        <td className="px-3 py-2 font-mono">{m.method}</td>
        <td className="tnum px-3 py-2 text-right font-mono">{mult(m.company_multiple)}</td>
        <td colSpan={3} className="px-3 py-2 text-right text-xs">Not used: {m.why_not}</td>
      </tr>
    );
  return (
    <tr className="border-t border-line">
      <td className="px-3 py-2 font-mono">{m.method}</td>
      <td className="tnum px-3 py-2 text-right font-mono">{mult(m.company_multiple)}</td>
      <td className="tnum px-3 py-2 text-right font-mono">
        {mult(m.peer_median)} <span className="text-muted">({mult(m.peer_p25)}–{mult(m.peer_p75)}, {m.peer_count} peers)</span>
      </td>
      <td className="tnum px-3 py-2 text-right font-mono">
        {usdM(m.company_figure)} <span className="text-xs text-muted">{m.figure}</span>
      </td>
      <td className="tnum px-3 py-2 text-right font-mono">
        <span className="text-brass">{usd(m.value)}</span> <span className="text-muted">({usd(m.low)}–{usd(m.high)})</span>
      </td>
    </tr>
  );
}

function FeatureCells({ f, revenue }: { f: { growth: number | null; margin: number | null; leverage: number | null }; revenue: number | null }) {
  return (
    <>
      <td className="tnum px-3 py-2 text-right font-mono">{usdM(revenue)}</td>
      <td className="tnum px-3 py-2 text-right font-mono">{signed(f.growth)}</td>
      <td className="tnum px-3 py-2 text-right font-mono">{pct(f.margin)}</td>
      <td className="tnum px-3 py-2 text-right font-mono">{f.leverage === null ? "N/A" : f.leverage.toFixed(2)}</td>
    </>
  );
}

function Sources({ v }: { v: Valuation }) {
  const c = v.company!;
  const rows = Object.entries(v.sources ?? {});
  return (
    <Section title="Where every number comes from" note={`FY${c.fiscal_year} 10-K, filed ${c.filed}`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-muted">
            <tr>
              {["Input", "Value", "Filing"].map((h, i) => (
                <th key={h} className={`px-3 py-2 font-medium ${i === 1 ? "text-right" : "text-left"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, s]) => (
              <tr key={name} className="border-t border-line">
                <td className="px-3 py-2" title={s.concept}>{name}</td>
                <td className="tnum px-3 py-2 text-right font-mono">
                  {name === "Diluted EPS" ? usd(s.value) : name === "Diluted Shares" ? `${(s.value / 1e6).toLocaleString("en-US", { maximumFractionDigits: 1 })}M` : usdM(s.value)}
                </td>
                <td className="px-3 py-2 font-mono text-xs">
                  <a href={s.url} target="_blank" rel="noreferrer" className="text-teal hover:underline">{s.accn} ↗</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        Hover an input to see its XBRL tag. Debt used: {c.debt_parts.filter((p) => !["Cash", "Short-term Investments"].includes(p)).join(" + ") || "none tagged"}.
        Shares: {c.shares_source}. {v.source}
      </p>
    </Section>
  );
}

function BacktestCard({ bt }: { bt: Backtest }) {
  const a = bt.average;
  if (!bt.years) return null;
  const q = a.quintile_returns;
  return (
    <Section title="Has this worked before?" note={`back-test · ${bt.years} years`}>
      <p className="text-sm text-muted">{bt.method}</p>
      <div className="grid gap-3 sm:grid-cols-5">
        {q.map((r, i) => (
          <div key={i} className={`rounded-xl border p-3 ${i === 0 ? "border-teal/40" : i === 4 ? "border-rose/40" : "border-line"}`}>
            <div className="eyebrow">{i === 0 ? "Most undervalued" : i === 4 ? "Most overvalued" : `Group ${i + 1}`}</div>
            <div className="tnum font-mono text-xl">{pct(r)}</div>
            <div className="text-xs text-muted">avg. next-12-month return</div>
          </div>
        ))}
      </div>
      <p className="text-sm">
        Most undervalued minus most overvalued: <span className="tnum font-mono text-brass">{signed(a.spread)}</span> a year on average, positive in{" "}
        {a.spread_positive_years} of {bt.years} years (t = {a.spread_t?.toFixed(2) ?? "N/A"}). Rank correlation between the gap and the next year&apos;s
        return: <span className="tnum font-mono">{a.rank_correlation?.toFixed(3) ?? "N/A"}</span> (t = {a.rank_correlation_t?.toFixed(2) ?? "N/A"}).{" "}
        Using each group&apos;s median return instead (so one stock that tripled can&apos;t drive it), the difference is{" "}
        <span className="tnum font-mono">{signed(a.median_spread)}</span>, positive in {a.median_spread_positive_years} of {bt.years} years.{" "}
        {a.spread_t !== null && Math.abs(a.spread_t) < 2
          ? "With a t-value under 2, this difference could easily be chance."
          : "A t-value above 2 is the usual bar for a result that's unlikely to be chance."}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-muted">
            <tr>
              {["Formed", "Companies", "All", "Most undervalued", "Most overvalued", "Difference", "Rank corr."].map((h, i) => (
                <th key={h} className={`px-3 py-2 font-medium ${i ? "text-right" : "text-left"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {bt.cohorts.map((c) => (
              <tr key={c.formed} className="border-t border-line">
                <td className="px-3 py-2 font-mono text-xs">{c.formed}</td>
                <td className="tnum px-3 py-2 text-right font-mono">{c.companies}</td>
                <td className="tnum px-3 py-2 text-right font-mono">{pct(c.all_return)}</td>
                <td className="tnum px-3 py-2 text-right font-mono">{pct(c.quintile_returns[0])}</td>
                <td className="tnum px-3 py-2 text-right font-mono">{pct(c.quintile_returns[4])}</td>
                <td className={`tnum px-3 py-2 text-right font-mono ${c.spread >= 0 ? "text-teal" : "text-rose"}`}>{signed(c.spread)}</td>
                <td className="tnum px-3 py-2 text-right font-mono text-muted">{c.rank_correlation?.toFixed(3) ?? "N/A"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="list-disc pl-5 text-xs text-muted">
        {bt.caveats.map((c) => <li key={c}>{c}</li>)}
      </ul>
    </Section>
  );
}

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
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
