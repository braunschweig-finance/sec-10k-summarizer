"""
Small web API for the redesigned site. Runs the same SEC logic as the Streamlit app and returns JSON.

Run locally:  uvicorn main:app --reload   (from the api/ folder)
"""
import multiprocessing
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

import ai_client
import ai_routes
import benchmarks
import export
import governance_policies
import prebuilt
import prices
import sec_core
import valuation
from sec_core import DataUnavailable

app = FastAPI(title="SEC Financial & Corporate Governance Terminal API")

# An unexpected error inside a route returns a plain JSON message. Added before the CORS middleware so it runs
# inside it: otherwise the error reply has no CORS headers and the browser only sees "Failed to fetch".
@app.middleware("http")
async def unexpected_errors(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        print(f"[{request.url.path}] unexpected error: {e!r}", flush=True)
        return JSONResponse({"detail": f"The data server hit an unexpected error: {e}"}, status_code=500)


# The web site lives on a different address (Vercel), so the browser needs permission to call this API.
# ALLOWED_ORIGINS is an optional comma-separated list, e.g. "https://sec-terminal.vercel.app". Left blank
# (Render's blueprint creates it empty), any site may call the API. Any *.vercel.app address is always
# allowed, since Vercel gives each deploy its own address.
allowed = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed,
    allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Earnings release tone and ask a filing (see ai_routes.py)
app.include_router(ai_routes.router)


def _timed(step, ticker, fn):
    # Errors raise and are not cached, so a temporary SEC outage doesn't stick
    started = time.time()
    print(f"[{ticker}] {step}: fetching from SEC EDGAR", flush=True)
    result = fn(ticker)
    print(f"[{ticker}] {step}: done in {time.time() - started:.1f}s", flush=True)
    return result


# Each SEC lookup runs in its own short-lived child process, one at a time. Reading a large filer takes a lot of
# memory (Citigroup's 10-K alone needs about 300 MB on top of the app's 215 MB, and the free plan has 512 MB), and
# Python keeps memory it has used. Before this, one big company in the server process meant Render restarted the
# whole server mid-request. Now the child hands its memory back when it exits, and if a filing is too big, the
# system stops only that child (it volunteers via oom_score_adj) and the page gets a plain explanation.
_fork = multiprocessing.get_context("fork")
_child_slot = threading.Semaphore(1)
CHILD_LIMIT = 120  # seconds; a stuck child is stopped so it can't hold the slot forever


def _child(fn, ticker, conn):
    # Another thread may have been mid-print when this process was copied, leaving the copy's stdout lock held
    # forever. Fresh stdout/stderr objects have their own locks.
    sys.stdout = open(1, "w", buffering=1, closefd=False)
    sys.stderr = open(2, "w", buffering=1, closefd=False)
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("1000")
    except OSError:
        pass
    try:
        conn.send(("ok", fn(ticker)))
    except DataUnavailable as e:
        conn.send(("unavailable", str(e)))
    except Exception as e:
        conn.send(("error", str(e) or repr(e)))
    finally:
        conn.close()


def isolated(fn, ticker):
    with _child_slot:
        recv, send = _fork.Pipe(duplex=False)
        proc = _fork.Process(target=_child, args=(fn, ticker, send))
        proc.start()
        send.close()
        try:
            if not recv.poll(CHILD_LIMIT):
                proc.kill()
                raise RuntimeError(f"the lookup was stopped after {CHILD_LIMIT} seconds")
            status, payload = recv.recv()
        except EOFError:
            proc.join()
            if proc.exitcode == -9:
                raise RuntimeError("this filing is too large for the free server's memory (512 MB), so it can't be read here")
            raise RuntimeError(f"the lookup stopped unexpectedly (exit code {proc.exitcode})")
        finally:
            recv.close()
        proc.join()
    if status == "unavailable":
        raise DataUnavailable(payload)
    if status == "error":
        raise RuntimeError(payload)
    return payload


def _lookup(kind, step, fn, ticker):
    """The ready-made result when there is one (Russell 1000 and S&P 500 companies, see prebuilt.py), otherwise a live read."""
    ready = prebuilt.get(kind, ticker)
    if ready is not None:
        if "__unavailable__" in ready:
            raise DataUnavailable(ready["__unavailable__"])
        return ready
    return _timed(step, ticker, lambda t: isolated(fn, t))


# The 10-K and the proxy are separate requests, so ratios show up without waiting for the (slower) proxy
@lru_cache(maxsize=64)
def cached_financials(ticker):
    return _lookup("company", "10-K", sec_core.get_financial_report, ticker)


@lru_cache(maxsize=64)
def cached_governance(ticker):
    return _lookup("governance", "DEF 14A", sec_core.get_governance_report, ticker)


@lru_cache(maxsize=64)
def cached_pay_efficiency(ticker):
    return _lookup("pay_efficiency", "Pay Efficiency", sec_core.get_pay_efficiency, ticker)


@lru_cache(maxsize=64)
def cached_trends(ticker):
    return _lookup("trends", "Trends", sec_core.get_trends, ticker)


@lru_cache(maxsize=64)
def cached_risks(ticker):
    return _lookup("risks", "Risk factors", sec_core.get_risk_summary, ticker)


@lru_cache(maxsize=64)
def cached_fundamentals(ticker):
    return _lookup("fundamentals", "Valuation inputs", sec_core.get_valuation_inputs, ticker)


CACHES = (cached_financials, cached_governance, cached_pay_efficiency, cached_trends, cached_risks, cached_fundamentals)


# SEC lookups run in worker threads so a slow or stuck one returns an error instead of hanging the page
_pool = ThreadPoolExecutor(max_workers=4)
SEC_TIMEOUT = int(os.environ.get("SEC_TIMEOUT_SECONDS", "90"))


def lookup(fn, ticker):
    """Runs one cached SEC lookup with the time limit. A lookup that times out keeps running in the
    background and lands in the cache, so trying again a minute later is fast."""
    ticker = ticker.upper().strip()
    if not ticker.replace(".", "").replace("-", "").isalnum() or len(ticker) > 10:
        raise HTTPException(400, "That doesn't look like a ticker symbol.")
    try:
        return _pool.submit(fn, ticker).result(timeout=SEC_TIMEOUT)
    except DataUnavailable as e:
        # Not a server problem: SEC simply has no such data for this ticker. Not cached by lru_cache (it raised).
        print(f"[{ticker}] unavailable: {e}", flush=True)
        raise HTTPException(422, f"SEC data unavailable for {ticker}: {e}")
    except FutureTimeout:
        print(f"[{ticker}] timed out after {SEC_TIMEOUT}s", flush=True)
        raise HTTPException(504, f"SEC EDGAR took longer than {SEC_TIMEOUT} seconds for {ticker}. It keeps working in the background, so try again in a minute.")
    except Exception as e:
        print(f"[{ticker}] failed: {e!r}", flush=True)
        raise HTTPException(502, f"Couldn't read SEC data for {ticker} ({e}). This is usually temporary, so try again in a minute.")


@app.on_event("startup")
def load_prebuilt():
    prebuilt.start(on_refresh=lambda: [f.cache_clear() for f in CACHES])


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/prebuilt-status")
def prebuilt_status():
    return prebuilt.status()


@app.get("/api/sec-check")
def sec_check():
    """One direct request to SEC EDGAR, to tell a blocked or throttled server apart from a slow one."""
    import httpx
    url = "https://data.sec.gov/submissions/CIK0000018230.json"  # Caterpillar's filing index
    started = time.time()
    try:
        r = httpx.get(url, headers={"User-Agent": sec_core.SEC_IDENTITY}, timeout=15)
        result = {"status": r.status_code, "seconds": round(time.time() - started, 2), "bytes": len(r.content)}
        if r.status_code != 200:
            result["body_start"] = r.text[:300]
    except Exception as e:
        result = {"error": repr(e), "seconds": round(time.time() - started, 2)}
    print(f"[sec-check] {result}", flush=True)
    return result


@app.get("/api/company/{ticker}")
def company(ticker: str):
    report = lookup(cached_financials, ticker)
    # Sector medians come from the ready-made Russell 1000 results, so they cost nothing to add here
    return {**report, "benchmark": benchmarks.for_company(report.get("sic"), prebuilt.benchmarks_path())}


@app.get("/api/governance/{ticker}")
def governance(ticker: str):
    return lookup(cached_governance, ticker)


@app.get("/api/pay-efficiency/{ticker}")
def pay_efficiency(ticker: str):
    return lookup(cached_pay_efficiency, ticker)


@app.get("/api/trends/{ticker}")
def trends(ticker: str):
    return lookup(cached_trends, ticker)


@app.get("/api/risks/{ticker}")
def risks(ticker: str):
    return lookup(cached_risks, ticker)


_quotes = {}  # ticker -> (fetched at, price, date); a fresh close every 15 minutes at most
QUOTE_SECONDS = 15 * 60


def latest_close(ticker):
    """(the latest close as traded, its date) from Yahoo Finance, or (None, None) if Yahoo doesn't answer."""
    hit = _quotes.get(ticker)
    if hit and time.time() - hit[0] < QUOTE_SECONDS:
        return hit[1], hit[2]
    from datetime import date, timedelta
    try:
        h = prices.history(ticker, date.today() - timedelta(days=10), date.today())
    except Exception as e:
        print(f"[{ticker}] latest price unavailable: {e!r}", flush=True)
        return None, None
    if not h["days"]:
        return None, None
    i = len(h["days"]) - 1
    _quotes[ticker] = (time.time(), prices.raw_close(h, i), h["days"][i].isoformat())
    return _quotes[ticker][1], _quotes[ticker][2]


@app.get("/api/valuation/{ticker}")
def fair_value(ticker: str):
    fund = lookup(cached_fundamentals, ticker)
    universe = valuation.load(prebuilt.valuation_path())
    if not universe:
        raise HTTPException(503, "The peer data for fair value isn't loaded yet (it comes with the weekly ready-made data). Try again in a few minutes.")
    t = fund["ticker"]
    price, day = latest_close(t)
    price_note = "Latest close from Yahoo Finance, as traded."
    if price is None:
        row = next((r for r in universe["rows"] if r["ticker"] == t), None)
        if not row:
            raise HTTPException(502, f"Yahoo Finance didn't return a share price for {t}, so it can't be compared with a fair value.")
        price, day, price_note = row["price"], row["price_date"], "Yahoo Finance didn't answer just now, so this is the close from the weekly data build."
    return valuation.report(fund, price, day, universe, price_note)


def full_report(ticker):
    return {**company(ticker), "governance": governance(ticker)}


class MemoRequest(BaseModel):
    ticker: str


def memo_prompt(r):
    ratios = r["ratios"]
    gov = r["governance"]
    governance_text = "\n\n".join(f"{k}:\n{v}" for k, v in gov["sections"].items())
    governance_flags = "\n".join(f"- {k}: {'discussed' if v else 'not found'}" for k, v in gov["checks"].items())
    return f"""
    You are a senior equity research analyst preparing an institutional investment and corporate governance memo.
    Company: {r['name']} ({r['ticker']})

    AUDITED 10-K QUANTITATIVE METRICS:
    - Gross Margin: {ratios['Gross Margin']}
    - Operating Margin: {ratios['Operating Margin']}
    - Current Ratio: {ratios['Current Ratio']}
    - Balance Sheet Leverage (Total Liabilities / Equity): {ratios['Total Liabilities-to-Equity']}

    DEF 14A PROXY CORPORATE GOVERNANCE DISCLOSURES:
    {governance_flags}

    {governance_text[:6000]}

    DELIVERABLES:
    Structure your memo in clean Markdown matching an institutional investment committee brief.
    Use only the figures and disclosures above; if something is not provided, say it was not disclosed.
    1. Executive Summary & Financial Quality (Evaluate core profitability, operating margin resilience, liquidity, and balance sheet leverage).
    2. Corporate Governance Evaluation (Analyze executive compensation alignment, CEO-to-median employee pay ratio, board of directors committee independence, and lead independent director safeguards).
    3. Annual Meeting & Shareholder Proposals (Review proposals submitted for shareholder vote, management recommendations, and shareholder rights).
    4. Strategic Capital Allocation & Risk Verdict (Assess CapEx, share repurchases, dividend coverage, and governance risk score).
    """


# Finished memos, keyed by ticker + the filings they were written from, so a repeat request skips Gemini.
# A new 10-K or proxy gives a new key. In memory only, so a restart clears it.
_memos = OrderedDict()
_memos_lock = threading.Lock()
_memo_key_locks = {}
MEMO_CACHE_SIZE = 200


def filing_id(url):
    # The accession number (e.g. 0000018230-24-000012) names the filing; fall back to the URL itself
    m = re.search(r"(\d{10}-\d{2}-\d{6})", url or "") or re.search(r"/(\d{18})/", url or "")
    return m.group(1) if m else (url or "")


def memo_key(report):
    return (report["ticker"], filing_id(report.get("tenk_url")), filing_id(report["governance"].get("proxy_url")))


@app.post("/api/memo")
def memo(req: MemoRequest):
    report = full_report(req.ticker)
    ai = ai_client.describe()
    # The model is part of the key, so switching where the AI runs doesn't serve an old model's memo
    key = memo_key(report) + (ai["provider"], ai["model"])

    with _memos_lock:
        key_lock = _memo_key_locks.setdefault(key, threading.Lock())
    # One AI call per key: a second identical request waits here, then reads the cache
    with key_lock:
        with _memos_lock:
            if key in _memos:
                _memos.move_to_end(key)
                print(f"[{key[0]}] memo: served from cache", flush=True)
                return {**_memos[key], "cached": True}
        result = write_memo(report)
        with _memos_lock:
            _memos[key] = result
            while len(_memos) > MEMO_CACHE_SIZE:
                old, _ = _memos.popitem(last=False)
                _memo_key_locks.pop(old, None)
    return {**result, "cached": False}


def write_memo(report):
    try:
        reply = ai_client.chat(memo_prompt(report))
    except ai_client.AIError as e:
        raise HTTPException(429 if e.busy else 503, str(e))
    return {"text": reply["text"], "usage": reply["usage"], "model": reply["model"]}


@app.get("/api/ai-status")
def ai_status():
    """Which AI the server is set to use (provider, address, model). The key itself is never shown."""
    return ai_client.describe()


_policies = OrderedDict()


@app.get("/api/governance-policies/{ticker}")
def governance_policies_route(ticker: str):
    """Ten governance policies read from the proxy by the AI, each with a quote checked against the filing.
    About ten AI calls per company, so results are kept in memory."""
    ticker = ticker.strip().upper()
    ai = ai_client.describe()
    key = (ticker, ai["provider"], ai["model"])
    if key in _policies:
        return {**_policies[key], "cached": True}
    try:
        result = _timed("governance policies", ticker, governance_policies.get_governance_policies)
    except DataUnavailable as e:
        raise HTTPException(422, str(e))
    except ai_client.AIError as e:
        raise HTTPException(429 if e.busy else 503, str(e))
    _policies[key] = result
    while len(_policies) > 64:
        _policies.popitem(last=False)
    return {**result, "cached": False}


class DocxRequest(BaseModel):
    ticker: str
    memo: str


@app.post("/api/memo.docx")
def memo_docx(req: DocxRequest):
    report = full_report(req.ticker)
    data = sec_core.build_word_memo(report["ticker"], report["name"], report["ratios"],
                                    report["governance"]["sections"], req.memo)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{report["ticker"]}_Institutional_Research_Brief.docx"'},
    )


def export_data(ticker):
    """Everything the export files show, from the same cached lookups as the page. A part that fails is left out and noted."""
    data = {"report": company(ticker), "notes": []}
    for key, fn in [("pay_efficiency", pay_efficiency), ("trends", trends)]:
        try:
            data[key] = fn(ticker)
        except HTTPException as e:
            data[key] = None
            data["notes"].append(f"{key.replace('_', ' ').title()} left out: {e.detail}")
    return data


@app.get("/api/export/{ticker}.xlsx")
def export_xlsx(ticker: str):
    data = export_data(ticker)
    t = data["report"]["ticker"]
    return Response(
        content=export.build_xlsx(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{t}_SEC_Terminal.xlsx"'},
    )


@app.get("/api/export/{ticker}.pdf")
def export_pdf(ticker: str):
    data = export_data(ticker)
    t = data["report"]["ticker"]
    return Response(
        content=export.build_pdf(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{t}_SEC_Terminal.pdf"'},
    )
