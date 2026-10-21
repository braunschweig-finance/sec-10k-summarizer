"""
Routes for the two AI readers: earnings release tone (/api/earnings-tone/{ticker}) and ask a filing (/api/ask).

Both run on the free Gemini key (or wherever ai_client points), so:
  - the SEC part runs in the API's one-at-a-time child process (main.isolated), like every other filing read;
  - finished answers are kept in memory, keyed by the filing(s) and the model, so a repeat costs no AI call;
  - at most AI_CALLS_PER_MINUTE new AI calls a minute across the whole site, so a burst gets a plain "try again in
    a minute" instead of using up the free-tier quota.
"""
import os
import re
import threading
import time
from collections import OrderedDict, deque

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import ai_client
import ask_filing
import earnings_tone
from sec_core import DataUnavailable

router = APIRouter()

AI_CALLS_PER_MINUTE = int(os.environ.get("AI_CALLS_PER_MINUTE", "8"))
SEC_TTL = 6 * 3600  # how long a company's filing lookup is reused before checking SEC for a newer filing


class Cache:
    """A small in-memory LRU with an optional age limit. A restart clears it."""

    def __init__(self, size, ttl=None):
        self.size, self.ttl, self.items, self.lock = size, ttl, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            hit = self.items.get(key)
            if not hit or (self.ttl and time.time() - hit[0] > self.ttl):
                return None
            self.items.move_to_end(key)
            return hit[1]

    def put(self, key, value):
        with self.lock:
            self.items[key] = (time.time(), value)
            self.items.move_to_end(key)
            while len(self.items) > self.size:
                self.items.popitem(last=False)


_calls = deque()
_calls_lock = threading.Lock()


def take_ai_slot():
    with _calls_lock:
        now = time.time()
        while _calls and now - _calls[0] > 60:
            _calls.popleft()
        if len(_calls) >= AI_CALLS_PER_MINUTE:
            raise HTTPException(429, "The free AI is at its limit for this minute. Try again in a minute; finished answers are kept, so a repeat is instant.")
        _calls.append(now)


def clean_ticker(ticker):
    t = ticker.upper().strip()
    if not t.replace(".", "").replace("-", "").isalnum() or len(t) > 10:
        raise HTTPException(400, "That doesn't look like a ticker symbol.")
    return t


def sec_read(step, fn, ticker):
    """One SEC read in the child process, with the API's usual error messages."""
    from main import _timed, isolated
    try:
        return _timed(step, ticker, lambda t: isolated(fn, t))
    except DataUnavailable as e:
        raise HTTPException(422, f"SEC data unavailable for {ticker}: {e}")
    except Exception as e:
        print(f"[{ticker}] {step} failed: {e!r}", flush=True)
        raise HTTPException(502, f"Couldn't read SEC data for {ticker} ({e}). This is usually temporary, so try again in a minute.")


def ai_key():
    ai = ai_client.describe()
    return ai["provider"], ai["model"]


def ai_errors(fn):
    try:
        return fn()
    except ai_client.AIError as e:
        raise HTTPException(429 if e.busy else 503, str(e))


# ---------- Earnings release tone ----------

_releases = Cache(32, ttl=SEC_TTL)  # ticker -> both releases' text
_tones = Cache(256)                 # (latest accession, prior accession, provider, model) -> result
_tone_locks = {}


@router.get("/api/earnings-tone/{ticker}")
def earnings_tone_route(ticker: str):
    t = clean_ticker(ticker)
    rel = _releases.get(t)
    if rel is None:
        rel = sec_read("earnings releases", earnings_tone.releases, t)
        _releases.put(t, rel)
    base = {"ticker": rel["ticker"], "name": rel["name"], **earnings_tone.public(rel)}
    if not rel["prior"] or not rel["prior"]["narrative"]:
        return {**base, "available": False,
                "reason": "Only one earnings release was found in SEC's recent filings, so there's nothing to compare it with yet."}
    key = (rel["latest"]["accession"], rel["prior"]["accession"]) + ai_key()
    # One AI call per pair of releases: a second identical request waits, then reads the cache
    with _tone_locks.setdefault(key, threading.Lock()):
        hit = _tones.get(key)
        if hit:
            return {**base, "available": True, **hit, "cached": True}
        take_ai_slot()
        result = ai_errors(lambda: earnings_tone.compare(rel))
        _tones.put(key, result)
    return {**base, "available": True, **result, "cached": False}


# ---------- Ask a filing ----------

_tenks = Cache(6, ttl=SEC_TTL)  # ticker -> the 10-K's text (about 0.3-2 MB each)
_answers = Cache(512)           # (accession, question, provider, model) -> answer


class AskRequest(BaseModel):
    ticker: str
    question: str


def normalize_question(q):
    return re.sub(r"\s+", " ", q).strip()


@router.post("/api/ask")
def ask_route(req: AskRequest):
    t = clean_ticker(req.ticker)
    q = normalize_question(req.question)
    if len(q) < 5:
        raise HTTPException(400, "Type a question about the 10-K, for example: How much debt is due next year?")
    if len(q) > ask_filing.MAX_QUESTION:
        raise HTTPException(400, f"Keep the question under {ask_filing.MAX_QUESTION} characters.")
    doc = _tenks.get(t)
    if doc is None:
        doc = sec_read("10-K text", ask_filing.tenk_text, t)
        _tenks.put(t, doc)
    key = (doc["accession"], q.lower().rstrip("?. ")) + ai_key()
    hit = _answers.get(key)
    if hit:
        return {**hit, "question": q, "cached": True}
    take_ai_slot()
    result = ai_errors(lambda: ask_filing.answer(doc, q))
    _answers.put(key, result)
    return {**result, "cached": False}
