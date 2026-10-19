"""
Peer ranking for Pay Efficiency, from a fixed research sample (no live SEC calls).

data/pay_efficiency_peers.csv: 132 S&P 500 companies (Financials and Real Estate excluded), fiscal 2022-2025,
pulled from each company's DEF 14A Pay Versus Performance XBRL (ecd:PeoActuallyPaidCompAmt) and the 10-K
operating income in SEC companyfacts (us-gaap:OperatingIncomeLoss). Only years with operating income above
zero are kept. Every row carries both accession numbers. Built from the project's pay_efficiency_data.csv.
"""
import csv
import os
from datetime import date

PEERS_FILE = os.path.join(os.path.dirname(__file__), "data", "pay_efficiency_peers.csv")


def _load():
    by_year = {}
    with open(PEERS_FILE, newline="") as f:
        for r in csv.DictReader(f):
            row = {
                "ticker": r["ticker"],
                "company": r["company"],
                "fy_end": r["fy_end"],
                "pct": int(r["peo_cap"]) / int(r["operating_income"]) * 100,
                "pvp_accn": r["pvp_accn"],
                "op_income_accn": r["op_income_accn"],
            }
            by_year.setdefault(int(r["fiscal_year"]), []).append(row)
    return by_year


PEERS = _load()


def fiscal_year(fy_end):
    d = date.fromisoformat(fy_end)
    return d.year - 1 if d.month == 1 and d.day <= 7 else d.year


def percentile(sorted_vals, q):
    """Linear-interpolated percentile (same as numpy's default), q in 0..1."""
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def rank(ticker, fy_end, pct, denominator):
    """Where a company's Pay Efficiency sits among the sample for the same fiscal year (the latest sample year if
    that year isn't in the sample). The company itself is left out of its own peer group. None if there's no value."""
    if pct is None or not PEERS:
        return None
    year = fiscal_year(fy_end)
    peer_year = year if year in PEERS else max(PEERS)
    group = [p for p in PEERS[peer_year] if p["ticker"] != ticker.upper()]
    vals = sorted(p["pct"] for p in group)
    higher = sum(1 for v in vals if v > pct)
    return {
        "fiscal_year": year,
        "peer_year": peer_year,
        "count": len(vals),
        "higher_count": higher,
        # Share of peers that paid their CEO a bigger slice of operating income (lower Pay Efficiency is better)
        "lower_than_pct": higher / len(vals) * 100,
        "median": percentile(vals, 0.5),
        "p25": percentile(vals, 0.25),
        "p75": percentile(vals, 0.75),
        "values": [round(v, 4) for v in vals],
        "notes": [n for n in [
            f"The sample has no fiscal {year} yet, so this compares against fiscal {peer_year}." if peer_year != year else "",
            "This company's value uses pretax income; the peers all use operating income." if denominator == "pretax" else "",
        ] if n],
        "source": "132 S&P 500 companies (Financials and Real Estate excluded): DEF 14A Pay Versus Performance XBRL and 10-K operating income, fiscal 2022-2025",
    }
