# Independent screener contract QA

Scope: `api/tests/test_screener_contract.py` only; no implementation changes. Read the reviewed canonical AGENTS.md and `docs/SCREENER_CONTRACT.md` before writing. No installs, live requests, AI calls, commits, or browser use.

## Execution status (2026-11-08)

**Not executed; no passing behavior claimed.** From `api/`, attempted:

```powershell
python -m pytest tests/test_screener_contract.py -q --tb=short
```

`python` is not on PATH. Retried using the existing canonical checkout's `.venv/Scripts/python.exe`; Windows returned `Access is denied`. No dependencies were installed. Rerun this command with an available Python environment after integration.

Source inspection finds no `/api/screener` route in this worktree's `api/main.py`. Successful-request tests deliberately require HTTP 200, and validation tests require 422. A current 404 therefore fails visibly; no skip, xfail, fake route, or mocked screener result masks missing implementation. Expected missing-route failures have **not** been observed by execution. After integration, any other failure needs investigation against the contract and fixture assumptions.

## Coverage

- Missing, corrupt and sentinel manifests require an unavailable, empty response with zero counts and warnings.
- Corrupt, sentinel and null pay/valuation files must preserve missing values; numeric filters exclude them. Pretax-denominator pay cannot masquerade as operating-income pay.
- Zero and signed negative pay remain numeric. Maximum pay uses 1.18 percentage points; minimum upside uses 50 percentage points. Identical peers at $20 imply 100% upside for an otherwise identical $10 target.
- All six sorts, both directions: nulls last, ascending ticker tie-breaks, including all-null grade scores and tied sectors/pay values.
- Case-insensitive search, exact sector, filter combinations, empty matches, pagination and beyond-end offset. Counts/coverage stay snapshot-wide while matched counts precede pagination.
- Required row/source fields, finite numbers, missing reasons, cached timestamp/date, source URLs, confidence enum, and file-change invalidation.
- Invalid sort/order/grade, pagination bounds/types, nonnumeric and nonfinite numeric queries require 422.

## Fixture provenance and limits

All companies/numbers are synthetic offline test data, not investment data or verified filings. `prebuild.py` supplies the manifest (`built_at`, ticker list, failures) and `__unavailable__` sentinel formats. `sec_core.get_financials` supplies company name/SIC/`tenk_url`; `get_pay_efficiency` supplies `available`, `pct`, denominator, fiscal year and proxy URL. Fundamentals follow `tests/test_valuation.py`'s years/value/concept/accession/URL structure. `valuation.build_row` produces the existing raw peer-row schema in `valuation.json`; fixtures do not invent a cached final valuation report. Source URLs are synthetic SEC-shaped references, not assertions about actual filings.

Five raw valuation rows cover six manifest companies; the sixth has no cached price row. Fiscal dates and prices are fixed. No governance/red-flag/insider caches are supplied, so the existing Company Grade must remain missing (zero grade coverage). Positive grade filtering/score ordering, low-confidence valuation construction, refresh callbacks, cache computation bounds and large-universe performance still require integrated QA; enum checks alone do not validate low-confidence semantics. Minimal company statements are empty because these contract fixtures exercise cached metadata, not statement parsing. Formula correctness remains the responsibility of the existing deterministic unit tests; the hand-checkable identical-peer case only guards screener units/data wiring.

The fixture blocks socket connects/DNS, HTTPX network transports, AI `chat`, and common live cached lookup entry points, before importing the app where possible. Attempted calls are recorded and fail teardown even if application code catches their exceptions. TestClient uses only its in-process transport. Production lifespan is deliberately not entered because it starts the prebuilt download thread; startup/download lifecycle behavior is outside this suite. These guards are defense in depth, not an OS network sandbox.
