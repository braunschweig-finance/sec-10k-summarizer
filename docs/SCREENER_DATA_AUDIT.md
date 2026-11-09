# Screener data/source audit (pre-implementation)

Data auditor's audit of `docs/SCREENER_CONTRACT.md` against the cached data and existing helpers in this
worktree (`work/screener-audit`, commit c7c033e, based on origin/main). Scope: verify that every field in the
contract's row schema can be produced **from data already on disk**, with the **existing pure helpers**, and
**without network or AI calls**; document source paths/keys, units, dates, coverage limits and a cheap caching
strategy; flag contract ambiguities and accuracy risks with file/line evidence.

**Honesty limits of this audit.** No `prebuilt.tar.gz` sample exists in this worktree (it is a GitHub release
artifact, `api/prebuilt.py:17-20`), and this audit was run without network, so no real prebuilt files could be
inspected. Every schema statement below is therefore derived from the code that **writes** the files
(`api/prebuild.py`) and the code that **reads** them (`api/prebuilt.py`, `api/main.py`). A QA-phase check against
the live file is recommended (see §9). Nothing here approves code that does not exist yet, and no formula,
weight, peer rule or provider setting is changed or proposed.

**Bottom line:** every contract field is derivable from the on-disk prebuilt directory + `valuation.json` +
`benchmarks.json` using existing pure helpers, with no network and no AI. Four decisions are needed before the
API builder starts (A1, A2, A3, A6, §10), and one systematic accuracy exposure must be surfaced in the UI
(B3, §11).

---

## 1. Cached data inventory (what the screener may read)

The weekly prebuild (`api/prebuild.py`, published by `.github/workflows/prebuild.yml`, cron `17 6 * * 1` at line 9)
writes `prebuilt.tar.gz`; the API downloads it at startup, within an hour of each new build, and at least every 12 h
(`api/prebuilt.py:29-31,101-114`) into `PREBUILT_DIR` (default `/tmp/prebuilt`, `api/prebuilt.py:21`):

```
<TICKER>/company.json        get_financial_report      (10-K statements, ratios, inputs)
<TICKER>/governance.json     get_governance_report     (DEF 14A checks, metrics, proxy_url, proxy_date)
<TICKER>/pay_efficiency.json get_pay_efficiency        (Pay Versus Performance vs operating income)
<TICKER>/trends.json         get_trends                (5-year income lines + year-end prices)
<TICKER>/risks.json          get_risk_summary          (Item 1A headings)
<TICKER>/fundamentals.json   get_valuation_inputs      (10-K valuation inputs, 10 fiscal years)
<TICKER>/red_flags.json      get_red_flags             (3 years of 8-K/NT flags)
<TICKER>/insiders.json       get_insider_trades        (12 months of Form 4 P/S trades)
manifest.json                {"built_at", "tickers", "failures"}   (api/prebuild.py:88)
benchmarks.json              {"source", "sectors": {...}, "all": {...}} (api/prebuild.py:77-80)
valuation.json               {"source", "rows": [...], "backtest", "built_at"} (api/prebuild.py:83-86)
```

- `KINDS` = the eight per-company files (`api/prebuilt.py:22`).
- `manifest["tickers"]` = tickers with **at least one** successful lookup (`api/prebuild.py:43-57,73,88`);
  `manifest["failures"]` = tickers with one or more failed lookups (`api/prebuild.py:50-52,75,88`). A ticker whose
  lookups **all** failed appears only in `failures`.
- A lookup that honestly found no data is saved as `{"__unavailable__": "<reason>"}` (`api/prebuild.py:48-49`),
  e.g. "doesn't file 10-K annual reports" (`api/sec_core.py:47-48`). That body **is not data**; readers treat it
  as unavailable (`api/main.py:136-137`, `api/benchmarks.py:36`).
- Lookups are saved "exactly as the API would return it" (`api/prebuild.py:4`), so each file's schema is the
  return value of the named function.
- Per-ticker files missing for a kind mean the lookup failed at build time (`api/prebuild.py:51-53`); a corrupt or
  missing file reads as `None` (`api/prebuilt.py:37-43`).

**Network/AI boundary for the endpoint.** The screener handler must read only: the per-kind JSON files above,
`manifest.json`, `benchmarks.json`, `valuation.json` (via `valuation.load`, `api/valuation.py:431-440`), plus
in-memory computation. It must **not** call `main.lookup`/`cached_*` (they fall back to live SEC,
`api/main.py:132-139,143-184`), `prebuilt.check/refresh` (network, `api/prebuilt.py:58-114`), `prices.*`
(Yahoo, `api/prices.py:14-77`), `sec_core.sec_fetch` (SEC, `api/sec_core.py:552-560`) or `ai_client` (AI).
`prebuilt.get` itself is a safe plain file read (`api/prebuilt.py:37-43`).

## 2. Per-field source map (exact paths and keys)

`DIR` = `PREBUILT_DIR`. All rows below are file-relative keys as produced by the named generator.

| Contract field | Source file → key(s) | Generated at | Notes |
|---|---|---|---|
| `ticker` | `manifest.json → tickers[i]` (directory name) | `api/prebuild.py:88` | Uppercase; universe list, §8.1 |
| `name` | `DIR/<T>/company.json → name` | `api/sec_core.py:483` | Fallback chain A13: `fundamentals.json → name` (`api/sec_core.py:989`, same edgartools source) → `red_flags.json → name` (`api/red_flags.py:187`) / `insiders.json → name` (`api/insiders.py:285`) (SEC ticker→company mapping) |
| `sector` | `sectors.sector(sic)`; `sic` from `company.json → sic` | `api/sectors.py:74-80`; `api/sec_core.py:484` | Pure helper. `sic` fallback: `fundamentals.json → sic` (`api/sec_core.py:991`) or `valuation.json` row `sic` (`api/valuation.py:154`). Unmapped SIC → `None` → null + `missing` entry; grade then compares vs whole Russell 1000 (`api/benchmarks.py:110-112`) |
| `fy_end` | **Decision A2.** Candidates: `fundamentals.json → years[-1].fy_end` (`api/sec_core.py:975,983,993`); `valuation.json` row `fy_end` (`api/valuation.py:156`); `pay_efficiency.json → fy_end` (`api/sec_core.py:735`) | — | `company.json` has **no clean fiscal-year-end key**: `inputs[*].period` is a display column string like `2025-12-31 (FY)` (`api/sec_core.py:196,495`), not an ISO date |
| `pay_efficiency_pct` | `DIR/<T>/pay_efficiency.json → pct` | `api/sec_core.py:734` | Percentage points: `cap / op * 100` (`api/sec_core.py:730`). Only when `available == true` **and** `denominator == "operating"` (contract line 37; matches `api/grade.py:45-46` and `api/benchmarks.py:45-46`). `pct` is `None` on operating loss ("N/M", `api/sec_core.py:727-728`) or missing operating/pretax income (`api/sec_core.py:724-726`). `available == false` reasons: no DEF 14A / no proxy XBRL / no PVP tag (`api/sec_core.py:674,679,683`). `denominator == "pretax"` (`api/sec_core.py:713-718`) → treat as **missing** per contract (operating only) |
| `grade`, `grade_score` | `grade.build(ticker, name, parts, errors)` | `api/grade.py:127-159` | `parts` assembled from cached files, §4. `letter` + `score` at `api/grade.py:159`; `available == false` when <50% of the weight is readable (`api/grade.py:155-157`) → both null + reason in `missing` |
| `upside_pct` | `valuation.value(row, rows)["upside_pct"]` | `api/valuation.py:246` | `(fair / price - 1) * 100`, percentage points. Only when est `available == true` (`api/valuation.py:245`); else null + reason (`api/valuation.py:236-237`). `row` = the ticker's stored row in `valuation.json`; `rows` = **all** stored rows (self is excluded inside `choose_peers`, `api/valuation.py:187-188`) — same inputs as the live route `api/main.py:306,317` |
| `price_date` | `valuation.json` row `price_date` | `api/valuation.py:157` | ISO date of the close actually used (last trading day ≤ build day, `api/valuation.py:295-298`). **Per-row**, can differ by company (trading halts) — the UI must show it per row, not one global date |
| `valuation_confidence` | `valuation.value(row, rows)["confidence"]` | `api/valuation.py:246` | `"normal"` / `"low"` when available; null when the estimate is unavailable. `"low"` = peer range top > 3× bottom (`api/valuation.py:47,244`); note text in `confidence_note` (`api/valuation.py:247-248`) |
| `sources.financials_url` | `DIR/<T>/company.json → tenk_url` | `api/sec_core.py:486` | Non-empty whenever `company.json` exists (`annual_reports` raises without a 10-K, `api/sec_core.py:51-56`); null + `missing` when the file is absent/unavailable |
| `sources.proxy_url` | `DIR/<T>/governance.json → proxy_url` | `api/sec_core.py:507,513` | Can be `""` when no DEF 14A was read → normalize `""` → null (A4). Alternate: `pay_efficiency.json → proxy_url` (`api/sec_core.py:697`), present only when available |
| `sources.valuation_source` | `valuation.json → source` | `api/valuation.py:53-54,425` | Universe-level description ("10-K figures: SEC EDGAR companyfacts (XBRL) … Prices: Yahoo Finance daily close …"). Per-company XBRL concept+accession for each input line live in `fundamentals.json → years[*].values[*] → {concept, accn, url}` (`api/sec_core.py:946`) if the builder wants row-level traceability (A5) |
| `missing` | assembled per row | — | One entry per null field with its reason; reasons available verbatim from the files (§5) |
| `built_at` | `manifest.json → built_at` (also `prebuilt.status()["built_at"]`) | `api/prebuild.py:88`; `api/prebuilt.py:79` | `valuation.json → built_at` (`api/prebuild.py:84`) is seconds earlier and is the actual as-of of the prices; the seconds difference is negligible but worth noting (A9) |
| `total`, `coverage` | computed over the unfiltered snapshot | — | `total` universe definition = A3; `coverage` = non-null counts per metric (§8.4) |

## 3. Units: percentage points vs ratios vs index values

| Quantity | Unit | Evidence |
|---|---|---|
| `pay_efficiency_pct` | **percentage points** (1.18 = 1.18%) | `cap / op * 100` (`api/sec_core.py:730`); display string `f"{pct:.2f}%"` (`api/sec_core.py:731`) |
| `upside_pct` | **percentage points** | `(fair / price - 1) * 100` (`api/valuation.py:246`) |
| Board Independence, Say-on-Pay Support | **percentage points** (0–100) | `ind / total * 100` (`api/governance_metrics.py:129`); vote `float(pct)` (`api/governance_metrics.py:234`) |
| CEO Pay Ratio | **raw ratio** (150 = 150:1), *not* a percent | parsed "N to 1" value (`api/governance_metrics.py:56-79`) |
| `grade_score`, part scores | 0–100 index | `api/grade.py:9-29,54-55` |
| Sector stats (`p25/median/p75`) in `benchmarks.json` | same units as the metric itself | built from the same lookups: `api/benchmarks.py:44-51` |
| Grade placement | value and sector stats always same-unit pairs | `grade.place` (`api/grade.py:58-65`); governance values read from the same `metrics` dict that `benchmarks.py` summarized |
| Grade valuation curve | `tanh(gap / 60)` with `gap` in percentage points | `api/grade.py:24-26,123` (30 pp ≈ 73) |
| Contract filters `max_pay_efficiency_pct`, `min_upside_pct` | "finite percentage points" (contract line 9) | matches the two columns above; no ×100 conversion anywhere in existing code |

No percentage/ratio unit mismatch exists between the stored values and the existing helpers. The only ratio
(non-percent) in the set is CEO Pay Ratio, which the screener does not surface directly (it feeds the grade).

## 4. Existing pure helpers (reusable as-is)

| Helper | Purity | Evidence |
|---|---|---|
| `grade.build(ticker, name, parts, errors)` | Pure (no I/O at all) | `api/grade.py:127-159`; module imports only `math` (`api/grade.py:31`). Returns `available/score/letter/components/missing/method/disclaimer` |
| `grade.governance_part / red_flags_part / insiders_part / valuation_part / place / letter` | Pure | `api/grade.py:50-124` |
| `valuation.value(target, rows, k=8)` | Pure | `api/valuation.py:215-248`; only `peers.percentile` (`api/peers.py:40-45`) |
| `valuation.choose_peers / per_share / methods_for / industry_step` | Pure | `api/valuation.py:57-212` |
| `sectors.sector(sic)` | Pure | `api/sectors.py:74-80` |
| `peers.percentile(sorted_vals, q)` | Pure | `api/peers.py:40-45` |
| `benchmarks.for_company(sic, path)` / `benchmarks.load(path)` | Disk read only (no network) | `api/benchmarks.py:87-112`; mtime-keyed cache |
| `valuation.load(path)` | Disk read only (no network) | `api/valuation.py:428-440`; mtime-keyed cache |
| `prebuilt.get(kind, ticker)`, `prebuilt.status()` | Disk read only / in-memory | `api/prebuilt.py:37-55` |

`grade.build` needs no modification: its `parts` signature (`api/grade.py:128-129`) is exactly
`{"governance": (governance.json, pay_efficiency.json, benchmarks.for_company(...)), "red_flags": red_flags.json,
"insiders": (insiders.json, market_cap), "valuation": <est from valuation.value>}`. The live route assembles the
same shapes from the same files (`api/main.py:409-440`); the screener differs only in that `market_cap` comes from
the cached `valuation.json` row (`api/valuation.py:158`) and `est` comes from `valuation.value(row, rows)` instead
of `valuation.report` (the live report re-runs `build_row` at a live price, `api/valuation.py:449-454` — that step
is exactly what must **not** happen here; the stored row already is the `build_row` result).

Note: `valuation.value` output includes everything `grade.valuation_part` reads — `available`, `confidence`,
`upside_pct`, `verdict`, `fair_value`, `price`, `reason`/`confidence_note` (`api/valuation.py:236-248`,
`api/grade.py:117-124`). The est object alone suffices for the grade; no `report()` wrapper needed.

## 5. Missing / unavailable / corrupt data handling

Contract rule (line 3): "Missing/corrupt/unavailable inputs remain missing, never zero."

1. **Sentinel body.** `{"__unavailable__": reason}` means "SEC has no usable data, and here is why"
   (`api/prebuild.py:49-50`). Check it on **every** file read, the same way `api/main.py:136-137` and
   `api/benchmarks.py:36` do. The reason string is suitable verbatim for a `missing` entry.
2. **Absent/corrupt file.** `prebuilt.get` returns `None` on `OSError`/`ValueError` (`api/prebuilt.py:37-43`);
   `valuation.json`/`benchmarks.json` missing → `None` from `load()` (`api/valuation.py:434-436`,
   `api/benchmarks.py:89-92`). Field → null, `missing` entry "not in prebuilt data".
3. **Per-field availability conditions** (all already encoded in the files):
   - `pay_efficiency_pct`: §2 — `available`, `denominator`, `pct not None`.
   - `grade`: `grade.build` returns `available: false` + `reason` when <50% of weight is readable
     (`api/grade.py:155-157`); each dropped part lands in `missing` with a reason (`api/grade.py:130,136,146,151`).
   - `upside_pct` / `valuation_confidence`: est `available` (`api/valuation.py:236-245`); reason string
     "None of the valuation multiples could be applied …" (`api/valuation.py:237`).
   - `name`/`sector`/`fy_end`/`sources.*`: per the fallbacks in §2.
4. **Real zeros are data, not missing.** `insiders.json` with `buys.value == 0` and `trades == 0`
   (`api/insiders.py:211-228`) means "no open-market trades in the last 12 months" — a legitimate value; the
   grade scores it 50 "nothing unusual" (`api/grade.py:110-111`), which is the intended semantics.
5. **`governance.json` without a DEF 14A.** `get_governance_report` does not raise; it returns the empty template
   (`api/sec_core.py:507,508-517`): `metrics == {}`, `proxy_url == ""`. Consequences: all four governance-part
   metrics unreadable → governance part dropped with reason (`api/grade.py:82-83`), and `sources.proxy_url`
   must be normalized `""` → null (A4).
6. **Snapshot-level absence.** Prebuilt not yet downloaded (startup, download failing):
   `prebuilt.status()` has `built_at == None`, `loaded_at == None` and an `error` (`api/prebuilt.py:33,79-88`).
   Contract's `available: false` + warnings path (line 39) maps directly onto this; do not fabricate rows.

## 6. Low-confidence valuation and negative compensation actually paid (CAP)

- **Low confidence.** `confidence == "low"` when the peer range is >3× wide (`api/valuation.py:47,244,246-248`,
  roughly 1 company in 8 per the comment at `api/valuation.py:242-243`). Existing behavior:
  - the **grade drops the whole value-vs-peers part** (15% weight rescaled onto the rest) with the
    `confidence_note` as the missing reason (`api/grade.py:120-121`);
  - the live fair-value page still shows the estimate with the low-confidence note (`api/valuation.py:247-248`).
  Contract (line 37) requires the same split: row shows `upside_pct` + `valuation_confidence: "low"`, UI labels it
  and must not call it a reliable signal; `grade_score` is already unaffected. No formula change needed.
- **Negative CAP.** `peo_cap` (compensation actually paid) can be negative when the stock falls
  (Super Micro FY2025 −$190M, comment at `api/grade.py:43-44`); `pct` then negative (`api/sec_core.py:730`).
  Existing behavior, kept verbatim:
  - the **grade excludes** negative values from the governance part — only `pct > 0` is placed against the sector
    (`api/grade.py:45-46`), so a negative value is never scored as "efficient pay";
  - the **sector distributions include** negative values (`api/benchmarks.py:45-46` has no positivity filter) —
    an existing asymmetry with the grade. Do **not** "fix" either side: it would be a formula/grade-weight change
    requiring owner sign-off (AGENTS.md, "Changes that need the owner's explicit approval").
  - Contract (line 37) "negative compensation values stay signed and must not be called superior efficiency": the
    screener displays the signed `pct` as-is; sorting is neutral (the contract's sort is an ordering, not a
    ranking), and the UI must not label the lowest value "best". `max_pay_efficiency_pct` filtering passes
    negatives through (they are ≤ any positive cap) — that is correct, they remain visible, not hidden.

## 7. Price and filing dates (what "as of" means)

| Date | Value | As-of semantics |
|---|---|---|
| `price_date` (per row) | close date used for the estimate, `api/valuation.py:157,295-298` | last trading day ≤ prebuild day; differs per company (halts); Yahoo Finance source, embedded at build time (`api/prices.py:10`) |
| `built_at` | `manifest.json` timestamp, `api/prebuild.py:88` | prebuild completion; prices in `valuation.json` are seconds older (`api/prebuild.py:84`) |
| 10-K fiscal year | `fundamentals.json → years[*].fy_end / filed` (`api/sec_core.py:975`) | `filed` = date the numbers first became public; `fy_end` of the valued year is on the valuation row (`api/valuation.py:156`) |
| Proxy | `governance.json → proxy_url / proxy_date` (`api/sec_core.py:513-514`); `pay_efficiency.json → proxy_url / proxy_date / proxy_accn` (`api/sec_core.py:697-699`) | latest DEF 14A at prebuild time |
| Red flags | `red_flags.json → since / checked` (`api/red_flags.py:187-188`) | rolling 3-year window ending at **prebuild** day (`api/red_flags.py:25,180`) |
| Insiders | `insiders.json → from / to` (`api/insiders.py:285`) | rolling 12-month window ending at **prebuild** day (`api/insiders.py:27,263`) |

Consequences:
- Every "recent activity" number (flags, insider totals) is as of the prebuild, not the request time; the page
  must label the snapshot (`built_at`) — the contract's page section already requires this (line 43).
- **No freshness cap on valuation rows in the production build.** `MAX_STALE_DAYS = 550`
  (`api/valuation.py:49`) is enforced only when `as_of` is set (`api/valuation.py:98-99`), i.e. in the back-test;
  the production `build()` passes `day=None` (`api/valuation.py:288-302,423`), so a row's `fy_end` can be
  arbitrarily old. The row carries `fy_end` + `filed`-adjacent dates, so the UI can show the gap — but the
  contract should expect rows whose 10-K year is well over a year old (A8).
- The 10-K **filing date** is not stored in `company.json` (only `tenk_url`, `api/sec_core.py:486`);
  `fundamentals.json → years[-1].filed` (`api/sec_core.py:975`) is the cached place to read it if the UI wants it.
- Fiscal years differ across companies by up to a year (`api/benchmarks.py:4-5` docstring) — pre-existing;
  sector medians are a mix of fiscal years.

## 8. Data coverage limitations (what the snapshot honestly is)

1. **Universe = Russell 1000 ∪ S&P 500** (`api/prebuild.py:37-40`; lists in `api/data/russell1000.csv`,
   `api/data/sp500_tickers.txt`; Russell list refreshed from Wikipedia at prebuild, `prebuild.yml:28-30`).
   Roughly ~1,000 companies — not the whole SEC. The contract's `total: 1000` example (line 17) is consistent.
2. **Per-kind gaps.** Each of the 8 lookups can fail per ticker and is simply absent then
   (`api/prebuild.py:51-53`); the row shows nulls + reasons. A ticker with everything failed is not in
   `manifest["tickers"]` at all (A3).
3. **Valuation row coverage** — a row exists only if: `fundamentals.json` present and not `__unavailable__`
   (`api/valuation.py:414-421`); Yahoo returned a price history (`api/valuation.py:270-285`); the latest 10-K year
   has Revenue and a usable diluted share count (`api/valuation.py:91-101,123-126`). No row → null
   `upside_pct`/`price_date`/`valuation_confidence`, and the grade loses its 15% value part (see B3 for the
   market-cap knock-on).
4. **Sector** null for unmapped SIC codes (`api/sectors.py:74-80`); peers then come from the whole Russell 1000
   (`api/valuation.py:188`) and benchmarks from the `all` group (`api/benchmarks.py:110-112`) — existing behavior.
5. **Proxy-dependent numbers** (3 governance metrics, Pay Efficiency) depend on regex/XBRL extraction from the
   latest DEF 14A; each metric can legitimately be not-found (`api/governance_metrics.py:239`,
   `api/sec_core.py:674-683`) — null, not zero.
6. **Foreign private issuers / funds** file no 10-K → `company.json` is `__unavailable__`
   (`api/sec_core.py:47-48`); they can still appear as rows (red flags/insiders work for any filer,
   `api/red_flags.py:178-190`, `api/insiders.py:260-286`) with all 10-K fields null. That is the honest
   representation the contract asks for.
7. **Third-party price source.** Valuation rows embed Yahoo Finance closes (`api/prices.py:10`,
   `api/valuation.py:53-54`), not SEC data — pre-existing design; the `valuation_source` string says so.
8. **Freshness.** Weekly rebuild + rebuild on changes to the lookup code + manual dispatch
   (`prebuild.yml:7-14`); the API re-downloads within an hour of a new build and at least every 12 h
   (`api/prebuilt.py:29-31,101-114`). Data can be up to ~7+ days old; all as-of dates are the prebuild day (§7).
9. **Peer sanity caveats are stored, not computed.** A row whose filed share count looks out of line
   (`sane == false`, `api/valuation.py:152,160`) or with no tagged debt (`debt == null`, `api/valuation.py:459-460`)
   still gets an estimate; the live `report()` turns those into notes (`api/valuation.py:456-462`) but the
   contract's row schema has no place for notes (A6).

## 9. Cheap caching strategy

Design that reuses existing patterns and stays within "bounded, cached snapshot … invalidate on refresh/file
changes … no repeat whole-universe computation per filter request" (contract line 39):

1. **One in-memory snapshot object**, e.g.
   `{"key": (manifest_built_at, valuation_mtime, benchmarks_mtime), "rows": [per-row contract fields], "sectors": [...], "warnings": [...]}`.
2. **Build inputs, all on disk:** `manifest.json`; the per-ticker files for the 5 kinds the row needs
   (`company`, `governance`, `pay_efficiency`, `red_flags`, `insiders` — `trends`/`risks`/`fundamentals` are not
   needed for any contract field except the A2 `fy_end` fallback); `valuation.json` via `valuation.load`
   (already memory-cached, `api/valuation.py:428-440`), pre-indexed by ticker; `benchmarks.json` via
   `benchmarks.load` (`api/benchmarks.py:84-96`).
3. **Per-ticker computation, once:** `est = valuation.value(row, all_rows)` for tickers with a row;
   `g = grade.build(...)` for every ticker. Everything else is field selection. `grade.build` is trivially cheap;
   `valuation.value` is the cost center: ~N × (distance over ~N candidates + sort) with N ≈ 1,000
   (`api/valuation.py:185-204`) — seconds on a full CPU, **potentially minutes on Render's free tenth of a CPU**
   (context: `api/prebuilt.py:2-6`, `api/main.py:74-78`). Build the snapshot off the request path:
   - on prebuilt load/refresh: the existing `on_refresh` hook already clears all per-company caches
     (`api/main.py:212-214`) — the screener can register the same way (`api/prebuilt.py:32,81-82`) and rebuild in a
     background thread;
   - lazily on the first `/api/screener` hit when the key is stale, behind a single lock, serving
     `available: false` (or the previous snapshot, labeled stale — decision for the builder) while it builds.
   - **Never** recompute per filter/sort/page request: filtering, sorting (nulls last, ticker tie-break),
     pagination and coverage counts all run over the finished row list.
4. **Invalidation.** Key on (manifest `built_at`, `valuation.json` mtime, `benchmarks.json` mtime) — the same
   mtime-keyed pattern as `valuation.load`/`benchmarks.load`. `prebuilt.refresh` swaps the directory atomically
   and fires `_on_refresh` (`api/prebuilt.py:58-88`), so a refresh always produces a new key; a file that changes
   on disk without a refresh is also caught by mtime.
5. **Memory.** `valuation.json` is "tens of MB" (`api/prebuilt.py:62`) and is already held in memory by
   `valuation.load`; the added snapshot (≈1,000 small dicts of precomputed fields) is a few MB — fine against the
   512 MB server (`api/main.py:74-78`).
6. **Unavailable case.** No prebuilt directory / failed download → `available: false`, zero counts, empty rows,
   warnings from `prebuilt.status()["error"]` (`api/prebuilt.py:33,85-88`) — contract line 39.
7. **Suggested QA cross-check (cheap, offline):** point `PREBUILT_DIR` at a downloaded release archive in a test
   and assert: `total == len(manifest["tickers"])`; every non-null row field is reproducible by re-reading the
   source file; `coverage` counts equal non-null counts; a hand-picked company's `grade_score`/`upside_pct`
   match a by-hand recomputation from its files (the AGENTS.md hand-check requirement).

## 10. Contract ambiguities needing a decision (with evidence)

- **A1 — `fy_end` source (blocking for implementation).** The contract shows one `fy_end` per row (line 25) but
  the cache holds up to three candidate values that can disagree: latest 10-K full year from
  `fundamentals.json → years[-1].fy_end` (`api/sec_core.py:983,993`); the valued year
  `valuation.json` row `fy_end` (`api/valuation.py:156`, which steps back one year when the latest year lacks
  Revenue, `api/valuation.py:91-101`); the latest Pay-Versus-Performance year `pay_efficiency.json → fy_end`
  (`api/sec_core.py:684,735`, from the proxy, a different filing). `company.json` offers no clean fiscal-year key
  (`api/sec_core.py:196,495`). Recommendation: `fundamentals.json` latest year first, valuation-row `fy_end` as
  fallback, pay-efficiency `fy_end` last — i.e. "latest 10-K fiscal year, else what could be read". Owner should
  confirm which filing's year the label means.
- **A2 — grade's market cap when there is no valuation row (blocking; see B3).** Decided together with B3.
- **A3 — universe / `total` definition.** `manifest["tickers"]` (≥1 successful lookup) or also
  `manifest["failures"]`-only tickers (all lookups failed, `api/prebuild.py:51-52,88`)? Recommendation:
  `total = len(manifest["tickers"])` — a failures-only ticker has nothing to render. Document the choice in the
  response (e.g. a warning with the failure count).
- **A4 — empty string vs null.** `governance.json → proxy_url` is `""` without a DEF 14A
  (`api/sec_core.py:507,513`); the contract says null with a reason. Normalize `""` → null everywhere in
  `sources` (and `missing` gets the reason).
- **A5 — `valuation_source` granularity.** Contract says "existing valuation source description or null"
  (line 30) — the universe string `valuation.json → source` (`api/valuation.py:53-54`) fits. Per-company
  concept+accession traceability exists in `fundamentals.json → years[*].values[*]` (`api/sec_core.py:946`) if
  row-level links are wanted later; adding them is a schema extension, not a formula change.
- **A6 — no row field for valuation caveats (schema gap).** The live report attaches notes when the row is
  `sane == false` (share count out of line) or `debt == null` (`api/valuation.py:456-462`); both flags are stored
  on the cached row (`api/valuation.py:158-160`) and can be re-checked for free. The contract's row has no `notes`
  field, and these values are **not** "missing", so `missing[]` is the wrong home. Options: add an optional
  per-row `notes` (schema change, owner sign-off), or fold into `warnings` (loses per-row precision), or surface
  in the UI only. Decide before the UI builder starts.
- **A7 — `name` fallback chain (minor).** When `company.json` is absent, use `fundamentals.json → name`
  (same edgartools source, `api/sec_core.py:989`) before `red_flags.json`/`insiders.json → name` (SEC
  ticker→company mapping, `api/red_flags.py:187`, `api/insiders.py:285`).
- **A8 — stale fiscal years are possible (informational).** No `MAX_STALE_DAYS` in the production build path
  (`api/valuation.py:98-99,423`); the UI should show `fy_end` next to `price_date` so the age is visible (§7).
- **A9 — two `built_at` timestamps (informational).** Manifest timestamp (contract's choice, line 16) vs
  `valuation.json` timestamp (`api/prebuild.py:84,88`); seconds apart. Use the manifest one; optionally expose the
  valuation one for the price-date label.

## 11. Accuracy risks flagged (with evidence)

- **B1 — live-fallback trap (blocking if violated).** The existing per-company routes use
  `main.lookup → _lookup`, which falls back to a **live SEC read** when the prebuilt file is absent
  (`api/main.py:132-139,143-184`). The screener must never call those; it must read `prebuilt.get`/raw files and
  treat `None` as missing. Any reuse of `cached_*`/`lookup`/`fair_value`/`company_grade` routes would break the
  "no live calls during screening" rule (contract line 3).
- **B2 — `__unavailable__` sentinel must be checked per file** (`api/prebuild.py:48-49`, pattern
  `api/main.py:136-137`); a sentinel body parsed as data would emit fake numbers.
- **B3 — insiders part of the grade when market cap is unavailable (systematic in the screener).**
  `grade.insiders_part(ins, market_cap)` computes `share = None` when `market_cap` is falsy
  (`api/grade.py:101`) and then falls through to score **50, "nothing unusual (routine or planned selling)"**
  (`api/grade.py:110-111`). The live route only hits this transiently (Yahoo outage, `api/main.py:310-317`); the
  screener hits it for **every company without a valuation row** (coverage gap §8.3), and a heavy unplanned seller
  would display the "nothing unusual" label. Reusing the helper unchanged (contract line 3: "reuse existing pure
  … helpers") preserves the live endpoint's exact behavior — but the label can mislead. Minimum mitigation
  without touching the formula: record in the row's `missing` that "insider-selling thresholds couldn't be
  evaluated (market value unavailable)" so the UI can dim/annotate the grade. Owner decision: keep-as-is + note
  (recommended) vs drop the part when market cap is missing (changes the score relative to the live endpoint —
  effectively a method change needing sign-off).
- **B4 — low-confidence upside must stay labeled** (contract line 37). The data supports it exactly
  (`api/valuation.py:246-248`); risk is UI-only. The grade already excludes low-confidence estimates
  (`api/grade.py:120-121`), so `grade_score` is safe either way.
- **B5 — negative Pay Efficiency must not be presented as "best".** Signed values are stored
  (`api/sec_core.py:730`); the grade already refuses to score them (`api/grade.py:45-46`); the UI must not rank
  them (§6). Sorting per contract is neutral ordering — fine.
- **B6 — do not "fix" the negative-value asymmetry** between benchmark distributions (include negatives,
  `api/benchmarks.py:45-46`) and grade scoring (exclude, `api/grade.py:45-46`): that is an existing
  financial-method property; changing it is owner-only (AGENTS.md approval list).

## 12. Verdict

**Yes — cached data can honestly provide every field in the contract's row schema without network or AI calls**,
using only: the eight per-kind files + `manifest.json` from the prebuilt directory, `valuation.json` (via the
existing `valuation.load`), `benchmarks.json` (via `benchmarks.load`), and the existing pure helpers
`grade.build`, `valuation.value`, `sectors.sector`, `peers.percentile` (plus the disk-backed
`benchmarks.for_company`). Units are consistent (percentage points for both filterable metrics, §3); dates are
cached and label-able (§7); missing/unavailable/corrupt inputs map cleanly to null + reason (§5); low-confidence
and negative-CAP handling already exists and matches the contract (§6).

Conditions before the API builder starts: decisions **A1** (fy_end source), **A3** (universe/`total`), **A6**
(caveat field) and **B3/A2** (insiders-part market-cap exposure); implementation must honor B1 (no live-fallback
code paths) and B2 (sentinel checks). This is a **pre-implementation data audit only**: it is not approval of any
code, and it changes no formula, grade weight, peer rule, red-flag rule, sector mapping or provider setting.
