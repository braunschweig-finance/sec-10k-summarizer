# Screener data context: preimplementation independent audit

## Final integration evidence — November 9, 2026

Production build/TypeScript and 38 tests passed (12 context-helper, 13 URL, 13 Terminal). Independent final code review approved the scoped changes. Browser checks with real AGNC and AAON records verified a 14-day snapshot age, distinct fiscal/price dates, metric-specific N/A reasons, signed-pay explanations, debt and low-confidence caveats, readable valuation provenance and supplied filing links. Native Data notes opened with Enter and pointer input; at 390px the summary measured 44px high and page width stayed within the viewport. URL-driven search remained functional. The checklist below records original risk analysis, not additional runtime claims.

Scope: static inspection only; acceptance cases below are requirements, not execution results or approval.
Rules read: canonical `../sec-10k-summarizer/AGENTS.md`; no historical logs.
Evidence: `api/screener.py` (`_row`, `_unavailable_row`, `_snapshot`, `screen`),
`api/grade.py` (`build`), `web/lib/screener.ts`, `web/components/Screener.tsx`,
`docs/SCREENER_CONTRACT.md`, and the two `api/tests/test_screener_*` files.

## Actual cached projection and limitations

- Row keys: ticker, name, sector, fy_end, pay_efficiency_pct, grade, grade_score,
  upside_pct, price_date, valuation_confidence, sources, missing.
- `sources` contains nullable financials_url/proxy_url links and valuation_source text.
- `missing` is a string array: `field: reason`, `grade.part: reason`, or
  `sources.key: reason`; it also contains caveats for present values, not just missing data.
- Malformed-row fallback makes every field except ticker/sources/missing null, including name;
  the client currently declares name as nonnullable, so its type understates the wire schema.
- Snapshot built_at is manifest metadata; fy_end prefers valuation target, then fundamentals,
  then pay data. price_date belongs to the cached price. These are three distinct clocks.
- There is no per-metric fiscal date, filing date, grade component coverage/weights,
  XBRL concept/accession, or per-component source map in this projection.
- Coverage counts nonnull metrics across the entire snapshot, not filtered rows or grade completeness.

## Specific risks and acceptance cases

- Dates: `fmtDate` uses local formatting and permissive Date parsing; date-only values can shift
  a day and invalid components can normalize. Label build time, fiscal period and price date
  separately; never present snapshot age as filing age or cached price as live.
- Accept: absent/invalid/future dates show unknown age, never zero or a negative age;
  legitimate today shows 0 days. No age threshold or freshness assurance is supplied by this schema.
- N/A: `missingNote` joins every reason into each null metric's title, leaking unrelated causes.
  Accept: null remains N/A with only its own reasons; numeric 0 remains 0, signed negatives stay signed;
  an absent explanation gets neutral unavailable text, never a guessed cause.
- Grade: existing build permits scores at >=50 original weight and renormalizes included parts;
  the row omits components and can omit reasons for parts rejected inside `grade.build`.
  Accept: grade caveats remain visible beside a present grade; do not claim complete coverage,
  infer a coverage percentage, or treat missing grade inputs as healthy/zero from this row.
- Negative CAP: current pay cell preserves sign and uses muted styling; its explanation is in title/footer.
  Accept: a negative compensation-actually-paid percentage remains visible with an accessible
  explanation that it is not superior efficiency, including when it passes a maximum-pay filter.
- Low confidence: current `low` badge expands only through title; positive upside is teal.
  Accept: readable low-confidence context accompanies the estimate without hover or color reliance;
  preserve available upside caveats (share-count sanity/debt assumption), even for nonnull estimates.
- Sources: supplied 10-K/14A destinations must remain intact; valuation `src` was a title-only span.
  Accept: supplied filing links open their actual destinations; source text and missing-source reasons
  are readable by touch and keyboard through visible text or native focusable disclosure controls.
  Do not turn valuation-source prose into an invented URL or claim concept-level traceability.
- Interaction: N/A titles and `src` are not keyboard disclosure controls; scroll-region focus alone
  does not expose their content. Accept: tap and Enter/Space reveal equivalent context with clear
  focus and accessible names; closing disclosure restores usable focus without obscuring table controls.
- Investment language: existing copy calls grade descriptive and estimates cached; retain that context.
  Accept: old built_at/price_date, positive upside and grade A never produce “current bargain”,
  “buy”, “recommended”, or reliable-return labels; changing filters cannot imply refreshed market data.

## Shared helper contract: acceptance boundary, no implementation here

- New dependency-free `web/lib/screenerContext.ts` exports
  `fieldReasons(reasons:readonly string[],field:string):string[]` and
  `dataAgeDays(value:string|null,now:number):number|null`; no external imports/browser APIs.
- fieldReasons splits at the first colon, trims prefix/reason, matches exact field prefixes;
  grade additionally matches grade_score and grade.*; upside_pct additionally matches
  valuation_confidence and price_date. Ignore non-prefixed messages and empty reasons;
  deduplicate trimmed text in original order. Never include unrelated metric reasons.
- Accept mixed reasons: pay_efficiency_pct must not receive grade/upside reasons; grade must
  receive grade.insiders and grade_score but not gradebook; upside must receive price_date
  and valuation_confidence but not pay_efficiency_pct; retain later colons inside reason text.
- dataAgeDays accepts strict valid YYYY-MM-DD or valid ISO timestamps with explicit Z/offset;
  reject missing, malformed, overflowed/impossible components, nonfinite now and future instants.
- Accept leap-day validity, invalid Feb 30/month 13/hour 24, zone-less timestamps and bad offsets;
  compare instants before UTC-day subtraction so a future time today returns null.
- Return floor(now/86400000) minus floor(parsedInstant/86400000), independent of local timezone;
  accept yesterday 23:59Z to today 00:01Z as 1 day, same UTC date as 0, and offset crossings by UTC date.
