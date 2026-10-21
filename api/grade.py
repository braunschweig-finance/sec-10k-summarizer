"""
One overall grade per company, from the four things this site reads out of SEC filings that other tools don't put
together: governance, red flags, insider trading and value against peers.

It describes the company today. It is not a prediction of returns: the fair value part was back-tested and showed no
reliable return signal (valuation.backtest), so it carries the smallest weight, and the other parts have no history
to test against yet.

Each part is scored 0-100, 50 being typical:

  Governance (35%)    Board independence, say-on-pay support, CEO pay ratio and Pay Efficiency, each placed against
                      the company's sector (the Russell 1000 medians in benchmarks.json): the sector's 25th percentile
                      scores 25, its median 50, its 75th percentile 75, straight lines between and beyond, kept within
                      0-100. Lower is better for the pay ratio and Pay Efficiency (only a positive Pay Efficiency
                      counts). A say-on-pay vote under 70% (the level proxy advisers treat as a failed vote) scores
                      at most 20. The part is the average of the
                      numbers found.
  Red flags (35%)     100, minus 35 for each high flag (restatement, delisting notice, bankruptcy, late 10-K), 12 for
                      each medium one (auditor change, late 10-Q, cyber incident, CEO or CFO leaving) and 4 for each
                      low one, over the last three years. At least 0.
  Insiders (15%)      50 when nothing stands out. Cluster buying (3+ insiders within 30 days): 85. Net open-market
                      buying: 70. Net selling outside 10b5-1 plans worth over 0.5% of the company's market value: 35,
                      over 2%: 20.
  Value vs peers (15%) 50 + 50 x tanh(gap / 60%), where gap is fair value against price: at the peers' price 50, 30%
                      below fair value about 73, 30% above about 27. Left out when the estimate is low confidence
                      (the peers' range is over 3x wide).

A part that couldn't be read is left out and the weights of the rest are scaled up to 100%; the grade says which.
Letters: A 80+, B 65+, C 50+, D 35+, F below.
"""
import math

WEIGHTS = {"governance": 35, "red_flags": 35, "insiders": 15, "valuation": 15}
NAMES = {"governance": "Governance", "red_flags": "Red flags", "insiders": "Insider trading", "valuation": "Value vs peers"}
LETTERS = [(80, "A"), (65, "B"), (50, "C"), (35, "D"), (0, "F")]
FLAG_POINTS = {"high": 35, "medium": 12, "low": 4}
SAY_ON_PAY_FAIL = 70.0
GOV_METRICS = {
    # name: (where to read the value, True when higher is better)
    "Board Independence": (lambda g, pe: ((g.get("metrics") or {}).get("Board Independence") or {}).get("pct"), True),
    "Say-on-Pay Support": (lambda g, pe: ((g.get("metrics") or {}).get("Say-on-Pay Support") or {}).get("pct"), True),
    "CEO Pay Ratio": (lambda g, pe: ((g.get("metrics") or {}).get("CEO Pay Ratio") or {}).get("value"), False),
    # Compensation actually paid can be negative when the stock falls (Super Micro FY2025: -$190M); a negative ratio isn't
    # "efficient pay", so only positive values are placed against the sector
    "Pay Efficiency": (lambda g, pe: pe.get("pct") if pe.get("available") and pe.get("denominator") == "operating"
                       and (pe.get("pct") or 0) > 0 else None, False),
}


def letter(score):
    return next(l for cut, l in LETTERS if score >= cut)


def _clamp(x):
    return max(0.0, min(100.0, x))


def place(value, stats, higher_is_better=True):
    """0-100 for a value against a sector's {"p25", "median", "p75"}: 25 at p25, 50 at the median, 75 at p75."""
    p25, med, p75 = stats["p25"], stats["median"], stats["p75"]
    if value >= med:
        s = 50 + 25 * (value - med) / (p75 - med) if p75 > med else (50 if value == med else 75)
    else:
        s = 50 - 25 * (med - value) / (med - p25) if med > p25 else 25
    return _clamp(s if higher_is_better else 100 - s)


def governance_part(gov, pay_eff, benchmark):
    metrics = (benchmark or {}).get("metrics") or {}
    items = []
    for name, (read, higher) in GOV_METRICS.items():
        value = read(gov or {}, pay_eff or {})
        stats = metrics.get(name)
        if value is None or not stats:
            continue
        score = place(value, stats, higher)
        note = ""
        if name == "Say-on-Pay Support" and value < SAY_ON_PAY_FAIL:
            score, note = min(score, 20.0), f"under {SAY_ON_PAY_FAIL:.0f}%, which proxy advisers treat as a failed vote"
        items.append({"metric": name, "value": value, "sector_median": stats["median"], "sector_p25": stats["p25"],
                      "sector_p75": stats["p75"], "lower_is_better": not higher, "score": score, "note": note})
    if not items:
        return None, "None of the four governance numbers could be read from the proxy and compared with the sector."
    return {"score": sum(i["score"] for i in items) / len(items), "items": items,
            "group": (benchmark or {}).get("group"), "proxy_url": (gov or {}).get("proxy_url")}, None


def red_flags_part(rf):
    flags = rf.get("flags") or []
    by = {s: sum(1 for f in flags if f.get("severity") == s) for s in FLAG_POINTS}
    score = max(0.0, 100.0 - sum(FLAG_POINTS[s] * n for s, n in by.items()))
    return {"score": score, "high": by["high"], "medium": by["medium"], "low": by["low"], "since": rf.get("since"),
            "flags": [{k: f.get(k) for k in ("flag", "severity", "filed", "form", "url")} for f in flags]}


def insiders_part(ins, market_cap):
    sells, planned = ins.get("sells") or {}, ins.get("planned_sells") or {}
    buys = ins.get("buys") or {}
    unplanned = (sells.get("value") or 0) - (planned.get("value") or 0)
    net_unplanned = (buys.get("value") or 0) - unplanned
    share = net_unplanned / market_cap * 100 if market_cap else None
    if ins.get("cluster"):
        score, why = 85.0, "cluster buying (3 or more insiders bought within 30 days)"
    elif buys.get("count") and (buys.get("value") or 0) >= (sells.get("value") or 0):
        score, why = 70.0, "insiders bought more than they sold"
    elif share is not None and share < -2:
        score, why = 20.0, f"selling outside 10b5-1 plans was {-share:.2f}% of market value"
    elif share is not None and share < -0.5:
        score, why = 35.0, f"selling outside 10b5-1 plans was {-share:.2f}% of market value"
    else:
        score, why = 50.0, "nothing unusual (routine or planned selling)"
    return {"score": score, "why": why, "buys_value": buys.get("value") or 0, "sells_value": sells.get("value") or 0,
            "planned_sells_value": planned.get("value") or 0, "net_unplanned_pct_of_market_cap": share,
            "from": ins.get("from"), "to": ins.get("to"), "signal": ins.get("signal")}


def valuation_part(val):
    if not val.get("available"):
        return None, val.get("reason") or "No fair value estimate."
    if val.get("confidence") == "low":
        return None, val["confidence_note"]
    gap = val["upside_pct"]
    return {"score": 50 + 50 * math.tanh(gap / 60), "upside_pct": gap, "verdict": val["verdict"],
            "fair_value": val["fair_value"], "price": val["price"]}, None


def build(ticker, name, parts, errors):
    """parts: {"governance": (governance, pay_efficiency, benchmark), "red_flags": ..., "insiders": (insiders, market cap),
    "valuation": ...}; errors: {part: why it couldn't be read}. Returns the grade with every part's inputs."""
    out, missing = {}, dict(errors)
    if "governance" in parts:
        res, why = governance_part(*parts["governance"])
        if res:
            out["governance"] = res
        else:
            missing["governance"] = why
    if "red_flags" in parts:
        out["red_flags"] = red_flags_part(parts["red_flags"])
    if "insiders" in parts:
        out["insiders"] = insiders_part(*parts["insiders"])
    if "valuation" in parts:
        res, why = valuation_part(parts["valuation"])
        if res:
            out["valuation"] = res
        else:
            missing["valuation"] = why
    total_weight = sum(WEIGHTS[k] for k in out)
    components = [{"part": k, "name": NAMES[k], "weight": WEIGHTS[k], "used_weight": WEIGHTS[k] / total_weight * 100 if total_weight else 0,
                   "score": v["score"], "letter": letter(v["score"]), "details": v} for k, v in out.items()]
    base = {"ticker": ticker, "name": name, "components": components,
            "missing": [{"part": k, "name": NAMES[k], "why": v} for k, v in missing.items()],
            "method": __doc__.strip(),
            "disclaimer": "Describes the company's filings today; not a prediction of returns. The value-vs-peers part showed no "
                          "reliable return signal in its back-test, so it carries the least weight."}
    if total_weight < 50:
        return {**base, "available": False,
                "reason": "Too little could be read to grade this company fairly (less than half the weight)."}
    score = sum(WEIGHTS[k] * v["score"] for k, v in out.items()) / total_weight
    return {**base, "available": True, "score": score, "letter": letter(score)}
