"""
Refreshes data/russell1000.csv (ticker, company, GICS sector) from Wikipedia's Russell 1000 Index page, which lists
the index's members with their GICS sector. The prebuild job runs this first; if the page can't be read or looks
wrong, the committed file is kept.

Run from the api/ folder:  python update_russell.py
"""
import csv
import io
import os
import sys
import time

import httpx
import pandas as pd

URL = "https://en.wikipedia.org/wiki/Russell_1000_Index"
OUT = os.path.join(os.path.dirname(__file__) or ".", "data", "russell1000.csv")
HEADERS = {"User-Agent": "SEC-Terminal/1.0 (https://sec-10k-summarizer.vercel.app; jacob.braunschweig@gmail.com)"}


def fetch():
    r = httpx.get(URL, headers=HEADERS, timeout=60, follow_redirects=True)
    r.raise_for_status()
    for t in pd.read_html(io.StringIO(r.text)):
        cols = {str(c).strip().lower(): c for c in t.columns}
        sym = next((cols[c] for c in cols if c in ("symbol", "ticker")), None)
        sector = next((cols[c] for c in cols if "sector" in c), None)
        name = next((cols[c] for c in cols if c in ("company", "security", "name")), None)
        if sym is not None and sector is not None and len(t) >= 900:
            rows = []
            for _, r in t.iterrows():
                tk = str(r[sym]).strip().upper().replace(".", "-")
                if tk and tk != "NAN":
                    rows.append({"ticker": tk, "company": str(r[name]).strip() if name is not None else "", "sector": str(r[sector]).strip()})
            return rows
    raise RuntimeError("no Russell 1000 components table with a sector column on the page")


def main():
    try:
        rows = fetch()
    except Exception as e:
        print(f"Kept the committed Russell 1000 list: {e!r}")
        return
    rows = list({r["ticker"]: r for r in rows}.values())
    with open(OUT, "w", newline="") as f:
        f.write(f"# Russell 1000 members and GICS sectors from {URL} (read {time.strftime('%Y-%m-%d', time.gmtime())})\n")
        w = csv.DictWriter(f, fieldnames=["ticker", "company", "sector"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["ticker"]))
    sectors = pd.Series([r["sector"] for r in rows]).value_counts()
    print(f"Wrote {len(rows)} companies to {OUT}\n{sectors.to_string()}")


if __name__ == "__main__":
    main()
    sys.exit(0)
