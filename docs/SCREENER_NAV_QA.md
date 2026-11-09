# Analyze | Screener navigation and mobile screener QA

## Integrated validation — November 9, 2026

The supervisor verified the production build in the in-app browser at 390×844, 768×1024 and 1280×800. The page did not exceed viewport width; only the table region overflowed. Both primary navigation links measured 44px high. Screener and Analyze each received the correct `aria-current="page"` after navigation. Keyboard ArrowRight scrolled the named, visibly focused table region to its final columns. Real cached rows, source links and existing caveats remained present. Production build/TypeScript and all 13 Terminal regression tests passed. A separate final code review approved all three implementation files. The broader matrix below remains a reusable acceptance plan; unexecuted scenarios are not claimed as passed.

## Scope and evidence

Independent acceptance plan for the planned navigation/mobile changes. Read the canonical `sec-10k-summarizer/AGENTS.md`, `web/app/{layout,page,globals.css}`, `web/app/screener/page.tsx`, `web/components/{Terminal,Screener}.tsx`, `web/lib/screener.ts`, and `docs/SCREENER_CONTRACT.md`.

**Source inspection only.** No browser, build, unit test, API request, or viewport check was executed. All acceptance checks below are pending; this document is not implementation approval. No implementation edits or brittle source-text tests are part of this task.

## Test setup and evidence to retain

Use a local Next.js build and a controlled cached-response fixture through the existing API interface; do not change credentials, production configuration, or formulas. Test both API-connected mode and the existing no-API preview. A preview-only check cannot validate the populated screener. Use an allowed non-Chrome browser.

Prepare response cases covering more than 200 matches, a partial final page, no matches, unavailable snapshot, request failure/retry, slow/out-of-order responses, long company/sector/source text, null metrics with reasons, negative Pay Efficiency, zero metrics, low-confidence upside, grade/upside caveats, and missing source URLs. Fixture numbers are test data, not verified filing facts. Use existing public cached records separately for source verification.

For each check record viewport, route, fixture or snapshot timestamp, steps, expected/actual result, and pass/fail or blocked. Capture screenshots for all three widths and keyboard focus, plus relevant request parameters for filter/pagination checks. Run `npm run build` from `web/` on the final implementation and record its actual result. Do not report an unavailable check as passed.

## Responsive acceptance matrix

Run at CSS viewport sizes **390 × 844**, **768 × 1024**, and **1280 × 800**, at 100% zoom, on `/`, `/?ticker=CAT`, and `/screener`. Repeat the narrow-layout checks with long text, errors, and populated results.

| Width | Required acceptance checks |
| --- | --- |
| 390 | Analyze and Screener are both discoverable and tappable without sideways page movement. Header, title, search, all four other filters, reset, counts, warnings, and pagination fit within the viewport. Labels wrap without overlapping controls; long sector selections do not widen the page. Mobile rows/cards retain company identity, FY end, all metrics, price date, sources, and caveats. If a table remains, only its explicit scroll region scrolls horizontally; the last source column is reachable by touch and keyboard, with an evident overflow affordance. Prev/Next and page size wrap without clipping. |
| 768 | Check the intermediate layout independently: filter spans and labels remain aligned, no empty/overlapping grid tracks, and navigation stays visible. All result fields and source controls remain accessible across the mobile/desktop presentation boundary. A table may scroll locally; it must not push pagination or caveats beyond the viewport. Resize from 390 to 768 with filters/page selected: no duplicate results or lost state solely due to resizing. |
| 1280 | Header and content align with the existing centered content/gutters. Navigation does not collide with the live/preview badge or hero. Desktop table shows all nine current column roles with readable headings and intact row associations. Long caveats wrap without obscuring adjacent cells. Counts, page-size control, page indicator, Prev/Next, and explanatory text remain usable. Resize to 390 and back without duplicate requests caused solely by alternate result renderings. |

At every width verify document-level horizontal overflow and inspect clipped content: `body` currently hides horizontal overflow, so absence of a scrollbar alone is insufficient. Check 200% zoom, reduced motion, and visible focus after scrolling. If navigation becomes sticky, it must not cover focused controls or content.

## Navigation, keyboard, and active state

- Direct-load and refresh `/`: Analyze alone has a visible active treatment and `aria-current="page"`. On `/?ticker=CAT`, Analyze remains active. On `/screener`, Screener alone is active. Active state must remain distinguishable without color alone and must differ from hover/focus.
- Both items are real links with correct destinations (`/` and `/screener`) inside a named navigation landmark. Enter activates them; open-in-new-tab and browser Back/Forward work. Do not use report-tab semantics for route navigation. Route active state follows the pathname after navigation and history changes.
- Tab/Shift+Tab through navigation, filters, reset, sort controls, ticker/source links, page size, and pagination. Focus is visible, follows visual reading order, never enters hidden duplicate mobile/desktop controls, and is never trapped. Native selects work with arrow keys; buttons work with Enter/Space. Exactly the current route is announced as current.
- Load the screener in every state (loading, error, unavailable, no match, data, offline preview): global navigation remains usable. Any retained local back links agree with Analyze and do not create competing active states.
- Open a result ticker, including an encoded symbol containing punctuation: destination retains `?ticker=...`, loads the intended company, and marks Analyze active. Navigation must not strip the query or initiate a company load merely by rendering the header. Return with Back and record filter/page restoration behavior; do not promise persistence unless implemented intentionally.
- Preserve the terminal ticker form, live/preview indicator, report tabs, loading/error behavior, and exports. Global Analyze must remain distinct from the form's Analyze action and report tabs.

## Filters, sorting, pagination, and async states

- Initial connected request uses ticker ascending, limit 50, offset 0. Verify search by ticker and name, whitespace trimming, and the existing 350ms debounce using observable requests/results, not source matching. Quick typing must ultimately show the newest query's rows/counts only.
- On page 2 or later, independently change search, sector, grade, each numeric filter, sort, and page size: committed results return to offset 0 with matching counts. Combine all filters and verify their parameters survive Next/Prev and sorting. Clearing a numeric field removes its parameter; zero and negative finite values retain their sign/value in percentage points. Incomplete/invalid numeric entry must not become a fabricated zero or silently misleading filter.
- Exercise all six sortable fields in both directions. Same-column activation toggles direction; a new column starts ascending. Visible direction and accessible sort state agree with results. Nulls remain last in either direction and tied values use ticker order, per the contract. Mobile presentation must retain a reachable sorting mechanism and announce its state.
- Exercise page sizes 25/50/100/200. Verify ranges against response offset/row count, no skipped/duplicate tickers across adjacent pages, Prev disabled on the first page, Next disabled on the last, and correct partial-final-page ranges. For a controlled 123-match fixture at size 50, expect 1–50, 51–100, 101–123 and pages 1–3.
- Reset clears filters and restores ticker ascending/page 1 while retaining the selected page size (current behavior). No-match clear restores results. Zero matches must not show a misleading populated range or actionable Next.
- Delay requests and rapidly change filters, sort, size, Next/Prev, then reset. Deliver older responses last: neither old successes nor old errors may replace current results. During refresh, retained old rows/counts must be clearly marked busy and must not imply that they match the new controls. Repeated Next clicks must not create an empty out-of-range page or a false page indicator.
- Verify distinct initial loading, refresh loading, error with working retry, `available:false` with warnings/retry, valid empty results, and no-API offline preview. No state invents sample rows or silently falls back to another company's data. Retry preserves the current query. Status/error messages are announced without unexpected focus jumps.
- Inspect local network activity: screening/filtering/pagination uses the cached screener endpoint, with no per-company SEC, price, or AI calls. Opening a ticker is a separate terminal action; do not confuse its requests with screening.

## Financial caveats and source preservation

- Compare desktop and mobile presentations against the same response: ticker/name/sector/FY, Pay Efficiency, Company Grade plus score, upside, cached price date, confidence, missing reasons, and sources all survive. Preserve current rounding/signs (Pay Efficiency two decimals, score whole number, upside one decimal with positive sign), including zero and null distinctions. Do not recompute metrics in the UI.
- Preserve snapshot built date, unfiltered coverage counts/total, filtered matched count, cached-price warning, server warnings, and unknown-date behavior. The current Price (cached) column displays a **date**, not a price amount; mobile labels must describe that honestly. Coverage counts must not be presented as percentages.
- Preserve the signed Pay Efficiency explanation: CEO pay actually paid divided by operating income; a negative value does not imply better efficiency. Missing values remain N/A with their actual reasons, never zero. Reasons and valuation source descriptions must be accessible by touch and keyboard as well as pointer hover.
- Preserve the explanation that Company Grade is the overall grade, including governance, red flags, insiders and value versus peers. Keep per-row grade/upside caveats adjacent to their metrics and low-confidence badges/explanations attached to the correct row. The low-confidence count describes the current page only; it is not the whole universe or an investment recommendation.
- Preserve the cached peer-valuation estimate framing, individual price dates, and no-live-calls disclosure. Do not rename upside as guaranteed return or suggest prices are current. Keep caveats accessible even if cards collapse details.
- For public cached records, follow each available 10-K/14A link and verify company, filing period/accession and relevant financial/proxy evidence; inspect valuation source descriptions too. Preserve exact supplied URLs and safe new-tab behavior. Missing URLs must not produce empty links or invented citations. A generic filing link alone does not establish concept-level traceability: report missing XBRL concept/accession, proxy sentence, or valuation provenance as a limitation requiring follow-up, without inventing it in the UI.
- Recheck terminal source tags and Excel/PDF source listings after navigating from a screener row. Any existing verified filing quote must remain verbatim and associated with its source. This change must not alter formulas, AI verification, or exports.

## Likely regressions identified by source inspection

These are risk findings against the current baseline, not reproduced runtime failures or verdicts on the planned implementation.

| Risk | Evidence and targeted check |
| --- | --- |
| Navigation duplicated or route active state wrong | Root layout currently has no global navigation; Terminal has a hero Screener link and Screener has header/footer Terminal links. Verify one coherent global landmark and query-safe active state. |
| Mobile content silently clipped | Screener table has `min-w-[1020px]`; body has `overflow-x: hidden`. Two-column base filter grid and long native selects need narrow-width checks; local scrolling must actually reach Sources. |
| Important explanations unavailable on touch/keyboard | N/A reasons, signed Pay Efficiency explanation, valuation `src`, and confidence details currently rely partly on `title` attributes/non-focusable spans. Mobile conversion must expose the substance without hover. |
| Responsive cards omit financial context | Current table associates sources, price dates and caveats by row. Check that cards preserve this association and do not hide warnings or duplicate accessible content. |
| Pagination outruns refreshed results | Current controls remain usable while older data is retained during loading; Next uses current offset plus limit while its disabled condition uses existing matched data. Repeated clicks, delayed filters, and changing result counts need explicit checks. |
| Search briefly shows a different query/page | Search input immediately resets offset, while committed search updates after debounce. Test from a later page under delay so intermediate old-query rows cannot be mistaken for the newly typed search. |
| Runtime accessibility/build gap | No rendered viewport or accessibility evidence was collected here. Planned shared navigation may introduce client/server routing or hydration issues; final production build plus route/keyboard checks remain required. |

## Completion gate

Release evidence must include the final diff reviewed independently, actual build result, all three viewport results, keyboard/current-link results, async/filter/pagination results, source/caveat comparisons, and any unresolved failures. Until those checks are executed, status remains **acceptance plan prepared; runtime QA pending**.
