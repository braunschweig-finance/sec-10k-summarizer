"""
Live check of the new lookups against SEC EDGAR, run by .github/workflows/feature-check.yml on GitHub's machines.
Prints each extracted number with its evidence sentence so it can be checked against the filing by eye, the peak
memory of each lookup (the API server has 512 MB), and cross-checks Yahoo's year-end closes against Nasdaq's.

Run from api/:  python tests/live_check.py [TICKER ...]
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import sec_core

DEFAULT = ["CAT", "AAPL", "MSFT", "JPM", "XOM", "NVDA", "PFE", "META", "BRK-B", "UBER", "BE", "DKS", "ROKU", "C", "HD", "LLY", "COST", "ADBE", "DE"]


def in_child(fn, ticker):
    """Runs fn(ticker) in a forked child like the API does; returns (result or error, seconds, peak MB)."""
    r, w = os.pipe()
    started = time.time()
    sys.stdout.flush()  # or the child inherits unprinted lines and prints them again
    pid = os.fork()
    if pid == 0:
        os.close(r)
        import signal
        signal.alarm(150)  # the API stops a lookup after 120 s; a stuck one here shouldn't hang the whole check
        try:
            out = {"ok": fn(ticker)}
        except sec_core.DataUnavailable as e:
            out = {"unavailable": str(e)}
        except Exception as e:
            out = {"error": repr(e)[:300]}
        with os.fdopen(w, "w") as f:
            json.dump(out, f, default=str)
        os._exit(0)
    os.close(w)
    with os.fdopen(r) as f:
        body = f.read()
    _, _, usage = os.wait4(pid, 0)
    return json.loads(body or '{"error": "child died"}'), time.time() - started, usage.ru_maxrss / 1024


def nasdaq_closes(ticker, first, last):
    """{iso date: close} from Nasdaq's historical quotes, the independent source the Yahoo prices are checked against."""
    url = f"https://api.nasdaq.com/api/quote/{ticker.replace('-', '.')}/historical"
    r = httpx.get(url, params={"assetclass": "stocks", "fromdate": first, "todate": last, "limit": 9999},
                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                           "Accept": "application/json"}, timeout=30)
    rows = ((r.json().get("data") or {}).get("tradesTable") or {}).get("rows") or []
    return {f"{x['date'][6:10]}-{x['date'][0:2]}-{x['date'][3:5]}": float(x["close"].replace("$", "").replace(",", "")) for x in rows}


def debug_misses(ticker, metrics):
    """For a number that wasn't found, the proxy sentences that came closest, to see how this filer words it."""
    import re
    import governance_metrics as gm
    from edgar import Company
    misses = [k for k, v in metrics.items() if not v or (k == "Board Independence" and v.get("pct") is None)]
    if not misses:
        return
    proxy = sec_core.latest_filings(Company(ticker), "DEF 14A")[0]
    flat = sec_core.clean_governance_text(sec_core.get_proxy_text(proxy)[0])
    probes = {"CEO Pay Ratio": (r"ratio", r"median"), "Board Independence": (r"\bindependent\b", r"director|nominee"),
              "Say-on-Pay Support": (r"say[- ]on[- ]pay|votes cast", r"%")}
    for k in misses:
        a, b = probes[k]
        hits = [s for _, s in gm.sentences(flat) if re.search(a, s, re.I) and re.search(b, s, re.I) and len(s) < 450
                and not re.search(r"lead independent director|independent (?:registered|auditor|accounting)", s, re.I)][:5]
        for h in hits:
            print(f"      ? {k}: {h[:260]}")


def debug_risks(ticker):
    """Why Item 1A gave no headings: whether the section was found, how long it is, and what its emphasized lines look like."""
    import risk_factors as rf
    from edgar import Company
    filing = sec_core.annual_reports(Company(ticker))[0]
    html = sec_fetch_doc = sec_core.sec_fetch(sec_core.primary_doc_url(filing))
    heads = [(m.start(), m.group(1)) for m in rf.ITEM.finditer(html)]
    print(f"      ? doc {len(html):,} bytes; Item mentions {len(heads)}; heading-like {[(p, i.decode()) for p, i in heads if rf._is_heading(html, p)][:14]}")
    frag = rf.item_1a_html(html)
    if not frag:
        for p, i in heads[:6]:
            print(f"      ? mention {i.decode()} at {p}: {html[max(0, p - 150):p + 80]!r}"[:330])
        return
    rows = rf.blocks(frag)
    print(f"      ? Item 1A fragment {len(frag):,} chars, {len(rows)} blocks, {sum(1 for r in rows if r[1])} emphasized, {sum(1 for r in rows if r[2])} run-in")
    for text, emph, lead in rows[:40]:
        if emph or lead or len(text) < 200:
            print(f"      ? [{''.join(sorted(emph)) or '-'}] {(lead or text)[:150]}")
    i = frag.find("isk")
    print("      ? raw:", repr(frag[:1200]))


def main():
    tickers = sys.argv[1:] or DEFAULT
    for t in tickers:
        print(f"\n================ {t} ================", flush=True)
        g, secs, mb = in_child(sec_core.get_governance_report, t)
        print(f"governance: {secs:.1f}s, peak {mb:.0f} MB")
        for name, m in ((g.get("ok") or {}).get("metrics") or {}).items():
            print(f"  {name}: {json.dumps({k: v for k, v in m.items() if k != 'evidence'}) if m else 'NOT FOUND'}")
            if m:
                print(f"      \"{m['evidence'][:400]}\"")
        if "ok" not in g:
            print("  ", g)
        else:
            debug_misses(t, g["ok"]["metrics"])

        rs, secs, mb = in_child(sec_core.get_risk_summary, t)
        print(f"risks: {secs:.1f}s, peak {mb:.0f} MB")
        res = rs.get("ok")
        if not res:
            print("  ", rs)
        elif not res["available"]:
            print("   unavailable:", res["reason"])
            debug_risks(t)
        else:
            print(f"   {res['count']} risks, {res['words']} words, {len(res['categories'])} categories; changes {res['changes']}; "
                  f"prior {res['prior'] and (res['prior']['count'], res['prior']['words'])}")
            print("   categories:", res["categories"][:6])
            for r in res["risks"][:4]:
                print(f"   - [{r.get('status')}] {r['title'][:160]}")
            for r in [r for r in res["risks"] if r.get("status") == "new"][:3]:
                print(f"   + NEW {r['title'][:160]}")
            for r in [r for r in res["risks"] if r.get("status") == "reworded"][:2]:
                print(f"   ~ REWORDED {r['title'][:120]}\n       was {r['prior_title'][:120]}")
            for x in res["removed"][:3]:
                print(f"   - REMOVED {x[:160]}")

        tr, secs, mb = in_child(sec_core.get_trends, t)
        print(f"trends: {secs:.1f}s, peak {mb:.0f} MB")
        p = (tr.get("ok") or {}).get("prices")
        print("   prices:", json.dumps(p)[:600] if p else tr)
        if p and p.get("available"):
            days = [y["date"] for y in p["years"] if y["date"]]
            try:
                nq = nasdaq_closes(t, min(days), max(days))
            except Exception as e:
                nq, err = {}, repr(e)[:120]
                print("   nasdaq failed:", err)
            for y in p["years"]:
                if y["date"]:
                    n = nq.get(y["date"])
                    ok = n is not None and abs(n - y["close"]) / y["close"] < 0.005
                    print(f"   {y['date']}: yahoo {y['close']:.2f} vs nasdaq {n} {'OK' if ok else 'MISMATCH'}")

        pe, secs, mb = in_child(sec_core.get_pay_efficiency, t)
        hist = (pe.get("ok") or {}).get("history")
        print(f"pay efficiency: {secs:.1f}s, peak {mb:.0f} MB; tsr by year:",
              [(h["fy_end"], h.get("tsr"), h.get("peer_tsr")) for h in hist] if hist else pe)

    for t in ["ZZZZQ", "TSM", "SPY"]:
        print(f"\n{t}: company ->", in_child(sec_core.get_financial_report, t)[0])


if __name__ == "__main__":
    main()
