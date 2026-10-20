"""
Sector medians for the ratio cards and governance numbers. Built by prebuild.py from the ready-made results of every
Russell 1000 company, grouped by GICS sector (data/russell1000.csv, from Wikipedia's Russell 1000 Index page), and
published in the same file as those results. Each company's own latest 10-K and proxy are used, so fiscal years can
differ by up to a year between companies. Companies outside the Russell 1000 are compared with all of it.
"""
import csv
import json
import os

import peers
import sec_core

RUSSELL_FILE = os.path.join(os.path.dirname(__file__), "data", "russell1000.csv")
SOURCE = ("Russell 1000 companies' latest 10-K and proxy (DEF 14A) on SEC EDGAR, grouped by GICS sector as listed on "
          "Wikipedia's Russell 1000 Index page")
MIN_GROUP = 5  # fewer companies than this with a value and no median is shown for that metric


def russell_members():
    """{ticker: {"company", "sector"}} from the committed list (skips the # source line)."""
    if not os.path.exists(RUSSELL_FILE):
        return {}
    with open(RUSSELL_FILE, newline="") as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        return {r["ticker"]: {"company": r["company"], "sector": r["sector"]} for r in rows}


def company_values(folder):
    """The benchmarked numbers for one company's ready-made results folder, or {} if there's no 10-K result."""
    def read(kind):
        try:
            with open(os.path.join(folder, f"{kind}.json")) as f:
                body = json.load(f)
            return None if "__unavailable__" in body else body
        except (OSError, ValueError):
            return None

    report = read("company")
    if not report:
        return {}
    vals = sec_core.ratio_values(report.get("inputs", {}))
    pe = read("pay_efficiency")
    if pe and pe.get("available") and pe.get("denominator") == "operating":
        vals["Pay Efficiency"] = pe.get("pct")
    gov = read("governance")
    m = (gov or {}).get("metrics", {})
    vals["CEO Pay Ratio"] = (m.get("CEO Pay Ratio") or {}).get("value")
    vals["Board Independence"] = (m.get("Board Independence") or {}).get("pct")
    vals["Say-on-Pay Support"] = (m.get("Say-on-Pay Support") or {}).get("pct")
    return vals


def summarize(values):
    vals = sorted(v for v in values if v is not None)
    if len(vals) < MIN_GROUP:
        return None
    return {"median": peers.percentile(vals, 0.5), "p25": peers.percentile(vals, 0.25), "p75": peers.percentile(vals, 0.75), "n": len(vals)}


def build(out_dir, members=None):
    """benchmarks.json contents: medians per sector and for the whole Russell 1000, plus each member's sector."""
    members = russell_members() if members is None else members
    by_sector, everyone = {}, {}
    for ticker, info in members.items():
        vals = company_values(os.path.join(out_dir, ticker))
        if not vals:
            continue
        for k, v in vals.items():
            by_sector.setdefault(info["sector"], {}).setdefault(k, []).append(v)
            everyone.setdefault(k, []).append(v)

    def group(metrics):
        return {"companies": max((len(v) for v in metrics.values()), default=0),
                "metrics": {k: summarize(v) for k, v in metrics.items()}}

    return {
        "source": SOURCE,
        "sectors": {s: group(m) for s, m in sorted(by_sector.items())},
        "all": group(everyone),
        "members": {t: info["sector"] for t, info in members.items()},
    }


_cache = {"path": None, "mtime": None, "data": None}


def load(path):
    """benchmarks.json from the downloaded ready-made results, re-read when the file changes."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _cache["path"] != path or _cache["mtime"] != mtime:
        with open(path) as f:
            _cache.update(path=path, mtime=mtime, data=json.load(f))
    return _cache["data"]


def for_ticker(ticker, path):
    """The comparison group for one company: its sector if it's a Russell 1000 member, otherwise the whole index."""
    data = load(path)
    if not data:
        return None
    sector = data["members"].get(ticker.upper())
    if sector and sector in data["sectors"]:
        g = data["sectors"][sector]
        return {"group": sector, "is_sector": True, "companies": g["companies"], "metrics": g["metrics"], "source": data["source"],
                "built_at": data.get("built_at")}
    g = data["all"]
    return {"group": "Russell 1000", "is_sector": False, "companies": g["companies"], "metrics": g["metrics"], "source": data["source"],
            "built_at": data.get("built_at"),
            "note": "This company isn't in the Russell 1000 list, so it's compared with the whole index instead of its sector."}
