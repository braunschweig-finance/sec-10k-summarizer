import httpx, io
B = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
     "Accept": "text/csv,application/json,text/html;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.9"}
def show(name, url, n=800, **kw):
    try:
        r = httpx.get(url, headers={**B, **kw.pop("headers", {})}, timeout=40, follow_redirects=True, **kw)
        print(f"== {name}: {r.status_code} {len(r.content)} {r.headers.get('content-type')} final={r.url}")
        print(r.text[:n].replace("\n", " | "))
        return r
    except Exception as e:
        print(f"== {name}: ERROR {e!r}")
with httpx.Client(headers=B, follow_redirects=True, timeout=40) as c:
    c.get("https://www.ishares.com/us/products/239707/ishares-russell-1000-etf?switchLocale=y&siteEntryPassthrough=true")
    r = c.get("https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund")
    print("== ishares w/ passthrough", r.status_code, r.headers.get("content-type"), r.text[:1500].replace("\n", " | "))
show("ishares json", "https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?tab=all&fileType=json", n=600)
show("vanguard api", "https://investor.vanguard.com/investment-products/etfs/profile/api/VONE/portfolio-holding/stock?start=1&count=50")
show("vanguard api2", "https://investor.vanguard.com/vmf/api/VONE/portfolio-holding/stock")
show("schwab SCHK?", "https://www.schwabassetmanagement.com/allholdings/SCHK", n=400)
show("ssga onek", "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-onek.xlsx", n=80)
r = show("ssga spy", "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx", n=10)
if r is not None and r.status_code == 200:
    import pandas as pd
    df = pd.read_excel(io.BytesIO(r.content), skiprows=4)
    print(df.columns.tolist(), df.head(3).to_string())
show("wiki sp400", "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", n=100, headers={"User-Agent": "SEC-Terminal/1.0 (jacob.braunschweig@gmail.com)"})
