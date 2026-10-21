"""
Builds prebuilt.tar.gz for the API (see prebuilt.py): the six lookups for every Russell 1000 company
(data/russell1000.csv) and S&P 500 company (data/sp500_tickers.txt) plus any given on the command line, each saved
exactly as the API would return it, and the sector medians built from them (benchmarks.py). A lookup that fails
is left out, so the API reads that one live. One SEC has no data for (no 10-K, say) is saved as that answer.

Run from the api/ folder:  python prebuild.py [EXTRA_TICKER ...]
"""
import json
import os
import shutil
import sys
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import benchmarks
import sec_core
import valuation

LOOKUPS = {
    "company": sec_core.get_financial_report,
    "governance": sec_core.get_governance_report,
    "pay_efficiency": sec_core.get_pay_efficiency,
    "trends": sec_core.get_trends,
    "risks": sec_core.get_risk_summary,
    "fundamentals": sec_core.get_valuation_inputs,
}
OUT = "prebuilt"
WORKERS = int(os.environ.get("PREBUILD_WORKERS", "6"))


def tickers():
    with open(os.path.join(os.path.dirname(__file__) or ".", "data", "sp500_tickers.txt")) as f:
        listed = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    return list(dict.fromkeys(list(benchmarks.russell_members()) + listed + [t.upper() for t in sys.argv[1:]]))


def build_one(ticker):
    saved, failed = [], {}
    os.makedirs(os.path.join(OUT, ticker), exist_ok=True)
    for kind, fn in LOOKUPS.items():
        try:
            body = json.dumps(fn(ticker), allow_nan=False)
        except sec_core.DataUnavailable as e:
            body = json.dumps({"__unavailable__": str(e)})
        except Exception as e:
            failed[kind] = repr(e)[:200]
            continue
        with open(os.path.join(OUT, ticker, f"{kind}.json"), "w") as f:
            f.write(body)
        saved.append(kind)
    return ticker, saved, failed


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    started, done, failures = time.time(), [], {}
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        for fut in as_completed([pool.submit(build_one, t) for t in tickers()]):
            ticker, saved, failed = fut.result()
            if saved:
                done.append(ticker)
            if failed:
                failures[ticker] = failed
            print(f"{ticker}: {len(saved)}/{len(LOOKUPS)}" + (f" (failed: {', '.join(failed)})" if failed else ""), flush=True)
    bench = benchmarks.build(OUT)
    bench["built_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(os.path.join(OUT, "benchmarks.json"), "w") as f:
        json.dump(bench, f, allow_nan=False)
    print(f"Sector medians for {len(bench['sectors'])} sectors", flush=True)
    # Fair value peers and back-test: every company's 10-K inputs at the latest close, and the yearly back-test
    val = valuation.build(OUT, sorted(done))
    val["built_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(os.path.join(OUT, "valuation.json"), "w") as f:
        json.dump(val, f, allow_nan=False)
    print(f"Fair value back-test: {json.dumps(val['backtest']['average'])}", flush=True)
    manifest = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tickers": sorted(done), "failures": failures}
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    with tarfile.open("prebuilt.tar.gz", "w:gz") as tar:
        for name in os.listdir(OUT):
            tar.add(os.path.join(OUT, name), arcname=name)
    print(f"Built {len(done)} companies in {time.time() - started:.0f}s; {len(failures)} with a failed lookup", flush=True)


if __name__ == "__main__":
    main()
