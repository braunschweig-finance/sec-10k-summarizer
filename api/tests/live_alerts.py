"""
Live check of the red flag and insider lookups against SEC EDGAR, run by .github/workflows/feature-check.yml on
GitHub's machines. Prints every flag with its quote and each company's insider totals so they can be checked against
the filings by eye, the time and peak memory of each lookup (the API server has 512 MB), and cross-checks the two
insider sources: the totals from SEC's quarterly data sets must match the totals from reading each Form 4's XML.

Run from api/:  python tests/live_alerts.py [TICKER ...]
"""
import json
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import insiders
import red_flags
from live_check import in_child

DEFAULT = ["CAT", "AAPL", "MSFT", "JPM", "TSLA", "SMCI", "BA", "INTC", "NKE", "WBA", "BE", "DKS", "ROKU", "KHC"]


def money(v):
    return f"${v:,.0f}"


def main():
    tickers = [t.upper() for t in sys.argv[1:]] or DEFAULT
    os.environ.pop(insiders.BULK_DIR, None)
    live = {}
    for t in tickers:
        out, secs, mb = in_child(red_flags.get_red_flags, t)
        print(f"\n=== {t} red flags ({secs:.1f}s, peak {mb:.0f} MB)")
        if "ok" not in out:
            print("  ", out)
        else:
            r = out["ok"]
            print(f"   {r['filings_checked']} filings since {r['since']}: {r['counts'] or 'none'}")
            for f in r["flags"]:
                print(f"   - {f['filed']} {f['flag']} [{f['severity']}] {f['url']}\n       {f['quote'] or f['detail']}")
        out, secs, mb = in_child(insiders.get_insider_trades, t)
        print(f"=== {t} insiders, live ({secs:.1f}s, peak {mb:.0f} MB)")
        if "ok" not in out:
            print("  ", out)
            continue
        s = live[t] = out["ok"]
        print(f"   {s['form4_count']} Form 4s from {s['from']}{' (capped)' if s['capped'] else ''}; {s['signal']}")
        print(f"   buys {s['buys']['count']} by {s['buys']['insiders']} = {money(s['buys']['value'])}; sells {s['sells']['count']} = "
              f"{money(s['sells']['value'])} ({money(s['planned_sells']['value'])} under 10b5-1); net {money(s['net_value'])}")
        for g in s["purchases"][:5]:
            print(f"   BUY  {g['last']} {g['insider']} ({g['role']}) {g['shares']:,.0f} sh @ ${g['avg_price']} = {money(g['value'])} {g['url']}")
        for g in s["top_sales"][:3]:
            print(f"   SELL {g['last']} {g['insider']} ({g['role']}) {g['shares']:,.0f} sh @ ${g['avg_price']} = {money(g['value'])}{' 10b5-1' if g['plan'] else ''}")

    print("\n=== Quarterly data sets vs Form 4 XML")
    started = time.time()
    meta = insiders.prepare_bulk("/tmp/insider_bulk")
    print(f"   prepared in {time.time() - started:.0f}s, peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB: {meta}")
    bad = 0
    for t, s in live.items():
        b = insiders.get_insider_trades(t)
        # Compare only filings both runs saw: the live run may be capped, and stops at the same date
        def by_acc(x):
            return {(g["accession"], g["type"]): (round(g["shares"]), round(g["value"], 0)) for g in x["purchases"] + x["top_sales"]}
        lv, bk = by_acc(s), by_acc(b)
        common = set(lv) & set(bk)
        diff = {k: (lv[k], bk[k]) for k in common if lv[k] != bk[k]}
        same_totals = (b["buys"]["value"], b["sells"]["value"]) == (s["buys"]["value"], s["sells"]["value"]) if not s["capped"] else None
        bad += bool(diff) or same_totals is False
        print(f"   {t}: {len(common)} filings in both, {len(diff)} differ {diff if diff else ''}; totals equal: {same_totals} "
              f"(data sets buys {money(b['buys']['value'])} sells {money(b['sells']['value'])}; live buys {money(s['buys']['value'])} sells {money(s['sells']['value'])})")
    print(f"\n{bad} companies where the two sources disagree")
    print(json.dumps({t: live[t]["signal"] for t in live}, indent=1))


if __name__ == "__main__":
    main()
