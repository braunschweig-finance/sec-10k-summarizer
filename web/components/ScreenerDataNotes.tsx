import type { ScreenerRow } from "@/lib/screener";
import { fieldReasons } from "@/lib/screenerContext";

export default function ScreenerDataNotes({ row }: { row: ScreenerRow }) {
  const fields = [
    ["sector", "Sector", row.sector],
    ["fy_end", "Fiscal year end", row.fy_end],
    ["pay_efficiency_pct", "Pay Efficiency", row.pay_efficiency_pct],
    ["grade", "Company Grade", row.grade],
    ["grade_score", "Grade score", row.grade_score],
    ["upside_pct", "Upside vs peers", row.upside_pct],
    ["price_date", "Cached price date", row.price_date],
    ["valuation_confidence", "Valuation confidence", row.valuation_confidence],
  ] as const;

  return (
    <details className="mt-1 min-w-36 max-w-72 text-xs">
      <summary
        aria-label={`${row.ticker} Data notes`}
        className="min-h-11 cursor-pointer content-center rounded text-paper focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass"
      >
        Data notes
      </summary>
      <div className="space-y-2 pb-2 leading-relaxed text-muted [overflow-wrap:anywhere]">
        <p>Missing values are absent, not zero. Coverage counts do not describe the completeness of this company’s grade.</p>
        <dl className="space-y-2">
          {fields.map(([field, label, value]) => {
            const reasons = fieldReasons(row.missing, field);
            if (value !== null && reasons.length === 0 && field !== "fy_end" && field !== "price_date") return null;
            return (
              <div key={field}>
                <dt className="font-medium text-paper">{label}</dt>
                <dd>
                  {value === null ? "N/A — " : field === "fy_end" || field === "price_date" ? `${value}. ` : "Caveat: "}
                  {reasons.length ? reasons.join(" · ") : value === null ? "No value in the snapshot; no field-specific reason supplied." : ""}
                </dd>
              </div>
            );
          })}
        </dl>
        <p>Fiscal year end identifies the financial reporting period. The snapshot build date records assembly of the cache; rebuilding it does not update cached quotes.</p>
        <p>Pay Efficiency is CEO compensation actually paid ÷ operating income. It stays signed: negative compensation actually paid can produce a negative value, which does not mean better efficiency.</p>
        <p>Valuation source: {row.sources.valuation_source || "Unavailable in the snapshot."}</p>
        {row.valuation_confidence === "low" && <p className="text-brass">Low-confidence valuation estimate — not a reliable investment signal.</p>}
      </div>
    </details>
  );
}
