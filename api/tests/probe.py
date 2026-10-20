"""One-off network probe run on GitHub Actions (cloud sessions can't reach these hosts)."""
import httpx, io
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
def show(name, url, client=None, n=600):
    try:
        r = (client or httpx).get(url, headers=BROWSER, timeout=30, follow_redirects=True)
        print(f"== {name}: {r.status_code} {len(r.content)} bytes {r.headers.get('content-type')}")
        print(r.text[:n])
        return r
    except Exception as e:
        print(f"== {name}: ERROR {e!r}")
r = show("wiki", "https://en.wikipedia.org/wiki/Russell_1000_Index", n=200)
if r is not None and r.status_code == 200:
    import pandas as pd
    for i, t in enumerate(pd.read_html(io.StringIO(r.text))):
        print(i, t.shape, list(t.columns)[:6])
        if len(t) > 900:
            print(t.head(8).to_string()); print(t.iloc[:, -1].value_counts().head(15) if t.shape[1] > 1 else "")
with httpx.Client(follow_redirects=True) as c:
    show("ishares page", "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf", client=c, n=100)
    show("ishares csv", "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund", client=c, n=1500)
show("vanguard", "https://investor.vanguard.com/investment-products/etfs/profile/api/VONE/portfolio-holding/stock", n=600)
show("ssga", "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx", n=100)
