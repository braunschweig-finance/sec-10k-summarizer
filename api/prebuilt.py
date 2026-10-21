"""
Ready-made results for Russell 1000 and S&P 500 companies. Render's free plan gives the API a tenth of a CPU, so reading a 10-K
there takes 20-50 seconds (JPMorgan's took 52 s at that CPU share and 5 s with one full CPU). A GitHub Actions job
(.github/workflows/prebuild.yml) runs the same lookups on GitHub's faster machines every week and publishes the
results as one file. The API downloads it at startup, again within an hour of each new build, and at least twice a
day, and answers from it; any other company is read live from SEC as before.
"""
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
KINDS = ("company", "governance", "pay_efficiency", "trends", "risks", "fundamentals")
# GitHub's release API says when the file was last published, so a new build is picked up within the hour even when
# the API itself was redeployed (and loaded the old file) while the build was still running
RELEASE_API = os.environ.get(
    "PREBUILT_RELEASE_API",
    "https://api.github.com/repos/braunschweig-finance/sec-10k-summarizer/releases/tags/prebuilt-data",
)
CHECK_SECONDS = 3600
REFRESH_SECONDS = 12 * 3600
RETRY_SECONDS = 15 * 60  # until the first download works (e.g. the weekly file hasn't been built yet)
_on_refresh = []  # called after new files are swapped in, e.g. to drop results cached from the old ones
_status = {"built_at": None, "companies": 0, "loaded_at": None, "error": None}
_state = {"published": None, "refreshed": 0.0}


def get(kind, ticker):
    """The ready-made result for one lookup, or None to read it live."""
    try:
        with open(os.path.join(DIR, ticker, f"{kind}.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def benchmarks_path():
    return os.path.join(DIR, "benchmarks.json")


def valuation_path():
    return os.path.join(DIR, "valuation.json")


def status():
    return dict(_status)


def refresh():
    """Downloads the latest file and swaps it in. On any failure the current files stay in use."""
    try:
        new, old, archive = DIR + ".new", DIR + ".old", DIR + ".tar.gz"
        # Streamed to disk, so the file (tens of MB with the Russell 1000) never sits in the server's memory
        with httpx.stream("GET", URL, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            with open(archive, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        shutil.rmtree(new, ignore_errors=True)
        with tarfile.open(archive, mode="r:gz") as tar:
            tar.extractall(new, filter="data")
        os.remove(archive)
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


def published_at():
    """When prebuilt.tar.gz was last uploaded to the release, or None if GitHub can't be asked right now."""
    try:
        r = httpx.get(RELEASE_API, timeout=30, follow_redirects=True)
        r.raise_for_status()
        return max(a["updated_at"] for a in r.json()["assets"] if a["name"] == "prebuilt.tar.gz")
    except Exception:
        return None


def check(now=None):
    """Downloads the file when nothing is loaded yet, when a newer build was published, or every 12 hours regardless."""
    now = time.time() if now is None else now
    stamp = published_at()
    stale = now - _state["refreshed"] >= REFRESH_SECONDS
    if not _status["loaded_at"] or stale or (stamp and stamp != _state["published"]):
        if refresh():
            _state.update(published=stamp, refreshed=now)


def _loop():
    while True:
        check()
        time.sleep(CHECK_SECONDS if _status["loaded_at"] else RETRY_SECONDS)


def start(on_refresh=None):
    if on_refresh:
        _on_refresh.append(on_refresh)
    if URL:
        threading.Thread(target=_loop, daemon=True, name="prebuilt").start()
