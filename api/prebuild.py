"""
Builds prebuilt.tar.gz for the API (see prebuilt.py): the four lookups for every ticker in
data/sp500_tickers.txt plus any given on the command line, each saved exactly as the API would return it.
A lookup that fails is left out, so the API reads that one live.

Run from the api/ folder:  python prebuild.py [EXTRA_TICKER ...]
"""
import json
import os
import shutil
import sys
import tarfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import sec_core

LOOKUPS = {
    "company": sec_core.get_financial_report,
    "governance": sec_core.get_governance_report,
    "pay_efficiency": sec_core.get_pay_efficiency,
    "trends": sec_core.get_trends,
}
OUT = "prebuilt"


def tickers():
    with open(os.path.join(os.path.dirname(__file__) or ".", "data", "sp500_tickers.txt")) as f:
        listed = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
    return list(dict.fromkeys(listed + [t.upper() for t in sys.argv[1:]]))


def build_one(ticker):
    saved, failed = [], {}
    os.makedirs(os.path.join(OUT, ticker), exist_ok=True)
    for kind, fn in LOOKUPS.items():
        try:
            body = json.dumps(fn(ticker), allow_nan=False)
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
    with ProcessPoolExecutor(max_workers=4) as pool:
        for fut in as_completed([pool.submit(build_one, t) for t in tickers()]):
            ticker, saved, failed = fut.result()
            if saved:
                done.append(ticker)
            if failed:
                failures[ticker] = failed
            print(f"{ticker}: {len(saved)}/4" + (f" (failed: {', '.join(failed)})" if failed else ""), flush=True)
    manifest = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tickers": sorted(done), "failures": failures}
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    with tarfile.open("prebuilt.tar.gz", "w:gz") as tar:
        for name in os.listdir(OUT):
            tar.add(os.path.join(OUT, name), arcname=name)
    print(f"Built {len(done)} companies in {time.time() - started:.0f}s; {len(failures)} with a failed lookup", flush=True)


if __name__ == "__main__":
    main()
