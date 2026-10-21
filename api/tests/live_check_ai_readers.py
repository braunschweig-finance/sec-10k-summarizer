"""
Live check of earnings release tone and ask a filing against SEC EDGAR, run by .github/workflows/ai-readers-check.yml
on GitHub's machines (they can reach SEC; Claude's sandbox can't). Prints which releases and 10-K were found, the
text sizes, the word check, the passages each sample question picks, and each read's time and peak memory (the API
server has 512 MB). With GEMINI_API_KEY set it also runs the AI part; with --live it asks the live site instead.

Run from api/:  python tests/live_check_ai_readers.py [--live] [TICKER ...]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

import ai_client
import ask_filing
import earnings_tone as et
from live_check import in_child

DEFAULT = ["CAT", "AAPL", "MSFT", "JPM", "NVDA", "XOM", "C", "BE", "COST", "DE"]
QUESTIONS = ["How much debt is due next year?", "How many employees does the company have?", "Who are the main competitors?"]
LIVE = "https://sec-terminal-api.onrender.com"


def check_sec(t):
    rel, secs, mb = in_child(et.releases, t)
    if "ok" not in rel:
        print(f"  tone: {rel}  ({secs:.0f}s, {mb:.0f} MB)")
    else:
        r = rel["ok"]
        for k in ("latest", "prior"):
            v = r[k]
            if not v:
                print(f"  {k}: none")
                continue
            print(f"  {k}: 8-K filed {v['filed']} period {v['period']}  {v['url']}")
            print(f"      text {len(v['text']):,} chars, narrative {len(v['narrative']):,}, word check {v['word_check']}")
            print(f"      starts: {v['narrative'][:220]!r}")
        print(f"  tone SEC read: {secs:.1f}s, peak {mb:.0f} MB")
        if r["latest"] and r["prior"] and ai_client.describe()["has_key"]:
            out = et.compare(r)
            print(f"  AI: {out['overall']} | guidance {out['guidance']['change']} (quote checked: {out['guidance']['verified']}) | {out['summary']}")
            for s in out["shifts"]:
                print(f"      {s['direction']:<15} {s['topic']:<20} verified={s['verified']}  {s['latest_quote'][:120]}")
    doc, secs, mb = in_child(ask_filing.tenk_text, t)
    if "ok" not in doc:
        print(f"  ask: {doc}  ({secs:.0f}s, {mb:.0f} MB)")
        return
    d = doc["ok"]
    print(f"  10-K filed {d['filed']} period {d['period']}: {len(d['text']):,} chars  ({secs:.1f}s, peak {mb:.0f} MB)  {d['url']}")
    fy = int(d["period"][:4]) if d["period"][:4].isdigit() else None
    for q in QUESTIONS:
        found = ask_filing.excerpts(d["text"], q, fy)
        best = max(found, key=lambda p: ask_filing.search([p], ask_filing.query_terms(q, fy))[0]) if found else ""
        print(f"    Q {q}  ({len(found)} passages)\n      best: {best[:260]!r}")
        if ai_client.describe()["has_key"]:
            a = ask_filing.answer(d, q)
            print(f"      AI: found={a['found']} verified={a['verified']} {a['answer'][:200]}")
            time.sleep(7)  # stay under the free tier's requests per minute


def check_live(t):
    started = time.time()
    r = httpx.get(f"{LIVE}/api/earnings-tone/{t}", timeout=200)
    print(f"  tone {r.status_code} in {time.time() - started:.1f}s")
    if r.status_code == 200:
        b = r.json()
        print(f"    {b.get('latest', {}).get('filed')} vs {(b.get('prior') or {}).get('filed')}: {b.get('overall')} | guidance "
              f"{(b.get('guidance') or {}).get('change')} | {b.get('summary') or b.get('reason')}")
        for s in b.get("shifts") or []:
            print(f"      {s['direction']:<15} {s['topic']:<20} verified={s['verified']}  {s['latest_quote'][:120]}")
    else:
        print(f"    {r.text[:300]}")
    for q in QUESTIONS[:2]:
        started = time.time()
        r = httpx.post(f"{LIVE}/api/ask", json={"ticker": t, "question": q}, timeout=200)
        b = r.json()
        print(f"  ask {r.status_code} in {time.time() - started:.1f}s  {q}")
        print(f"    found={b.get('found')} verified={b.get('verified')} {str(b.get('answer') or b.get('detail'))[:220]}")
        print(f"    quote: {str(b.get('quote'))[:220]}")


if __name__ == "__main__":
    args = sys.argv[1:]
    live = "--live" in args
    tickers = [a.upper() for a in args if a != "--live"] or DEFAULT
    print(f"AI: {ai_client.describe()}  live={live}")
    for t in tickers:
        print(f"\n=== {t}")
        try:
            check_live(t) if live else check_sec(t)
        except Exception as e:
            print(f"  failed: {e!r}")
