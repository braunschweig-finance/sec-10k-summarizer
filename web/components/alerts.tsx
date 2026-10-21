"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import type { Report } from "@/lib/types";
import { API_URL, callApi, errorText } from "@/lib/api";

// ---------- API shapes (api/red_flags.py, api/insiders.py) ----------

type Severity = "high" | "medium" | "low";
export type RedFlag = { flag: string; severity: Severity; filed: string; form: string; item?: string; detail: string; quote: string | null; url: string };
export type RedFlags = { ticker: string; since: string; checked: string; filings_checked: number; flags: RedFlag[]; counts: Record<string, number>; high: number; medium: number };

type Total = { count: number; insiders: number; shares: number; value: number };
export type InsiderTrade = {
  accession: string; filed: string; first: string; last: string; type: "Buy" | "Sell"; shares: number; value: number;
  avg_price: number; plan: boolean; insider: string; role: string; url: string;
};
export type Insiders = {
  ticker: string; from: string; to: string; form4_count: number; capped: boolean; source: string; trades: number;
  buys: Total; sells: Total; planned_sells: Total; net_value: number;
  last_90_days: { buys: Total; sells: Total; net_value: number };
  cluster: { from: string; to: string; insiders: number; value: number } | null; signal: string;
  purchases: InsiderTrade[]; top_sales: InsiderTrade[];
};

async function get<T>(path: string, what: string): Promise<T> {
  const res = await callApi(path);
  if (!res.ok) throw new Error(await errorText(res, what));
  return res.json();
}

function useLookup<T>(ticker: string, path: string, what: string, enabled: boolean) {
  const [state, setState] = useState<{ data?: T; error?: string }>({});
  useEffect(() => {
    if (!enabled) return;
    let live = true;
    setState({});
    get<T>(`${path}/${encodeURIComponent(ticker)}`, what)
      .then((data) => live && setState({ data }))
      .catch((e) => live && setState({ error: (e as Error).message }));
    return () => {
      live = false;
    };
  }, [ticker, path, what, enabled]);
  return state;
}

// ---------- Formatting ----------

const usd = (v: number) => {
  const a = Math.abs(v);
  const s = a >= 1e9 ? `$${(a / 1e9).toFixed(2)}B` : a >= 1e6 ? `$${(a / 1e6).toFixed(1)}M` : `$${Math.round(a).toLocaleString("en-US")}`;
  return v < 0 ? `-${s}` : s;
};
const people = (k: number) => `${k} ${k === 1 ? "insider" : "insiders"}`;
const TONE: Record<Severity, string> = { high: "border-rose text-rose", medium: "border-brass text-brass", low: "border-line text-muted" };
const LABEL: Record<Severity, string> = { high: "Serious", medium: "Watch", low: "Note" };

function Box({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
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

function Waiting({ text }: { text: string }) {
  return (
    <div className="flex animate-pulse items-center gap-3 rounded-2xl border border-line bg-panel p-5 text-sm text-muted">
      <span className="h-2 w-2 rounded-full bg-violet" /> {text}
    </div>
  );
}

const Err = ({ text }: { text: string }) => <p className="rounded-xl border border-rose/30 bg-rose/10 px-4 py-3 text-sm text-rose">{text}</p>;

// ---------- Tab ----------

export function AlertsPanel({ report }: { report: Report }) {
  const on = !report.sample && !!API_URL;
  const flags = useLookup<RedFlags>(report.ticker, "/api/red-flags", "the red flags", on);
  const ins = useLookup<Insiders>(report.ticker, "/api/insiders", "the insider trades", on);
  if (!on) return <p className="text-sm text-muted">Red flags and insider trades are read from SEC filings once the API is online.</p>;
  return (
    <div className="flex flex-col gap-5">
      {flags.error ? <Err text={`Red flags: ${flags.error}`} /> : !flags.data ? <Waiting text="Checking three years of SEC filings for red flags…" /> : <FlagList r={flags.data} />}
      {ins.error ? <Err text={`Insider trades: ${ins.error}`} /> : !ins.data ? <Waiting text="Reading insiders' Form 4 filings…" /> : <InsiderCard s={ins.data} />}
    </div>
  );
}

function FlagList({ r }: { r: RedFlags }) {
  const n = r.flags.length;
  return (
    <Box title="Red flags" note={`8-K, NT 10-K and NT 10-Q filings since ${r.since}`}>
      <p className={`text-lg ${r.high ? "text-rose" : r.medium ? "text-brass" : "text-teal"}`}>
        {n === 0
          ? `No red flags: none of ${r.filings_checked.toLocaleString("en-US")} filings since ${r.since} was a restatement, auditor change, late filing, CEO or CFO exit, delisting notice, bankruptcy or cyber incident.`
          : `${n} ${n === 1 ? "flag" : "flags"} in ${r.filings_checked.toLocaleString("en-US")} filings since ${r.since}` +
            (r.high ? `, ${r.high} serious.` : ".")}
      </p>
      {n > 0 && (
        <ul className="flex flex-col gap-2">
          {r.flags.map((f, i) => (
            <motion.li
              key={`${f.url}-${f.flag}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(i, 10) * 0.04 }}
              className={`flex flex-col gap-1 rounded-xl border-l-2 bg-ink/40 px-4 py-3 text-sm ${TONE[f.severity].split(" ")[0]}`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-semibold">
                  <span className={`mr-2 font-mono text-xs uppercase ${TONE[f.severity].split(" ")[1]}`}>{LABEL[f.severity]}</span>
                  {f.flag}
                </span>
                <a href={f.url} target="_blank" rel="noreferrer" className="font-mono text-xs text-teal hover:underline">
                  {f.form} filed {f.filed} ↗
                </a>
              </div>
              <span className="leading-relaxed text-muted">{f.quote ? `"${f.quote}"` : f.detail}</span>
            </motion.li>
          ))}
        </ul>
      )}
      <p className="text-xs text-muted">
        SEC tags each 8-K with its item numbers: 4.02 non-reliance on past financials (restatement), 4.01 auditor change, 5.02 officer changes (only CEO
        and CFO departures are shown, read from the filing&apos;s text), 3.01 delisting notice, 1.03 bankruptcy, 1.05 cybersecurity incident, 2.06 impairment.
        A retirement is a note, not a warning. Checked {r.checked}.
      </p>
    </Box>
  );
}

function Stat({ label, value, sub, tone = "text-paper" }: { label: string; value: string; sub: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl border border-line bg-ink/40 p-4">
      <span className="eyebrow">{label}</span>
      <span className={`tnum font-display text-2xl font-bold ${tone}`}>{value}</span>
      <span className="text-xs text-muted">{sub}</span>
    </div>
  );
}

function TradeTable({ rows }: { rows: InsiderTrade[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead className="text-muted">
          <tr>
            {["Date", "Insider", "Shares", "Avg. price", "Value", "Form 4"].map((h, i) => (
              <th key={h} className={`px-3 py-2 font-medium ${i < 2 || i === 5 ? "text-left" : "text-right"}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((g) => (
            <tr key={`${g.accession}-${g.type}`} className="border-t border-line">
              <td className="px-3 py-2 font-mono text-xs">{g.first === g.last ? g.last : `${g.first} to ${g.last}`}</td>
              <td className="px-3 py-2">
                {g.insider} <span className="text-xs text-muted">{g.role}</span>
                {g.plan && <span className="ml-2 rounded bg-line px-1.5 py-0.5 text-xs text-muted" title="Made under a Rule 10b5-1 trading plan set up in advance">10b5-1 plan</span>}
              </td>
              <td className="tnum px-3 py-2 text-right font-mono">{Math.round(g.shares).toLocaleString("en-US")}</td>
              <td className="tnum px-3 py-2 text-right font-mono">${g.avg_price.toFixed(2)}</td>
              <td className="tnum px-3 py-2 text-right font-mono">{usd(g.value)}</td>
              <td className="px-3 py-2 font-mono text-xs">
                <a href={g.url} target="_blank" rel="noreferrer" className="text-teal hover:underline">
                  filed {g.filed} ↗
                </a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InsiderCard({ s }: { s: Insiders }) {
  const tone = s.cluster || s.net_value > 0 ? "text-teal" : s.sells.count ? "text-brass" : "text-paper";
  const r = s.last_90_days;
  return (
    <Box title="Insider buying and selling" note={`Form 4 open-market trades, ${s.from} to ${s.to}`}>
      <p className={`text-lg ${tone}`}>{s.signal}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Bought (12 mo.)" value={usd(s.buys.value)} sub={`${s.buys.count} trades by ${people(s.buys.insiders)}`} tone={s.buys.count ? "text-teal" : "text-paper"} />
        <Stat
          label="Sold (12 mo.)"
          value={usd(s.sells.value)}
          sub={`${s.sells.count} trades by ${people(s.sells.insiders)}; ${usd(s.planned_sells.value)} under 10b5-1 plans`}
          tone={s.sells.count ? "text-brass" : "text-paper"}
        />
        <Stat label="Net, last 90 days" value={usd(r.net_value)} sub={`${usd(r.buys.value)} bought, ${usd(r.sells.value)} sold`} />
      </div>
      {s.purchases.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h4 className="font-semibold">Open-market purchases</h4>
          <TradeTable rows={s.purchases} />
        </div>
      ) : (
        <p className="text-sm text-muted">No insider bought shares on the open market in this period.</p>
      )}
      {s.top_sales.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="font-semibold">Largest sales</h4>
          <TradeTable rows={s.top_sales} />
        </div>
      )}
      <p className="text-xs text-muted">
        Counts only transaction codes P (purchase) and S (sale); option exercises, grants, tax withholding and gifts are left out, and each Form 4&apos;s fills are
        added into one row. Insiders sell for many reasons (taxes, diversification), so buying is the stronger signal. Source: {s.source}
        {s.capped ? `; the ${s.form4_count} Form 4s in 12 months were more than the live limit, so this covers ${s.from} on` : ""}.
      </p>
    </Box>
  );
}
