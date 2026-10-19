"""Pay Efficiency data pull.

For each company and fiscal year 2022-2025 it collects:
  - CEO pay from the Pay Versus Performance table in the DEF 14A XBRL
    (ecd:PeoTotalCompAmt, ecd:PeoActuallyPaidCompAmt, ecd:TotalShareholderRtnAmt)
  - 10-K figures from SEC companyfacts (operating income, net income,
    assets, liabilities, equity), matched to the same fiscal year end
and records the accession number of the filing behind every number.

Standard library only. Run:  python pull_pay_efficiency.py [tickers.txt]
(tickers.txt: one ticker per line; without it the 20-company pilot list runs)
Writes pay_efficiency_data.csv and pay_efficiency_log.txt next to this script.

Rules (decided 2026-10-19):
  - Two CEOs in one year: their pay is added together (ceo_count says how many).
  - Same fact tagged twice for one CEO and year: kept once.
  - A year's pay comes from the first proxy that reports it (the original).
  - 10-K values come from the first 10-K that reports that year (as originally filed).
  - No us-gaap:OperatingIncomeLoss tag: pretax income is used and op_income_tag says so.
"""
import csv
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

USER_AGENT = "Jacob Braunschweig student research jacob.braunschweig@gmail.com"
HERE = Path(__file__).parent
PILOT = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JNJ", "PG", "KO", "PEP",
         "CAT", "DE", "HON", "XOM", "CVX", "WMT", "HD", "MCD", "NKE", "UNH"]
YEARS = range(2022, 2026)
XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
PVP_TAGS = {"PeoTotalCompAmt": "peo_total_comp", "PeoActuallyPaidCompAmt": "peo_cap"}

OP_TAGS = ["OperatingIncomeLoss"]
PRETAX_TAGS = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
]
NI_TAGS = ["NetIncomeLoss"]
ASSET_TAGS = ["Assets"]
LIAB_TAGS = ["Liabilities"]
EQUITY_TAGS = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(msg)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            time.sleep(0.3)  # stay well under SEC's 10 requests/second limit
            return data
        except Exception as e:  # retry twice, then give up
            if attempt == 2:
                raise
            log(f"  retry {url}: {e}")
            time.sleep(3)


def fiscal_year(fy_end):
    """52/53-week years can end in the first days of January; count those as the prior year."""
    d = date.fromisoformat(fy_end)
    return d.year - 1 if d.month == 1 and d.day <= 7 else d.year


def days_apart(a, b):
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


# ---------- proxy (DEF 14A) ----------

def instance_url(cik, accn):
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}"
    names = [i["name"] for i in json.loads(fetch(folder + "/index.json"))["directory"]["item"]]
    for n in names:
        if n.endswith("_htm.xml"):
            return f"{folder}/{n}"
    for n in names:
        if n.endswith(".xml") and "FilingSummary" not in n and not n.endswith(("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            return f"{folder}/{n}"
    return None


def pvp_from_filing(cik, accn):
    """Returns {fy_end: {"peo_total_comp", "peo_cap", "ceo_count", "tsr", "flags"}}."""
    url = instance_url(cik, accn)
    if not url:
        return {}
    root = ET.fromstring(fetch(url))
    contexts = {}
    for ctx in root.iter(XBRLI + "context"):
        p = ctx.find(XBRLI + "period")
        end = p.findtext(XBRLI + "endDate") or p.findtext(XBRLI + "instant")
        members = tuple(sorted(f"{m.get('dimension')}={m.text}" for m in ctx.iter(XBRLDI + "explicitMember")))
        contexts[ctx.get("id")] = (end, members)

    facts = []
    for el in root:
        if "}" not in el.tag or "/ecd/" not in el.tag.split("}")[0]:
            continue
        name = el.tag.split("}")[1]
        end, members = contexts.get(el.get("contextRef"), (None, ()))
        try:
            val = float((el.text or "").strip())
        except ValueError:
            continue
        facts.append((name, end, members, val))

    # Fiscal year ends = end dates of the company's own TSR (no dimension).
    fy_ends = sorted({end for name, end, members, val in facts
                      if name == "TotalShareholderRtnAmt" and not members})
    out = {}
    for name, end, members, val in facts:
        if name == "TotalShareholderRtnAmt" and not members:
            out.setdefault(end, {"tsr": val, "flags": []})

    def fy_for(end):
        # A CEO who left mid-year has an earlier end date; map it to the next fiscal year end.
        for fy in fy_ends:
            if date.fromisoformat(fy) >= date.fromisoformat(end) or days_apart(fy, end) <= 10:
                return fy
        return None

    for tag, col in PVP_TAGS.items():
        per_ceo = {}  # (fy, individual) -> value
        for name, end, members, val in facts:
            if name != tag or end is None:
                continue
            other_dims = [m for m in members if not m.startswith("ecd:IndividualAxis=")]
            if other_dims:
                continue  # adjustment breakdowns, not the headline number
            fy = fy_for(end)
            if fy is None:
                continue
            who = members[0].split("=", 1)[1] if members else ""
            key = (fy, who)
            if key in per_ceo and per_ceo[key] != val:
                out[fy]["flags"].append(f"{col} differs for {who or 'CEO'}: {per_ceo[key]} vs {val}")
            per_ceo.setdefault(key, val)
        for fy in out:
            people = {who: v for (f, who), v in per_ceo.items() if f == fy}
            if "" in people and len(people) != 1:
                out[fy]["flags"].append(f"{col}: both total and per-CEO tags; used total")
                people = {"": people[""]}
            if people:
                out[fy][col] = sum(people.values())
                out[fy]["ceo_count"] = len(people)
    return out


# ---------- 10-K (companyfacts) ----------

def tenk_value(gaap, tags, fy_end, flow):
    """First-filed 10-K value for fy_end. flow=True for income-statement items."""
    for tag in tags:
        rows = gaap.get(tag, {}).get("units", {}).get("USD", [])
        hits = []
        for r in rows:
            if r.get("form") != "10-K" or days_apart(r["end"], fy_end) > 10:
                continue
            if flow:
                if "start" not in r or not 340 <= days_apart(r["start"], r["end"]) <= 390:
                    continue
            elif "start" in r:
                continue
            hits.append(r)
        if hits:
            first = min(hits, key=lambda r: r["filed"])
            return first["val"], tag, first["accn"]
    return None, None, None


# ---------- main ----------

def main():
    tickers = PILOT
    if len(sys.argv) > 1:
        tickers = [t.strip().upper() for t in Path(sys.argv[1]).read_text().split() if t.strip()]
    ticker_map = {v["ticker"]: (str(v["cik_str"]).zfill(10), v["title"])
                  for v in json.loads(fetch("https://www.sec.gov/files/company_tickers.json")).values()}

    cols = ["ticker", "cik", "company", "sic", "financial_firm", "fiscal_year", "fy_end", "ceo_count",
            "peo_total_comp", "peo_cap", "tsr", "pvp_accn",
            "operating_income", "op_income_tag", "op_income_accn",
            "net_income", "net_income_accn", "assets", "assets_accn",
            "liabilities", "equity", "pay_efficiency", "flags"]
    rows = []
    for t in tickers:
        if t not in ticker_map:
            log(f"{t}: not in SEC ticker list, skipped")
            continue
        cik, title = ticker_map[t]
        try:
            sub = json.loads(fetch(f"https://data.sec.gov/submissions/CIK{cik}.json"))
            sic = sub.get("sic", "")
            recent = sub["filings"]["recent"]
            proxies = sorted((filed, accn) for form, accn, filed in
                             zip(recent["form"], recent["accessionNumber"], recent["filingDate"])
                             if form == "DEF 14A" and filed >= "2023-01-01")
            pvp = {}
            for filed, accn in proxies:  # oldest first, so the original report wins
                for fy, vals in pvp_from_filing(cik, accn).items():
                    if fy not in pvp and fiscal_year(fy) in YEARS:
                        pvp[fy] = dict(vals, pvp_accn=accn)
            gaap = json.loads(fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"))["facts"].get("us-gaap", {})
        except Exception as e:
            log(f"{t}: FAILED {e}")
            continue

        for fy in sorted(pvp):
            v = pvp[fy]
            op, op_tag, op_accn = tenk_value(gaap, OP_TAGS, fy, True)
            if op is None:
                op, op_tag, op_accn = tenk_value(gaap, PRETAX_TAGS, fy, True)
                if op is not None:
                    op_tag = "PRETAX:" + op_tag
            ni, _, ni_accn = tenk_value(gaap, NI_TAGS, fy, True)
            assets, _, assets_accn = tenk_value(gaap, ASSET_TAGS, fy, False)
            liab, _, _ = tenk_value(gaap, LIAB_TAGS, fy, False)
            eq, _, _ = tenk_value(gaap, EQUITY_TAGS, fy, False)
            cap = v.get("peo_cap")
            eff = cap / op if cap is not None and op and op > 0 else None
            rows.append({
                "ticker": t, "cik": cik, "company": title, "sic": sic,
                "financial_firm": str(sic).isdigit() and 6000 <= int(sic) <= 6799,
                "fiscal_year": fiscal_year(fy), "fy_end": fy, "ceo_count": v.get("ceo_count"),
                "peo_total_comp": v.get("peo_total_comp"), "peo_cap": cap, "tsr": v.get("tsr"),
                "pvp_accn": v["pvp_accn"],
                "operating_income": op, "op_income_tag": op_tag, "op_income_accn": op_accn,
                "net_income": ni, "net_income_accn": ni_accn,
                "assets": assets, "assets_accn": assets_accn,
                "liabilities": liab, "equity": eq,
                "pay_efficiency": eff, "flags": "; ".join(v["flags"]),
            })
        log(f"{t}: {len(pvp)} fiscal years from {len(proxies)} proxies")

    with open(HERE / "pay_efficiency_data.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    log(f"Wrote {len(rows)} rows to pay_efficiency_data.csv")
    (HERE / "pay_efficiency_log.txt").write_text("\n".join(log_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
