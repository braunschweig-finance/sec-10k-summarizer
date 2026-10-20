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

DEFAULT = ["CAT", "AAPL", "MSFT", "JPM", "GS", "XOM", "NVDA", "KO", "WMT", "PFE", "META", "BRK-B", "UBER", "BE", "DKS", "ROKU", "C"]


def in_child(fn, ticker):
    """Runs fn(ticker) in a forked child like the API does; returns (result or error, seconds, peak MB)."""
    r, w = os.pipe()
    started = time.time()
    pid = os.fork()
    if pid == 0:
        os.close(r)
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


def nasdaq_close(ticker, day):
    url = f"https://api.nasdaq.com/api/quote/{ticker.replace('-', '.')}/historical"
    r = httpx.get(url, params={"assetclass": "stocks", "fromdate": day, "todate": day, "limit": 5},
                  headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0 Safari/537.36"}, timeout=30)
    rows = ((r.json().get("data") or {}).get("tradesTable") or {}).get("rows") or []
    return float(rows[0]["close"].replace("$", "").replace(",", "")) if rows else None


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

        rs, secs, mb = in_child(sec_core.get_risk_summary, t)
        print(f"risks: {secs:.1f}s, peak {mb:.0f} MB")
        res = rs.get("ok")
        if not res:
            print("  ", rs)
        elif not res["available"]:
            print("   unavailable:", res["reason"])
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
            for y in p["years"]:
                if y["date"]:
                    try:
                        n = nasdaq_close(t, y["date"])
                    except Exception as e:
                        n = repr(e)[:80]
                    ok = isinstance(n, float) and abs(n - y["close"]) / y["close"] < 0.01
                    print(f"   {y['date']}: yahoo {y['close']:.2f} vs nasdaq {n} {'OK' if ok else 'MISMATCH'}")

        pe, secs, mb = in_child(sec_core.get_pay_efficiency, t)
        hist = (pe.get("ok") or {}).get("history")
        print(f"pay efficiency: {secs:.1f}s, peak {mb:.0f} MB; tsr by year:",
              [(h["fy_end"], h.get("tsr"), h.get("peer_tsr")) for h in hist] if hist else pe)

    for t in ["ZZZZQ", "TSM", "SPY"]:
        print(f"\n{t}: company ->", in_child(sec_core.get_financial_report, t)[0])


if __name__ == "__main__":
    main()
