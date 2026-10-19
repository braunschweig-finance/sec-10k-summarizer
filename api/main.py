"""
Small web API for the redesigned site. Runs the same SEC logic as the Streamlit app and returns JSON.

Run locally:  uvicorn main:app --reload   (from the api/ folder)
"""
import os
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

import sec_core

app = FastAPI(title="SEC Financial & Corporate Governance Terminal API")

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


def _timed(step, ticker, fn):
    # Errors raise and are not cached, so a temporary SEC outage doesn't stick
    started = time.time()
    print(f"[{ticker}] {step}: fetching from SEC EDGAR", flush=True)
    result = fn(ticker)
    print(f"[{ticker}] {step}: done in {time.time() - started:.1f}s", flush=True)
    return result


# The 10-K and the proxy are separate requests, so ratios show up without waiting for the (slower) proxy
@lru_cache(maxsize=64)
def cached_financials(ticker):
    return _timed("10-K", ticker, sec_core.get_financial_report)


@lru_cache(maxsize=64)
def cached_governance(ticker):
    return _timed("DEF 14A", ticker, sec_core.get_governance_report)


@lru_cache(maxsize=64)
def cached_pay_efficiency(ticker):
    return _timed("Pay Efficiency", ticker, sec_core.get_pay_efficiency)


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
    except FutureTimeout:
        print(f"[{ticker}] timed out after {SEC_TIMEOUT}s", flush=True)
        raise HTTPException(504, f"SEC EDGAR took longer than {SEC_TIMEOUT} seconds for {ticker}. It keeps working in the background, so try again in a minute.")
    except Exception as e:
        print(f"[{ticker}] failed: {e!r}", flush=True)
        raise HTTPException(502, f"Couldn't fetch SEC data for {ticker}: {e}")


@app.get("/health")
def health():
    return {"ok": True}


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
    return lookup(cached_financials, ticker)


@app.get("/api/governance/{ticker}")
def governance(ticker: str):
    return lookup(cached_governance, ticker)


@app.get("/api/pay-efficiency/{ticker}")
def pay_efficiency(ticker: str):
    return lookup(cached_pay_efficiency, ticker)


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
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(503, "GEMINI_API_KEY is not set on the API server.")
    report = full_report(req.ticker)
    key = memo_key(report)

    with _memos_lock:
        key_lock = _memo_key_locks.setdefault(key, threading.Lock())
    # One Gemini call per key: a second identical request waits here, then reads the cache
    with key_lock:
        with _memos_lock:
            if key in _memos:
                _memos.move_to_end(key)
                print(f"[{key[0]}] memo: served from cache", flush=True)
                return {**_memos[key], "cached": True}
        result = write_memo(api_key, report)
        with _memos_lock:
            _memos[key] = result
            while len(_memos) > MEMO_CACHE_SIZE:
                old, _ = _memos.popitem(last=False)
                _memo_key_locks.pop(old, None)
    return {**result, "cached": False}


def write_memo(api_key, report):
    from google import genai
    client = genai.Client(api_key=api_key)
    response, last_error = None, None
    # Same retry rule as app.py: a 429 moves to the next model instead of retrying
    for model_name in ["gemini-3.8-flash", "gemini-3.6-flash"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model_name, contents=memo_prompt(report))
                break
            except Exception as err:
                last_error = err
                if attempt == 0 and ("503" in str(err) or "UNAVAILABLE" in str(err)):
                    time.sleep(3)
                    continue
                break
        if response:
            break

    if not response:
        if "429" in str(last_error) or "RESOURCE_EXHAUSTED" in str(last_error):
            raise HTTPException(429, "The AI writer is busy (free-tier limit). Try again in a minute.")
        raise HTTPException(502, f"Failed to generate memo: {last_error}")

    usage = None
    if getattr(response, "usage_metadata", None):
        usage = {"input": response.usage_metadata.prompt_token_count, "output": response.usage_metadata.candidates_token_count}
    return {"text": response.text, "usage": usage}


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
