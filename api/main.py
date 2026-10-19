"""
Small web API for the redesigned site. Runs the same SEC logic as the Streamlit app and returns JSON.

Run locally:  uvicorn main:app --reload   (from the api/ folder)
"""
import os
import time
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

import sec_core

app = FastAPI(title="SEC Financial & Corporate Governance Terminal API")

# The web site lives on a different address (Vercel), so the browser needs permission to call this API.
# ALLOWED_ORIGINS is a comma-separated list, e.g. "https://sec-terminal.vercel.app"
allowed = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=allowed, allow_methods=["GET", "POST"], allow_headers=["*"])


@lru_cache(maxsize=64)
def cached_report(ticker):
    # Errors raise and are not cached, so a temporary SEC outage doesn't stick
    return sec_core.get_company_report(ticker)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/company/{ticker}")
def company(ticker: str):
    ticker = ticker.upper().strip()
    if not ticker.replace(".", "").replace("-", "").isalnum() or len(ticker) > 10:
        raise HTTPException(400, "That doesn't look like a ticker symbol.")
    try:
        return cached_report(ticker)
    except Exception as e:
        raise HTTPException(502, f"Couldn't fetch SEC data for {ticker}: {e}")


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


@app.post("/api/memo")
def memo(req: MemoRequest):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(503, "GEMINI_API_KEY is not set on the API server.")
    report = company(req.ticker)

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
            raise HTTPException(429, "Gemini rate limit reached (free-tier requests-per-minute cap). Wait a minute and try again.")
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
    report = company(req.ticker)
    data = sec_core.build_word_memo(report["ticker"], report["name"], report["ratios"],
                                    report["governance"]["sections"], req.memo)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{report["ticker"]}_Institutional_Research_Brief.docx"'},
    )
