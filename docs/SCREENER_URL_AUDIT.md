# Screener URL acceptance and risk checklist

## Final integration evidence — November 9, 2026

The production build and TypeScript passed. All 13 independent URL-contract tests and 13 existing Terminal tests passed. In-app browser checks using real cached results verified a direct multi-filter link, restored sort/page-size, pagination and refresh (page 3 of 4), browser Back, reset preserving an unrelated query parameter and hash, manual-copy recovery when clipboard access was unavailable, immediate removal of the fallback on draft edits, and no page overflow at 390px. Independent review approved initialization/history/request handling and then approved a repair invalidating pending clipboard results immediately on search edits. Delayed clipboard resolution was reviewed statically; successful clipboard writing is deferred to secure production verification. The checklist below is the original preimplementation plan; unchecked scenarios are not additional execution claims.

Preimplementation independent review, not approval. All boxes are acceptance criteria;
no implementation, build, browser, or runtime behavior has been verified here.
Source read: `web/components/Screener.tsx`, `web/lib/screener.ts`,
and `web/app/screener/page.tsx`; canonical repository AGENTS.md read separately.

## Existing source risks

- Search has separate draft/committed state and a 350 ms timer; edits reset offset immediately.
- Request effects start from local defaults; URL restoration must precede fetching.
- Threshold request construction uses `parseFloat`, which accepts partial numbers.
- Reset clears filters/sort/offset but retains limit; resolve this explicitly against shared defaults.
- Request IDs guard responses; old data remains rendered during subsequent loading.
- Sector options come from returned data; restored selections may precede their options.

## Shared pure helper contract

- [ ] Add only dependency-free `web/lib/screenerUrl.ts`: no imports or network/browser globals.
- [ ] Export `ScreenerUrlState`, `DEFAULT_SCREENER_STATE`,
  `parseScreenerUrl(search: string): ScreenerUrlState`, and
  `serializeScreenerUrl(state: ScreenerUrlState): string` (query without `?`).
- [ ] State string fields: search, sector, grade, maxPay, minUpside;
  sort: ticker | name | sector | pay_efficiency_pct | grade_score | upside_pct;
  order: asc | desc; limit and offset: number.
- [ ] Defaults: all five strings empty, sort ticker, order asc, limit 50, offset 0.
- [ ] Owned keys only: search, sector, grade, max_pay_efficiency_pct,
  min_upside_pct, sort, order, limit, offset; map threshold keys to maxPay/minUpside.
- [ ] Trim search/sector, cap each at 100 characters; safely encode reserved characters/Unicode.
- [ ] Grade accepts only A/B/C/D/F; invalid grade becomes empty; invalid sort/order default.
- [ ] Thresholds require full finite `Number` conversion: reject empty/whitespace,
  whitespace-containing values, partial `2junk`, NaN, Infinity and overflow;
  preserve 0 and negatives as canonical number strings (e.g. -2.50 becomes -2.5).
- [ ] Limit accepts only 25/50/100/200, otherwise 50; offset must be a safe integer
  from 0 through 1000000 inclusive, otherwise 0; reject partial numeric parses.
- [ ] Omit defaults; serialization normalizes values consistently with parsing.
- [ ] Check default output is empty and parse/serialize round trips normalized state;
  cover malformed encoding, duplicate keys (document deterministic policy), unknown keys,
  boundary lengths, signed/exponent numbers, offset fractions and out-of-range values.

## Initialization, debounce, reset and navigation

- [ ] Server rendering and first client render agree without reading window on the server;
  restore URL state before enabling the first request or writing defaults to history.
- [ ] A direct link's first request uses all restored filters/sort/limit/offset together;
  no preliminary default request or timer-driven reset to offset 0.
- [ ] Restore draft and committed search together; retain a supplied sector even before
  sector options load, so control, request and URL describe the same selection.
- [ ] Debounce only interactive search edits; commit search plus offset 0 atomically,
  avoiding an old-search request caused solely by the immediate page reset.
- [ ] Reset cancels/invalidates pending search work, resets both search states and all
  shared defaults (including limit 50), and removes owned default query keys.
- [ ] Back/Forward (`popstate`) restores every field atomically, including both searches;
  a pending debounce cannot overwrite restored state or reset its saved offset.
- [ ] Filter/sort/page-size edits reset offset; pagination preserves filters and sort.
- [ ] Define push versus replace policy; avoid per-keystroke history spam and navigation
  feedback loops; clean up timers/listeners and tolerate Strict Mode effect replay.

## URL ownership and sharing

- [ ] Merge owned keys into the current URL; preserve pathname, unrelated parameters
  (including duplicates), hash, and existing `history.state`/framework metadata.
- [ ] Reset/canonicalization removes only owned keys; never replace the whole query
  with helper output. The helper serializes screener state, not unrelated parameters.
- [ ] Copy produces an absolute reloadable URL for the intended current state;
  define pending-draft behavior so copying cannot silently share a previous search.
- [ ] Missing clipboard API, insecure context and rejected writes show accessible failure
  feedback/manual-copy recovery; announce success only after the write resolves.

## Results and mobile preservation

- [ ] Out-of-order successes and failures, reset, navigation and unmount cannot apply
  obsolete responses; retain request identity protection for every state transition.
- [ ] While loading, retained rows/counts/pagination are clearly stale or withheld;
  never label old results as matching the newly restored filters. Retry uses current state.
- [ ] Preserve distinct loading/error/retry/unavailable/no-match/offline states,
  source links, N/A reasons, dates, warnings and existing financial explanations.
- [ ] At narrow widths (320/375 px), long URL values and copy feedback wrap without
  page overflow; retain the table's own horizontal scroll and keyboard focus region.
- [ ] Preserve labels, focus indicators, status announcements, touch-sized controls,
  sort aria state and wrapping pagination; copying/reset/navigation remain operable.

Supervisor to integrate and test: helper edge cases, controlled request/timer ordering,
SSR/hydration, history/clipboard failures, mobile checks, and the required web build.
