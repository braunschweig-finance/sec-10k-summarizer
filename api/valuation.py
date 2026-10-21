"""
Fair value from comparable companies: what would this stock be worth if the market priced it like its closest peers?

Two identical houses on the same street should sell for about the same price. Here the "houses" are companies and the
features are the ones that drive valuation multiples:

1. Peers. Every Russell 1000 company in the same sector (sectors.py, from SEC's SIC industry code) is a candidate. Each
   is scored on how far it is from the company on four features, in units of the sector's own spread: size (log of
   revenue), revenue growth, profitability (operating margin; net margin for Financials and Real Estate) and leverage
   (total liabilities / total assets). Being in a different SEC industry adds a fixed distance (none for the same
   4-digit SIC code, 0.5 for the same 3-digit, 1.0 for the same 2-digit, 1.5 otherwise). The 8 closest are the peers.
2. Multiples. Each peer's EV/EBITDA, EV/EBIT, EV/Sales and P/E (P/E and P/B for Financials and Real Estate, whose debt is
   part of the business), using only positive numbers. EV = market value of equity + debt - cash and short-term
   investments.
3. Fair value. The peers' median multiple (and the 25th-75th percentile for the range) times the company's own figure,
   turned into a value per share (EV methods subtract debt and add back cash first). The fair value is the median of the
   methods' values, and the range is the median of their 25th and 75th percentile values.
4. Verdict. Price below the range: undervalued against peers. Above it: overvalued. Inside it: fairly valued.

Every 10-K number is the one first filed for that fiscal year (SEC companyfacts, see sec_core.get_valuation_inputs),
with its XBRL concept and accession number. Prices are Yahoo Finance daily closes (prices.py).

The back-test (backtest()) runs the same steps as of June 30 of each year from 2018, using only 10-Ks filed by that date
and that day's prices, and checks what each group of stocks returned over the next 12 months.
"""
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import peers
import prices
import sectors

EQUITY_SECTORS = {"Financials", "Real Estate"}
METHODS = {
    # name: (value it prices, the company figure it multiplies)
    "EV/EBITDA": ("ev", "EBITDA"),
    "EV/EBIT": ("ev", "EBIT"),
    "EV/Sales": ("ev", "Revenue"),
    "P/E": ("equity", "Net Income"),
    "P/B": ("equity", "Book Equity"),
}
PEER_COUNT = 8
MIN_PEERS = 3          # a multiple needs at least this many peers with a positive value, or it's left out
MAX_STALE_DAYS = 550   # the latest 10-K must cover a fiscal year that ended within this many days
INDUSTRY_STEP = [0.0, 0.5, 1.0, 1.5]  # added distance: same 4-digit SIC, 3-digit, 2-digit, only the same sector
FEATURES = ("size", "growth", "margin", "leverage")
CLIPS = {"growth": (-0.5, 1.0), "margin": (-0.5, 0.6), "leverage": (0.0, 1.2)}
SOURCE = ("10-K figures: SEC EDGAR companyfacts (XBRL), each as first filed for that fiscal year. Prices: Yahoo Finance "
          "daily close. Peers: Russell 1000 companies in the same sector (SEC SIC code).")


def methods_for(sector):
    return ["P/E", "P/B"] if sector in EQUITY_SECTORS else ["EV/EBITDA", "EV/EBIT", "EV/Sales", "P/E"]


def _v(year, name):
    hit = year["values"].get(name)
    return hit["value"] if hit else None


def _sum(*vals):
    present = [v for v in vals if v is not None]
    return sum(present) if present else None


def debt_and_cash(year):
    """(debt, cash, the line items used). Debt: total long-term debt plus short-term borrowings and commercial paper; or,
    without a total, noncurrent long-term debt plus current debt (DebtCurrent, which already includes them, or the
    current portion of long-term debt plus short-term borrowings and commercial paper). Cash includes short-term investments."""
    g = lambda n: _v(year, n)
    if g("Long-term Debt (total)") is not None:
        parts = ["Long-term Debt (total)", "Short-term Borrowings", "Commercial Paper"]
    elif g("Debt (current)") is not None:
        parts = ["Long-term Debt (noncurrent)", "Debt (current)"]
    else:
        parts = ["Long-term Debt (noncurrent)", "Long-term Debt (current)", "Short-term Borrowings", "Commercial Paper"]
    parts = [p for p in parts if g(p) is not None]
    debt = _sum(*[g(p) for p in parts])
    cash_parts = [p for p in ("Cash", "Short-term Investments") if g(p) is not None]
    return debt, _sum(*[g(p) for p in cash_parts]), parts + cash_parts


def pick_years(fund, as_of=None):
    """(the latest fiscal year whose 10-K was public by as_of, the year before it) or (None, None)."""
    years = [y for y in fund.get("years", []) if y.get("filed") and _v(y, "Revenue") is not None
             and (as_of is None or y["filed"] <= as_of.isoformat())]
    if not years:
        return None, None
    latest = years[-1]
    if as_of is not None and (as_of - date.fromisoformat(latest["fy_end"])).days > MAX_STALE_DAYS:
        return None, None
    prior = next((y for y in reversed(years[:-1]) if 330 <= (date.fromisoformat(latest["fy_end"]) - date.fromisoformat(y["fy_end"])).days <= 400), None)
    return latest, prior


def _clip(name, x):
    lo, hi = CLIPS[name]
    return min(max(x, lo), hi)


def build_row(fund, price, price_date, as_of=None):
    """One company's numbers, market value, multiples and peer features at a share price, or None if it can't be valued.

    price must be the price the shares actually traded at that day (prices.raw_close), to match the filed share count."""
    year, prior = pick_years(fund, as_of)
    if year is None or not price or price <= 0:
        return None
    sector = sectors.sector(fund.get("sic"))
    g = lambda n: _v(year, n)
    revenue, ebit, ni, da = g("Revenue"), g("Operating Income"), g("Net Income"), g("Depreciation & Amortization")
    shares, shares_note = g("Diluted Shares"), "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding"
    if not shares and ni and g("Diluted EPS"):
        shares, shares_note = ni / g("Diluted EPS"), "Derived: net income / diluted EPS"
    if not shares or shares <= 0:
        return None
    if ni is None and g("Diluted EPS") is not None:
        ni = g("Diluted EPS") * shares
    debt, cash, debt_parts = debt_and_cash(year)
    equity, assets, liabilities = g("Shareholders' Equity"), g("Total Assets"), g("Total Liabilities")
    if liabilities is None and assets is not None and equity is not None:
        liabilities = assets - equity
    mcap = price * shares
    ev = mcap + (debt or 0) - (cash or 0)
    figures = {"Revenue": revenue, "EBIT": ebit, "EBITDA": ebit + da if ebit is not None and da is not None else None,
               "Net Income": ni, "Book Equity": equity}
    multiples = {}
    for name, (base, fig) in METHODS.items():
        den = figures[fig]
        num = ev if base == "ev" else mcap
        multiples[name] = num / den if den and den > 0 and num > 0 else None

    margin_line = ni if sector in EQUITY_SECTORS else ebit
    features = {
        "size": math.log(revenue) if revenue and revenue > 0 else None,
        "growth": _clip("growth", revenue / _v(prior, "Revenue") - 1) if prior and revenue and _v(prior, "Revenue") and _v(prior, "Revenue") > 0 else None,
        "margin": _clip("margin", margin_line / revenue) if margin_line is not None and revenue and revenue > 0 else None,
        "leverage": _clip("leverage", liabilities / assets) if liabilities is not None and assets and assets > 0 else None,
    }
    # A share count that doesn't match the traded share class (Berkshire reports Class A-equivalent shares, for
    # example) shows up as a market value wildly out of line with sales. Such a row isn't used as a peer.
    sane = revenue is not None and revenue > 0 and 0.02 <= mcap / revenue <= 200
    return {
        "ticker": fund["ticker"], "name": fund.get("name", ""), "cik": fund.get("cik", ""), "sic": str(fund.get("sic") or ""),
        "industry": fund.get("industry", ""), "sector": sector,
        "fy_end": year["fy_end"], "fiscal_year": year.get("fiscal_year"), "filed": year["filed"],
        "price": price, "price_date": price_date.isoformat() if isinstance(price_date, date) else price_date,
        "shares": shares, "shares_source": shares_note, "market_cap": mcap, "debt": debt, "cash": cash, "ev": ev,
        "debt_parts": debt_parts, "figures": figures, "multiples": multiples, "features": features,
        "revenue_growth": features["growth"], "sane": sane,
    }


def industry_step(a, b):
    a, b = str(a or ""), str(b or "")
    if a and a == b:
        return INDUSTRY_STEP[0]
    if a[:3] and a[:3] == b[:3]:
        return INDUSTRY_STEP[1]
    if a[:2] and a[:2] == b[:2]:
        return INDUSTRY_STEP[2]
    return INDUSTRY_STEP[3]


def _spread(vals):
    """Standard deviation, or 1 when there are too few values to measure one."""
    vals = [v for v in vals if v is not None]
    if len(vals) < 3:
        return 1.0
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))
    return sd or 1.0


def choose_peers(target, rows, k=PEER_COUNT):
    """The k closest companies to target among rows, each with its distance and what it was compared on."""
    pool = [r for r in rows if r["sane"] and r["cik"] != target["cik"] and r["ticker"] != target["ticker"]
            and (r["sector"] == target["sector"] or not target["sector"])]
    scale = {f: _spread([r["features"][f] for r in pool]) for f in FEATURES}
    scored = []
    for r in pool:
        d2, used = 0.0, 0
        for f in FEATURES:
            a, b = target["features"][f], r["features"][f]
            if a is None or b is None:
                d2 += 1.0  # a feature that can't be compared counts as one spread apart
            else:
                d2 += ((a - b) / scale[f]) ** 2
                used += 1
        if used == 0:
            continue
        scored.append((math.sqrt(d2) + industry_step(target["sic"], r["sic"]), r))
    scored.sort(key=lambda x: (x[0], x[1]["ticker"]))
    return [(d, r) for d, r in scored[:k]]


def per_share(target, method, multiple):
    base, fig = METHODS[method]
    value = multiple * target["figures"][fig]
    if base == "ev":
        value = value - (target["debt"] or 0) + (target["cash"] or 0)
    return max(value, 0.0) / target["shares"]


def value(target, rows, k=PEER_COUNT):
    """The fair value estimate for target (a build_row result) against rows (other build_row results)."""
    chosen = choose_peers(target, rows, k)
    methods = []
    for name in methods_for(target["sector"]):
        fig = target["figures"][METHODS[name][1]]
        mults = sorted(r["multiples"][name] for _, r in chosen if r["multiples"][name])
        entry = {"method": name, "figure": METHODS[name][1], "company_figure": fig, "peer_count": len(mults),
                 "peer_median": None, "peer_p25": None, "peer_p75": None, "value": None, "low": None, "high": None,
                 "company_multiple": target["multiples"][name], "used": False}
        if fig is None or fig <= 0:
            entry["why_not"] = f"The company's {METHODS[name][1]} isn't positive, so this multiple can't price it."
        elif len(mults) < MIN_PEERS:
            entry["why_not"] = f"Only {len(mults)} peers have a positive {name}; at least {MIN_PEERS} are needed."
        else:
            med, p25, p75 = (peers.percentile(mults, q) for q in (0.5, 0.25, 0.75))
            entry.update(peer_median=med, peer_p25=p25, peer_p75=p75, used=True,
                         value=per_share(target, name, med), low=per_share(target, name, p25), high=per_share(target, name, p75))
        methods.append(entry)
    used = [m for m in methods if m["used"]]
    out = {"methods": methods, "peers": [{"distance": d, **{key: r[key] for key in PEER_KEYS}} for d, r in chosen]}
    if not used:
        return {**out, "available": False, "reason": "None of the valuation multiples could be applied (the company or too few peers have positive earnings, sales or book value)."}
    med = lambda key: peers.percentile(sorted(m[key] for m in used), 0.5)
    fair, low, high = med("value"), med("low"), med("high")
    price = target["price"]
    verdict = "undervalued" if price < low else "overvalued" if price > high else "fairly valued"
    return {**out, "available": True, "fair_value": fair, "low": low, "high": high, "price": price,
            "upside_pct": (fair / price - 1) * 100, "verdict": verdict}


PEER_KEYS = ("ticker", "name", "sic", "industry", "fy_end", "price", "price_date", "market_cap", "figures", "multiples", "features")


# ---------- Building the peer universe and the back-test (prebuild.py, on GitHub's machines) ----------

BACKTEST_START = 2018
PRICE_START = date(BACKTEST_START, 6, 1)


def formation_dates(last_price_day):
    """June 30 of each year from 2018 whose following 12 months are already priced."""
    out, y = [], BACKTEST_START
    while date(y + 1, 6, 30) <= last_price_day:
        out.append(date(y, 6, 30))
        y += 1
    return out


def fetch_histories(tickers, today=None, workers=4):
    """{ticker: prices.history} for every ticker Yahoo has; the rest are left out."""
    today = today or date.today()

    def one(t):
        for attempt in range(3):
            try:
                return t, prices.history(t, PRICE_START, today)
            except Exception as e:
                if attempt == 2 or "404" in str(e):
                    print(f"[{t}] price history unavailable: {e!r}", flush=True)
                    return t, None
                time.sleep(5 * (attempt + 1))  # usually Yahoo asking to slow down

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return {t: h for t, h in pool.map(one, tickers) if h and h["days"]}


def rows_at(funds, histories, day=None):
    """build_row for every company at the close on day (the latest close when day is None). One row per SEC company."""
    rows, seen = [], set()
    for t, fund in funds.items():
        h = histories.get(t)
        if not h or fund.get("cik") in seen:
            continue
        i = len(h["days"]) - 1 if day is None else prices.on_or_before(h, day)
        if i is None:
            continue
        row = build_row(fund, prices.raw_close(h, i), h["days"][i], as_of=day)
        if row:
            rows.append(row)
            seen.add(fund.get("cik"))
    return rows


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return cov / (sx * sy) if sx and sy else None


def _mean(v):
    return sum(v) / len(v) if v else None


def _tstat(v):
    if len(v) < 2:
        return None
    m = _mean(v)
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
    return m / (sd / math.sqrt(len(v))) if sd else None


def cohort(funds, histories, day):
    """Every company's estimate as of day and its total return over the next 12 months."""
    rows = rows_at(funds, histories, day)
    end = day + timedelta(days=365)
    out = []
    for row in rows:
        if not row["sane"]:
            continue
        h = histories[row["ticker"]]
        i, j = prices.on_or_before(h, day), prices.on_or_before(h, end)
        if i is None or j is None:
            continue
        est = value(row, rows)
        if not est["available"]:
            continue
        out.append({"ticker": row["ticker"], "sector": row["sector"], "gap": est["fair_value"] / row["price"] - 1,
                    "verdict": est["verdict"], "ret": h["adjclose"][j] / h["adjclose"][i] - 1})
    return out


def summarize_cohort(day, items):
    items = sorted(items, key=lambda x: -x["gap"])  # most undervalued first
    n = len(items)
    q = [items[i * n // 5:(i + 1) * n // 5] for i in range(5)]
    qret = [_mean([x["ret"] for x in g]) for g in q]
    by_verdict = {v: [x["ret"] for x in items if x["verdict"] == v] for v in ("undervalued", "fairly valued", "overvalued")}
    return {
        "formed": day.isoformat(), "companies": n, "all_return": _mean([x["ret"] for x in items]),
        "quintile_returns": qret, "spread": qret[0] - qret[4],
        "rank_correlation": spearman([x["gap"] for x in items], [x["ret"] for x in items]),
        "verdicts": {v: {"count": len(r), "return": _mean(r)} for v, r in by_verdict.items()},
    }


def backtest(funds, histories):
    last_day = max(h["days"][-1] for h in histories.values())
    cohorts = [summarize_cohort(d, cohort(funds, histories, d)) for d in formation_dates(last_day)]
    spreads = [c["spread"] for c in cohorts]
    ics = [c["rank_correlation"] for c in cohorts if c["rank_correlation"] is not None]
    under_minus_over = [c["verdicts"]["undervalued"]["return"] - c["verdicts"]["overvalued"]["return"] for c in cohorts
                        if c["verdicts"]["undervalued"]["return"] is not None and c["verdicts"]["overvalued"]["return"] is not None]
    return {
        "method": ("As of June 30 of each year, every Russell 1000 company in today's index was valued against its peers "
                   "using only 10-Ks filed by that date and that day's closing prices. Stocks were split into five equal "
                   "groups by how far the fair value was above the price, and each group's average total return "
                   "(dividends included) over the next 12 months was measured."),
        "caveats": [
            "Survivorship bias: only companies in today's Russell 1000 are tested, so companies that shrank, were bought or "
            "went bankrupt since 2018 are missing. That tends to flatter every group's returns.",
            f"{len(cohorts)} yearly cohorts is a short history; a few market regimes dominate the result.",
            "Returns are equal-weighted and ignore trading costs.",
        ],
        "cohorts": cohorts,
        "average": {
            "quintile_returns": [_mean([c["quintile_returns"][i] for c in cohorts]) for i in range(5)] if cohorts else [],
            "spread": _mean(spreads), "spread_t": _tstat(spreads), "spread_positive_years": sum(1 for s in spreads if s > 0),
            "rank_correlation": _mean(ics), "rank_correlation_t": _tstat(ics),
            "undervalued_minus_overvalued": _mean(under_minus_over), "undervalued_minus_overvalued_t": _tstat(under_minus_over),
        },
        "years": len(cohorts),
    }


def build(out_dir, tickers, today=None):
    """valuation.json for the API: every company valued at the latest close, plus the back-test."""
    funds = {}
    for t in tickers:
        try:
            with open(os.path.join(out_dir, t, "fundamentals.json")) as f:
                body = json.load(f)
            if "__unavailable__" not in body:
                funds[t] = body
        except (OSError, ValueError):
            continue
    histories = fetch_histories(list(funds), today)
    rows = rows_at(funds, histories)
    print(f"Valuation: {len(funds)} companies with 10-K inputs, {len(histories)} with prices, {len(rows)} valued", flush=True)
    return {"source": SOURCE, "rows": rows, "backtest": backtest(funds, histories)}


_cache = {"path": None, "mtime": None, "data": None}


def load(path):
    """valuation.json from the downloaded ready-made results, re-read when the file changes."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _cache["path"] != path or _cache["mtime"] != mtime:
        with open(path) as f:
            _cache.update(path=path, mtime=mtime, data=json.load(f))
    return _cache["data"]


# ---------- The API's answer for one company ----------

def report(fund, price, price_date, universe, price_note=""):
    """Everything the Fair Value tab shows: the estimate, each method, the peers and why, the sources, the back-test."""
    base = {"ticker": fund["ticker"], "name": fund.get("name", ""), "source": universe.get("source", SOURCE),
            "peers_built_at": universe.get("built_at"), "backtest": universe.get("backtest"), "price_note": price_note}
    target = build_row(fund, price, price_date)
    if target is None:
        return {**base, "available": False,
                "reason": "The latest 10-K is missing revenue or a diluted share count in SEC's XBRL data, so the company can't be valued."}
    year, _ = pick_years(fund)
    est = value(target, universe["rows"])
    notes = []
    if not target["sane"]:
        notes.append("The market value from the filed share count looks out of line with sales (often a company with several "
                     "share classes that reports shares in another class). Treat this estimate with care.")
    if target["debt"] is None:
        notes.append("No debt is tagged in the 10-K, so debt is counted as zero.")
    if target["sector"] is None:
        notes.append("SEC's industry code for this company doesn't map to a sector, so peers come from the whole Russell 1000.")
    sources = {name: hit for name, hit in year["values"].items() if hit}
    return {
        **base, **est, "notes": notes,
        "company": {key: target[key] for key in ("sic", "industry", "sector", "fy_end", "fiscal_year", "filed", "price", "price_date",
                                                 "shares", "shares_source", "market_cap", "debt", "cash", "ev", "debt_parts",
                                                 "figures", "multiples", "features")},
        "sources": sources,
    }
