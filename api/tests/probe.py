import httpx
for u in ["https://www.ishares.com/us/products/239707/ishares-russell-1000-etf/1467271812596.ajax?fileType=csv&fileName=IWB_holdings&dataType=fund&siteEntryPassthrough=true"]:
    r = httpx.get(u, headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True)
    print(r.status_code, r.text[:1200])
