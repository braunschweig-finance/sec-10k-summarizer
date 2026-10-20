"""
Ready-made results for S&P 500 companies. Render's free plan gives the API a tenth of a CPU, so reading a 10-K
there takes 20-50 seconds (JPMorgan's took 52 s at that CPU share and 5 s with one full CPU). A GitHub Actions job
(.github/workflows/prebuild.yml) runs the same lookups on GitHub's faster machines every week and publishes the
results as one file. The API downloads it at startup and twice a day and answers from it; any other company is
read live from SEC as before.
"""
import io
import json
import os
import shutil
import tarfile
import threading
import time

import httpx

URL = os.environ.get(
    "PREBUILT_URL",
    "https://github.com/braunschweig-finance/sec-10k-summarizer/releases/download/prebuilt-data/prebuilt.tar.gz",
)
DIR = os.environ.get("PREBUILT_DIR", "/tmp/prebuilt")
KINDS = ("company", "governance", "pay_efficiency", "trends")
REFRESH_SECONDS = 12 * 3600
RETRY_SECONDS = 15 * 60  # until the first download works (e.g. the weekly file hasn't been built yet)
_on_refresh = []  # called after new files are swapped in, e.g. to drop results cached from the old ones
_status = {"built_at": None, "companies": 0, "loaded_at": None, "error": None}


def get(kind, ticker):
    """The ready-made result for one lookup, or None to read it live."""
    try:
        with open(os.path.join(DIR, ticker, f"{kind}.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def status():
    return dict(_status)


def refresh():
    """Downloads the latest file and swaps it in. On any failure the current files stay in use."""
    try:
        r = httpx.get(URL, timeout=120, follow_redirects=True)
        r.raise_for_status()
        new, old = DIR + ".new", DIR + ".old"
        shutil.rmtree(new, ignore_errors=True)
        with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
            tar.extractall(new, filter="data")
        with open(os.path.join(new, "manifest.json")) as f:
            manifest = json.load(f)
        shutil.rmtree(old, ignore_errors=True)
        if os.path.exists(DIR):
            os.rename(DIR, old)
        os.rename(new, DIR)
        shutil.rmtree(old, ignore_errors=True)
        _status.update(built_at=manifest.get("built_at"), companies=len(manifest.get("tickers", [])),
                       loaded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), error=None)
        for fn in _on_refresh:
            fn()
        print(f"[prebuilt] loaded {_status['companies']} companies built {_status['built_at']}", flush=True)
        return True
    except Exception as e:
        _status["error"] = repr(e)[:300]
        print(f"[prebuilt] download failed: {e!r}", flush=True)
        return False


def _loop():
    while True:
        ok = refresh()
        time.sleep(REFRESH_SECONDS if ok or _status["loaded_at"] else RETRY_SECONDS)


def start(on_refresh=None):
    if on_refresh:
        _on_refresh.append(on_refresh)
    if URL:
        threading.Thread(target=_loop, daemon=True, name="prebuilt").start()
