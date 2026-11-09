"use client";

import {useEffect, useRef, useState, type ReactNode} from "react";
import {saveBlob} from "@/lib/api";
import {comparisonCsv} from "@/lib/comparisonCsv";
import type {ScreenerRow} from "@/lib/screener";
import {fieldReasons} from "@/lib/screenerContext";
import {canCompare} from "@/lib/screenerSelection";
import ScreenerDataNotes from "./ScreenerDataNotes";

export default function ScreenerComparison({rows,builtAt,onClose}: {
  rows:readonly ScreenerRow[]; builtAt:string|null; onClose:()=>void;
}) {
  const heading=useRef<HTMLHeadingElement>(null);
  const [exportError,setExportError]=useState("");
  const downloadCsv=()=>{
    setExportError("");
    try {
      saveBlob(new Blob([comparisonCsv(rows,builtAt)],{type:"text/csv;charset=utf-8"}),"SEC_company_comparison.csv");
    } catch {
      setExportError("Could not prepare the CSV. Check the selected companies and try again.");
    }
  };
  useEffect(()=>{heading.current?.focus();},[]);
  const pct=(value:number|null)=>value===null ? "N/A" : `${value.toFixed(2)}%`;
  const metrics: {label:string; render:(row:ScreenerRow)=>ReactNode}[]=[
    {label:"Sector",render:r=>r.sector??"N/A"},
    {label:"Fiscal year end",render:r=>r.fy_end??"N/A"},
    {label:"Pay Efficiency %",render:r=>pct(r.pay_efficiency_pct)},
    {label:"Company Grade / score",render:r=>r.grade===null ? "N/A" : `${r.grade} / ${r.grade_score===null?"N/A":r.grade_score.toFixed(0)}`},
    {label:"Upside vs peers %",render:r=><>{pct(r.upside_pct)}{r.valuation_confidence==="low"&&<p className="mt-1 text-brass">Low confidence — not a reliable investment signal.</p>}</>},
    {label:"Cached price date",render:r=>r.price_date??"N/A"},
    {label:"Sources and data notes",render:r=><>
      <div className="flex flex-wrap gap-3">
        {r.sources.financials_url&&<a className="text-teal underline" href={r.sources.financials_url} target="_blank" rel="noreferrer">10-K</a>}
        {r.sources.proxy_url&&<a className="text-teal underline" href={r.sources.proxy_url} target="_blank" rel="noreferrer">14A</a>}
      </div>
      {!r.sources.financials_url&&!r.sources.proxy_url&&<p>Filing links unavailable in this snapshot.</p>}
      <p className="mt-2 text-xs text-muted">Valuation source: {r.sources.valuation_source??"Unavailable in the snapshot."}</p>
      <ScreenerDataNotes row={r}/>
    </>},
  ];
  const caveatField:Record<string,string>={"Pay Efficiency %":"pay_efficiency_pct","Company Grade / score":"grade","Upside vs peers %":"upside_pct"};
  return <section aria-labelledby="screener-comparison-title" className="min-w-0 rounded-2xl border border-brass/40 bg-panel p-4 sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="screener-comparison-title" ref={heading} tabIndex={-1} className="text-2xl font-bold">Side-by-side comparison</h2>
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={!canCompare(rows)} onClick={downloadCsv} className="min-h-11 rounded-xl border border-brass px-4 text-brass hover:bg-brass/10 disabled:opacity-40">Download CSV</button>
        <button type="button" onClick={onClose} className="min-h-11 rounded-xl border border-line px-4 hover:border-brass">Close comparison</button>
      </div>
    </div>
    {exportError&&<p role="alert" className="mt-2 text-sm text-rose">{exportError}</p>}
    {!canCompare(rows)?<p>Select 2–4 distinct companies to compare.</p>:<>
      <p className="mt-3 text-sm text-muted">Selected from snapshot {builtAt??"with unknown build date"}. Fiscal periods and cached price dates can differ. Sector differences affect comparability; these are descriptive metrics, not a ranking or investment recommendation. Missing values are not zero.</p>
      <p id="comparison-scroll-help" className="mt-2 text-xs text-muted">Scroll sideways to see every company. Keyboard: focus the comparison table and use the left and right arrow keys.</p>
      <div role="region" aria-label="Selected company comparison" aria-describedby="comparison-scroll-help" tabIndex={0} className="mt-3 max-w-full overflow-x-auto rounded-xl border border-line focus-visible:outline-2 focus-visible:outline-brass">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead><tr><th scope="col" className="p-3">Metric</th>{rows.map(r=><th scope="col" key={r.ticker} className="min-w-52 p-3 align-top"><a className="text-brass underline" href={`/?ticker=${encodeURIComponent(r.ticker)}`}>{r.ticker}</a><p className="mt-1 font-normal">{r.name??r.ticker}</p></th>)}</tr></thead>
          <tbody>{metrics.map(metric=><tr key={metric.label} className="border-t border-line">
            <th scope="row" className="p-3 align-top font-medium">{metric.label}</th>
            {rows.map(r=><td key={r.ticker} className="max-w-80 p-3 align-top [overflow-wrap:anywhere]">
              {metric.render(r)}
              {caveatField[metric.label]&&fieldReasons(r.missing,caveatField[metric.label]).map(reason=><p key={reason} className="mt-2 text-xs leading-relaxed text-muted">{reason}</p>)}
            </td>)}
          </tr>)}</tbody>
        </table>
      </div>
    </>}
  </section>;
}
