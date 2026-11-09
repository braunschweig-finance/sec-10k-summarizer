# Company screener v1 contract

Use existing cached SEC/valuation data only: no live SEC, price, AI or external HTTP calls during screening. Do not change financial formulas, grade weights, peer valuation logic or provider settings. Reuse existing pure `grade.build`, `valuation.value` and sector/benchmark helpers where applicable. Missing/corrupt/unavailable inputs remain missing, never zero. Grade means the existing descriptive **Company Grade**, not a new governance-only grade. Estimates use cached price dates, not live prices.

## Endpoint

`GET /api/screener`

Optional query parameters: `search` (ticker/name substring), `sector` (exact sector), `grade` (A/B/C/D/F), `max_pay_efficiency_pct` (finite percentage points), `min_upside_pct` (finite percentage points), `sort` (ticker/name/sector/pay_efficiency_pct/grade_score/upside_pct; default ticker), `order` (asc/desc; default asc), `limit` (1..200; default 50), `offset` (>=0; default 0).

Response always includes:

```
{
  "available": true,
  "built_at": "cached manifest timestamp or null",
  "total": 1000,
  "matched": 123,
  "limit": 50,
  "offset": 0,
  "sectors": ["Industrials"],
  "coverage": {"pay_efficiency_pct": 900, "grade": 700, "upside_pct": 600},
  "rows": [{
    "ticker": "CAT", "name": "Caterpillar", "sector": "Industrials",
    "fy_end": "2025-12-31",
    "pay_efficiency_pct": 1.18,
    "grade": "B", "grade_score": 70.0,
    "upside_pct": 12.5, "price_date": "2026-10-30",
    "valuation_confidence": "normal",
    "sources": {"financials_url": "filing URL or null", "proxy_url": "filing URL or null", "valuation_source": "existing valuation source description or null"},
    "missing": []
  }],
  "warnings": []
}
```

Numbers/company counts above illustrate the schema, not promised data. All per-row fields are required; unavailable values use null with a reason in `missing`. Confidence can be normal/low/null. `total` and coverage describe the unfiltered snapshot; `matched` is after filters, before pagination. Sort nulls last in both directions; ticker is the deterministic tie-breaker. Numeric filters exclude missing metrics. Pay-efficiency values are existing `pct` percentage points, using operating-income denominator only. Negative compensation values stay signed and must not be called superior efficiency. Low-confidence valuation must be identified; do not label it a reliable investment signal.

Build a bounded, cached snapshot from the prebuilt directory/manifest and valuation.json. Invalidate on refresh/file changes; avoid repeat whole-universe computation per filter request. Reuse only data on disk; no per-company live API calls. Missing snapshot: HTTP 200 with `available:false`, empty rows, zero counts and explanatory warnings (not fabricated sample results).

## Page

New `/screener` route, linked visibly from the existing terminal home. Match existing dark theme and reusable table/filter styling. Search, sector, Company Grade, maximum pay-efficiency %, minimum peer-valuation upside %, sorting and pagination. Label snapshot timestamp, coverage, cached price dates, missing cells and low-confidence values. Loading, error/retry, unavailable and no-match states must differ. Accessible labels, keyboard controls and responsive overflow. Changing filters resets pagination; stale responses cannot overwrite newer filters.

Rows link to `/?ticker=SYMBOL`; implement URL-ticker loading in Terminal using an effect placed before the existing `load` declaration so its existing standalone closure tests remain valid. No automatic AI calls. No credentials, formula changes, nested agents, or Chrome automation.

## Parallel ownership

- API builder: api/screener.py, main.py route, tests/test_screener_data.py only.
- UI builder: web/app/screener/page.tsx, new web/components/Screener.tsx, minimal Terminal.tsx link/query loading and optional isolated web/lib/screener.ts only.
- QA: tests/test_screener_contract.py and docs/SCREENER_QA.md only; independent fixtures, no implementation edits.
- Data auditor: docs/SCREENER_DATA_AUDIT.md only; verify existing schema/source/grade/valuation reuse and flag limitations. This is pre-implementation audit, not final code approval.

Each agent owns a separate worktree. Supervisor integrates, tests, independently reviews and verifies a working preview before PR completion. Keep each agent's working context below 250,000 tokens; use small reads and fresh sessions, never load entire historical logs.
