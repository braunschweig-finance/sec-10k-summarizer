# Temporary: pulls valuation inputs + price histories for the whole universe so the method can be checked offline.
import gzip, json, os, sys, time
from concurrent.futures import ProcessPoolExecutor
import prebuild, sec_core, valuation

def one(t):
    try:
        return t, sec_core.get_valuation_inputs(t)
    except Exception as e:
        return t, {"__unavailable__": repr(e)[:200]}

if __name__ == "__main__":
    ts = prebuild.tickers()
    started = time.time()
    with ProcessPoolExecutor(2) as pool:
        funds = dict(pool.map(one, ts))
    print("fundamentals", len(funds), time.time() - started, flush=True)
    ok = {t: f for t, f in funds.items() if "__unavailable__" not in f}
    hist = valuation.fetch_histories(list(ok))
    print("histories", len(hist), time.time() - started, flush=True)
    ser = {t: {"days": [d.isoformat() for d in h["days"]], "close": h["close"], "adjclose": h["adjclose"],
               "splits": [(d.isoformat(), r) for d, r in h["splits"]]} for t, h in hist.items()}
    with gzip.open("valuation_dev.json.gz", "wt") as f:
        json.dump({"funds": funds, "histories": ser}, f)
    print("size", os.path.getsize("valuation_dev.json.gz"))
