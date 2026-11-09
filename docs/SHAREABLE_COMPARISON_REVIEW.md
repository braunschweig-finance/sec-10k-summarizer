# Shareable comparison: independent preimplementation review

Status: acceptance/risk checklist only; no implementation approval or runtime verification.
Scope: proposed contract reviewed against current API, screener client, URL state,
selection guards, comparison rendering and data notes. Parent integrates and verifies.

## API acceptance

- [ ] Existing GET /api/screener accepts optional `compare=CAT,AAPL`; append
  `compare=None` to `screen(...)`, preserving every existing positional argument.
- [ ] Omitted compare leaves the entire response unchanged, including key presence.
- [ ] Provided compare is at most 128 characters before trimming; trim/uppercase
  each comma-separated ticker, dedupe in requested order, require 1–4 unique.
- [ ] Every token fully matches existing `_TICKER`: `[A-Z0-9][A-Z0-9.-]{0,14}`.
  Empty input/tokens, unsafe tokens and >4 unique raise ValueError; route returns 422.
- [ ] Test 128/129 characters, 15/16-character tickers, lowercase, whitespace,
  duplicates, trailing commas, punctuation, internal whitespace and five unique.
- [ ] Each valid screen call invokes `_snapshot` exactly once; comparison selects
  from that complete snapshot, ignoring filters, sorting and page boundaries.
- [ ] Add only `comparison:{tickers:string[],rows:full matching rows,missing:string[]}`;
  tickers retain normalized request order, rows and missing retain their respective
  requested order. An existing row with null metrics is not an absent ticker.
- [ ] Compare filtered/paginated requests with/without compare: existing page rows,
  matched/total counts, coverage, sectors, warnings and pagination remain identical.
- [ ] Missing/all-missing/unavailable snapshots return explicit missing tickers;
  never fetch companies separately or fabricate rows. Deep-copy nested comparison
  sources/missing and page rows; mutate response and verify cached snapshot intact.

## URL helper acceptance

- [ ] New import-free `web/lib/comparisonUrl.ts` exports exactly the requested APIs:
  `parseComparisonUrl(search:string):{tickers:string[],open:boolean}` and
  `writeComparisonParams(params:URLSearchParams,tickers:readonly string[],open:boolean):URLSearchParams`.
- [ ] Parser uses first compare value, rejects that raw value over 128 characters,
  splits commas, trims/uppercases, drops invalid/empty/duplicate tokens, keeps first 4.
  Unlike strict API validation, malformed tokens do not invalidate other valid tokens.
- [ ] Open only when first comparison value is exactly `1` and >=2 valid tickers.
  Test repeated keys, encoded separators, absent/empty input and overlong raw values.
- [ ] Writer returns a NEW object, leaves input untouched, preserves unrelated keys
  including duplicates, replaces only compare/comparison, normalizes valid first 4.
  Empty selection writes neither key; comparison=1 requires open and >=2 tickers.

## Restoration, interaction and compatibility risks

- [ ] Reload/share restores requested order and off-page/filtered-out companies from
  the response comparison rows, never from page-only matches or separate requests.
  Resolve selection atomically with that response; null build dates require same-object
  provenance. A build timestamp alone cannot prove two responses share one snapshot.
- [ ] Show missing symbols explicitly even when >=2 others resolve; never silently
  present a partial selection as complete. Fewer than 2 resolved rows cannot open.
- [ ] Retain built_at, fiscal periods, cached price dates, filing/source links,
  field caveats, signed Pay Efficiency, N/A reasons and low-confidence warnings.
- [ ] Preserve filter/sort/page URL behavior and unrelated duplicates when selecting,
  opening, closing and copying; closing preserves selection with no comparison=1.
- [ ] Define reset semantics explicitly: current action says Reset all filters;
  test chosen selection/open behavior and URL together, avoiding stale resurrection.
- [ ] Popstate restores filters, selection and open intent together before fetching;
  cancel pending search debounce and invalidate older requests/clipboard callbacks.
- [ ] Exercise draft typing then copy/reset/back/forward, slow old response after
  navigation, selection changes during fetch and clipboard rejection after state change.
  Copy only committed coherent state; stale callbacks cannot restore old UI or links.
- [ ] Late backend: a 200 response without comparison means unsupported, not success
  or missing tickers. Preserve link intent, explain unavailable restoration, retain
  ordinary screening and allow retry; do not reconstruct from page rows. Verify
  old backend/new UI, new backend/old UI, 422, network failure and eventual support.

Evidence still required: focused API/helper tests and interaction checks above,
plus relevant existing regressions and frontend build after integration. No approval.
# Integration evidence — November 9, 2026

Build/TypeScript and 54 frontend tests passed. The full API run passed 330 tests; its existing process-startup test timed out during the parallel build and passed when rerun alone. Independent final review approved the repaired request-identity guard for Back/Forward restoration.

Browser checks using a four-company copy of public cached records verified restoration of CAT/AAPL despite a no-match filter, preserved order and sources, copy/manual fallback, refresh reopening, closing while retaining tickers, and explicit blocking for an unavailable third ticker. The subsequent local retry/recovery check was blocked by a delayed API response; no runtime claim is made for that case or old-backend compatibility. Snapshot subset files are test artifacts outside the repository; original data is unchanged.

