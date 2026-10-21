"""
A company's filing list from SEC's submissions file, and a polite SEC fetch, shared by the red flag and insider
lookups (red_flags.py, insiders.py).

SEC asks for at most 10 requests a second from one machine. The weekly prebuild runs several companies at once, so
each process here keeps to SEC_REQUESTS_PER_SECOND (the prebuild sets it low enough that all of them together stay
under SEC's limit), and a "slow down" answer from SEC is retried after a pause.
"""
import json
import os
import threading
import time
from datetime import date

import httpx

import sec_core

RATE = float(os.environ.get("SEC_REQUESTS_PER_SECOND", "5"))
_lock = threading.Lock()
_last = [0.0]


def fetch(url, tries=4):
    """The body of an SEC URL, at most RATE requests a second from this process."""
    for attempt in range(tries):
        with _lock:
            wait = _last[0] + 1 / RATE - time.time()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.time()
        r = httpx.get(url, headers={"User-Agent": sec_core.SEC_IDENTITY}, timeout=60, follow_redirects=True)
        if r.status_code in (403, 429, 503) and attempt < tries - 1:
            time.sleep(2 * (attempt + 1) ** 2)
            continue
        r.raise_for_status()
        return r.content
    raise RuntimeError(f"SEC kept refusing {url}")


def company(ticker):
    """(10-digit CIK, name) for a ticker; DataUnavailable if SEC has no such company."""
    c = sec_core.Company(ticker)
    return str(c.cik).zfill(10), c.name


def filings(cik, since):
    """Every filing the company made on or after `since` (ISO date), newest first, as dicts with form, filed,
    accession, items (8-K item numbers, e.g. "4.01,9.01") and doc (primary document name).

    The submissions file lists at least the last year (or 1,000 filings); older ones are in extra pages, read only
    when they reach back past `since`. Banks that file thousands of note prospectuses have one page per month."""
    body = json.loads(fetch(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    pages = [body["filings"]["recent"]]
    for extra in body["filings"].get("files", []):
        if extra.get("filingTo", "") >= since:
            pages.append(json.loads(fetch(f"https://data.sec.gov/submissions/{extra['name']}")))
    out = []
    for p in pages:
        for i, filed in enumerate(p["filingDate"]):
            if filed >= since:
                out.append({"form": p["form"][i], "filed": filed, "accession": p["accessionNumber"][i],
                            "items": p["items"][i] if "items" in p else "", "doc": p["primaryDocument"][i]})
    out.sort(key=lambda f: f["filed"], reverse=True)
    return body.get("name") or "", out


def folder(cik, accession):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"


def index_url(cik, accession):
    """The filing's index page on EDGAR, which lists every document in it."""
    return folder(cik, accession) + f"{accession}-index.htm"


def years_ago(n, today=None):
    t = today or date.today()
    try:
        return t.replace(year=t.year - n).isoformat()
    except ValueError:  # 29 February
        return t.replace(year=t.year - n, day=28).isoformat()
