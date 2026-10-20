"""
Refreshes data/russell1000.csv (ticker, CIK, company) with the stocks held by the Vanguard Russell 1000 ETF (VONE),
which tracks the Russell 1000 index, from Vanguard's public holdings data. Each holding is matched to its SEC filer
through SEC's company_tickers.json; a company with two share classes (GOOGL and GOOG) is kept once, under the class
the fund holds most of. The prebuild job runs this first; if either source can't be read, the committed file stays.

Run from the api/ folder:  python update_russell.py
"""
import csv
import os

import httpx

VANGUARD = "https://investor.vanguard.com/vmf/api/VONE/portfolio-holding/stock"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
OUT = os.path.join(os.path.dirname(__file__) or ".", "data", "russell1000.csv")
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
           "Accept": "application/json"}
SEC_UA = {"User-Agent": "Jacob Braunschweig jacob.braunschweig@gmail.com"}


def vanguard_holdings():
    """[(ticker, name, market value)] for every stock the fund holds, and the holdings date."""
    out, start, as_of = [], 1, ""
    while True:
        r = httpx.get(VANGUARD, params={"start": start, "count": 500}, headers=BROWSER, timeout=60)
        r.raise_for_status()
        body = r.json()
        rows = body["fund"]["entity"]
        as_of = body.get("asOfDate", as_of)[:10]
        out += [(h["ticker"].strip().upper(), h.get("longName") or h.get("shortName", ""), float(h.get("marketValue") or 0))
                for h in rows if h.get("ticker")]
        if len(out) >= int(body.get("size", 0)) or not rows:
            return out, as_of
        start += len(rows)


def main():
    try:
        holdings, as_of = vanguard_holdings()
        sec = httpx.get(SEC_TICKERS, headers=SEC_UA, timeout=60).json()
    except Exception as e:
        print(f"Kept the committed Russell 1000 list: {e!r}")
        return
    by_ticker = {v["ticker"].upper(): v for v in sec.values()}
    kept, seen_cik, unmatched = [], set(), []
    for ticker, name, value in sorted(holdings, key=lambda h: -h[2]):
        t = ticker.replace(".", "-").replace("/", "-")
        hit = by_ticker.get(t) or by_ticker.get(t.replace("-", ""))
        if not hit:
            unmatched.append(ticker)
            continue
        if hit["cik_str"] in seen_cik:
            continue
        seen_cik.add(hit["cik_str"])
        kept.append({"ticker": hit["ticker"].upper(), "cik": hit["cik_str"], "company": hit["title"]})
    if len(kept) < 900:
        print(f"Kept the committed Russell 1000 list: only {len(kept)} holdings matched SEC filers")
        return
    with open(OUT, "w", newline="") as f:
        f.write(f"# Russell 1000: stocks held by the Vanguard Russell 1000 ETF (VONE) on {as_of}, from {VANGUARD}, "
                f"matched to SEC filers via {SEC_TICKERS}\n")
        w = csv.DictWriter(f, fieldnames=["ticker", "cik", "company"])
        w.writeheader()
        w.writerows(sorted(kept, key=lambda r: r["ticker"]))
    print(f"Wrote {len(kept)} companies ({len(holdings)} holdings, {len(unmatched)} not SEC filers: {unmatched[:20]})")


if __name__ == "__main__":
    main()
