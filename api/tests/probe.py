"""One-off network probe run on GitHub Actions (cloud sessions can't reach these hosts)."""
import httpx, traceback
UA = {"User-Agent": "Jacob Braunschweig jacob.braunschweig@gmail.com"}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
def show(name, url, headers=BROWSER, n=600):
    try:
        r = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
        print(f"== {name}: {r.status_code} {len(r.content)} bytes {r.headers.get('content-type')}")
        print(r.text[:n])
    except Exception as e:
        print(f"== {name}: ERROR {e!r}")
show("iwb", "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund", n=2500)
show("yahoo", "https://query1.finance.yahoo.com/v8/finance/chart/CAT?range=10y&interval=1mo", n=400)
show("yahoo2", "https://query2.finance.yahoo.com/v8/finance/chart/CAT?period1=1577836800&period2=1767225600&interval=1d", n=300)
show("stooq", "https://stooq.com/q/d/l/?s=cat.us&i=m", n=400)
show("nasdaq", "https://api.nasdaq.com/api/quote/CAT/historical?assetclass=stocks&fromdate=2021-01-01&todate=2025-12-31&limit=10", n=400)
show("tiingo-free?", "https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=CAT&apikey=demo", n=300)
from edgar import Company, set_identity
set_identity(UA["User-Agent"])
for t in ["ZZZZQ", "TSM", "SPY", "BRK-B", "BRK.B"]:
    try:
        c = Company(t)
        print(t, "->", type(c), getattr(c, "name", None), getattr(c, "sic", None), getattr(c, "industry", None))
        fs = c.get_filings(form="10-K", trigger_full_load=False)
        print("  10-K count", len(fs) if fs is not None else None, [f.form for f in fs][:3] if fs else None)
    except Exception as e:
        print(t, "EXC", type(e).__module__, type(e).__name__, str(e)[:200])
c = Company("CAT")
fs = c.get_filings(form="10-K", trigger_full_load=False)
print("CAT 10-K first page", [(f.form, str(f.filing_date), f.primary_document) for f in fs][:4])
