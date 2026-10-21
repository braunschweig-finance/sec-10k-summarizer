"""
Insider buying and selling: open-market trades by a company's officers, directors and 10% owners over the last
12 months, from the Form 4s they must file within two business days of each trade.

Only transaction codes P (open-market or private purchase) and S (open-market or private sale) count. Option
exercises, grants, tax withholding and gifts aren't decisions to buy or sell, so they're left out. A sale flagged as
made under a Rule 10b5-1 plan was scheduled in advance, so those are totalled separately. Amendments (4/A) are
left out so a trade isn't counted twice.

Two sources, same numbers:
  - Live: each Form 4's XML file, read straight from EDGAR (up to LIVE_CAP filings, newest first).
  - Prebuild: SEC's quarterly "insider transactions data sets" (the same Form 4 fields, every filer in one file per
    quarter, https://www.sec.gov/dera/data/form-345), plus each Form 4 filed after the newest quarter in the set.
    One download covers all 1,000 companies, instead of about 80,000 single requests.
"""
import csv
import io
import json
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta

import sec_feed

WINDOW_DAYS = 365
RECENT_DAYS = 90
CLUSTER_DAYS = 30
LIVE_CAP = int(os.environ.get("INSIDER_LIVE_CAP", "80"))  # SEC answers 2-4 a second, and the API stops a lookup after 120 s
BULK_DIR = "INSIDER_BULK_DIR"  # environment variable naming the folder prepare_bulk() wrote
DATASETS_PAGE = "https://www.sec.gov/dera/data/form-345"


# ---------- One Form 4 XML ----------

def _text(el, path):
    found = el.find(path)
    if found is None:
        return ""
    v = found.find("value")
    return ((v.text if v is not None else found.text) or "").strip()


def _flag(el, path):
    return _text(el, path).lower() in ("1", "true")


def role(director, officer, ten_pct, title):
    parts = []
    if officer:
        parts.append(title.strip() or "Officer")
    if director:
        parts.append("Director")
    if ten_pct:
        parts.append("10% owner")
    return ", ".join(parts) or "Other"


def parse_form4(xml_bytes, accession, filed):
    """Trades (code P or S) in one Form 4, each a dict with the fields the summary needs."""
    root = ET.fromstring(xml_bytes)
    if _text(root, "documentType") != "4":
        return []
    owners = []
    for o in root.findall("reportingOwner"):
        rel = o.find("reportingOwnerRelationship")
        owners.append({"cik": _text(o, "reportingOwnerId/rptOwnerCik"), "name": _text(o, "reportingOwnerId/rptOwnerName"),
                       "role": role(_flag(rel, "isDirector"), _flag(rel, "isOfficer"), _flag(rel, "isTenPercentOwner"),
                                    _text(rel, "officerTitle")) if rel is not None else "Other"})
    plan = _flag(root, "aff10b5One")
    out = []
    for t in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        code = _text(t, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        out.append({"accession": accession, "filed": filed, "date": _text(t, "transactionDate")[:10], "code": code,
                    "shares": _num(_text(t, "transactionAmounts/transactionShares")),
                    "price": _num(_text(t, "transactionAmounts/transactionPricePerShare")),
                    "owners": owners, "plan": plan})
    return out


def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except ValueError:
        return None


def form4_xml_url(cik, f):
    # The listed primary document is SEC's styled copy (xslF345X06/form4.xml); the raw XML has the same name one folder up
    return sec_feed.folder(cik, f["accession"]) + f["doc"].split("/")[-1]


# ---------- SEC's quarterly insider transactions data sets (prebuild only) ----------

def _quarter_end(name):
    y, q = int(name[:4]), int(name[5])
    return date(y, 3 * q, 31 if q in (1, 4) else 30)


def _bulk_date(s):
    # The data sets write dates as 28-SEP-2026
    return datetime.strptime(s.strip(), "%d-%b-%Y").date().isoformat() if s.strip() else ""


csv.field_size_limit(1 << 28)  # REMARKS and footnote fields can be long


def _tsv(z, name):
    with z.open(name) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t",
                                  quoting=csv.QUOTE_NONE)


def bulk_rows(zip_bytes):
    """{issuer CIK: [trades]} from one quarter's data set, with the same fields parse_form4 gives."""
    z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    subs = {}
    for r in _tsv(z, "SUBMISSION.tsv"):
        if r["DOCUMENT_TYPE"] == "4":
            subs[r["ACCESSION_NUMBER"]] = (r["ISSUERCIK"].zfill(10), _bulk_date(r["FILING_DATE"]), r.get("AFF10B5ONE", "") in ("1", "true"))
    owners = {}
    for r in _tsv(z, "REPORTINGOWNER.tsv"):
        if r["ACCESSION_NUMBER"] in subs:
            rel = r["RPTOWNER_RELATIONSHIP"].lower()
            owners.setdefault(r["ACCESSION_NUMBER"], []).append({
                "cik": r["RPTOWNERCIK"], "name": r["RPTOWNERNAME"],
                "role": role("director" in rel, "officer" in rel, "tenpercent" in rel, r["RPTOWNER_TITLE"])})
    out = {}
    for r in _tsv(z, "NONDERIV_TRANS.tsv"):
        acc = r["ACCESSION_NUMBER"]
        if r["TRANS_CODE"] not in ("P", "S") or acc not in subs:
            continue
        issuer, filed, plan = subs[acc]
        out.setdefault(issuer, []).append({
            "accession": acc, "filed": filed, "date": _bulk_date(r["TRANS_DATE"]), "code": r["TRANS_CODE"],
            "shares": _num(r["TRANS_SHARES"]), "price": _num(r["TRANS_PRICEPERSHARE"]),
            "owners": owners.get(acc, []), "plan": plan})
    return out


def prepare_bulk(out_dir="insider_bulk", today=None):
    """Downloads the quarterly data sets covering the last 12 months and writes one file of trades per company, then
    sets INSIDER_BULK_DIR so get_insider_trades (in this process and the prebuild's workers) reads them."""
    start = ((today or date.today()) - timedelta(days=WINDOW_DAYS)).isoformat()
    page = sec_feed.fetch(DATASETS_PAGE).decode("utf-8", errors="replace")
    links = {}
    for href in re.findall(r'href="([^"]*?(\d{4}q[1-4])_form345\.zip)"', page):
        links.setdefault(href[1], href[0])
    wanted = sorted(q for q in links if _quarter_end(q).isoformat() >= start)
    if not wanted:
        raise RuntimeError("SEC's insider data set page lists no recent quarters")
    os.makedirs(out_dir, exist_ok=True)
    merged = {}
    for q in wanted:
        url = links[q] if links[q].startswith("http") else "https://www.sec.gov" + links[q]
        for cik, rows in bulk_rows(sec_feed.fetch(url)).items():
            merged.setdefault(cik, []).extend(rows)
        print(f"[insiders] data set {q} read", flush=True)
    for cik, rows in merged.items():
        with open(os.path.join(out_dir, f"{cik}.json"), "w") as f:
            json.dump([r for r in rows if r["date"] >= start], f)
    meta = {"through": _quarter_end(wanted[-1]).isoformat(), "quarters": wanted}
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f)
    os.environ[BULK_DIR] = os.path.abspath(out_dir)
    print(f"[insiders] {len(merged)} companies, data sets through {meta['through']}", flush=True)
    return meta


def _bulk(cik):
    d = os.environ.get(BULK_DIR)
    if not d:
        return None, None
    with open(os.path.join(d, "meta.json")) as f:
        meta = json.load(f)
    try:
        with open(os.path.join(d, f"{cik}.json")) as f:
            return json.load(f), meta
    except FileNotFoundError:
        return [], meta


# ---------- Summary ----------

def summarize(trades, cik, start, today):
    """Totals, notable trades and a plain-language signal from a list of trades."""
    recent = (date.fromisoformat(today) - timedelta(days=RECENT_DAYS)).isoformat()
    # One row per filing and trade direction: a Form 4 often splits one sale into many fills at different prices
    grouped = {}
    for t in trades:
        if not t["date"] or t["date"] < start or t["date"] > today or not t["shares"] or not t["price"]:
            continue
        g = grouped.setdefault((t["accession"], t["code"]), {
            "accession": t["accession"], "filed": t["filed"], "first": t["date"], "last": t["date"],
            "type": "Buy" if t["code"] == "P" else "Sell", "shares": 0.0, "value": 0.0, "plan": t["plan"],
            "insider": "; ".join(o["name"] for o in t["owners"]) or "Unknown",
            "insider_id": t["owners"][0]["cik"] if t["owners"] else t["accession"],
            "role": t["owners"][0]["role"] if t["owners"] else "",
            "url": sec_feed.index_url(cik, t["accession"])})
        g["shares"] += t["shares"]
        g["value"] += t["shares"] * t["price"]
        g["first"], g["last"] = min(g["first"], t["date"]), max(g["last"], t["date"])
    rows = sorted(grouped.values(), key=lambda g: g["last"], reverse=True)
    for g in rows:
        g["avg_price"] = round(g["value"] / g["shares"], 2)
        g["value"] = round(g["value"], 2)

    def total(kind, since=start, plan=None):
        sel = [g for g in rows if g["type"] == kind and g["last"] >= since and (plan is None or g["plan"] == plan)]
        return {"count": len(sel), "insiders": len({g["insider_id"] for g in sel}),
                "shares": round(sum(g["shares"] for g in sel)), "value": round(sum(g["value"] for g in sel), 2)}

    buys, sells = total("Buy"), total("Sell")
    planned = total("Sell", plan=True)
    buys_90, sells_90 = total("Buy", recent), total("Sell", recent)
    cluster = cluster_buying(rows)
    return {
        "buys": buys, "sells": sells, "planned_sells": planned,
        "net_value": round(buys["value"] - sells["value"], 2),
        "last_90_days": {"buys": buys_90, "sells": sells_90, "net_value": round(buys_90["value"] - sells_90["value"], 2)},
        "cluster": cluster, "signal": signal(buys, sells, planned, cluster),
        "purchases": [g for g in rows if g["type"] == "Buy"][:25],
        "top_sales": sorted((g for g in rows if g["type"] == "Sell"), key=lambda g: g["value"], reverse=True)[:10],
        "trades": len(rows),
    }


def cluster_buying(rows):
    """The busiest 30-day stretch of open-market buying when 3 or more different insiders bought in it, else None.
    Several insiders buying at once is the pattern studies find most telling."""
    buys = sorted((g for g in rows if g["type"] == "Buy"), key=lambda g: g["last"])
    best = None
    for i, g in enumerate(buys):
        end = (date.fromisoformat(g["last"]) + timedelta(days=CLUSTER_DAYS)).isoformat()
        group = [b for b in buys[i:] if b["last"] <= end]
        people = {b["insider_id"] for b in group}
        if len(people) >= 3 and (best is None or len(people) > best["insiders"]):
            best = {"from": group[0]["last"], "to": group[-1]["last"], "insiders": len(people),
                    "value": round(sum(b["value"] for b in group), 2)}
    return best


def signal(buys, sells, planned, cluster):
    if cluster:
        return f"Cluster buying: {cluster['insiders']} insiders bought within 30 days ({cluster['from']} to {cluster['to']})."
    if buys["count"] and buys["value"] >= sells["value"]:
        return "Net buying: insiders bought more stock than they sold in the last 12 months."
    if not buys["count"] and not sells["count"]:
        return "No open-market insider trades in the last 12 months."
    if sells["value"] and planned["value"] >= 0.75 * sells["value"]:
        return "Selling, mostly under preset 10b5-1 plans (scheduled in advance, so a weaker signal)."
    if not buys["count"]:
        return "Selling only: no open-market insider purchases in the last 12 months."
    return "Net selling: insiders sold more than they bought in the last 12 months."


def get_insider_trades(ticker_symbol, today=None):
    cik, name = sec_feed.company(ticker_symbol)
    today_s = (today or date.today()).isoformat()
    start = (date.fromisoformat(today_s) - timedelta(days=WINDOW_DAYS)).isoformat()
    _, filings = sec_feed.filings(cik, start)
    form4s = [f for f in filings if f["form"] == "4"]
    trades, meta = _bulk(cik)
    if meta is not None:
        to_read = [f for f in form4s if f["filed"] > meta["through"]]
        source = f"SEC insider transactions data sets ({meta['quarters'][0]} to {meta['quarters'][-1]}) plus each Form 4 filed since {meta['through']}"
        capped = False
    else:
        trades, to_read = [], form4s[:LIVE_CAP]
        capped = len(form4s) > LIVE_CAP
        source = "Each Form 4 XML filing on SEC EDGAR"
    read = 0
    for f in to_read:
        try:
            trades += parse_form4(sec_feed.fetch(form4_xml_url(cik, f)), f["accession"], f["filed"])
            read += 1
        except Exception as e:
            print(f"[{ticker_symbol}] Form 4 {f['accession']} unreadable: {e!r}", flush=True)
    covered_from = to_read[-1]["filed"] if capped else start
    summary = summarize(trades, cik, covered_from, today_s)
    print(f"[{ticker_symbol}] insiders: {summary['trades']} trades, {len(form4s)} Form 4s, {read} read one by one", flush=True)
    return {"ticker": ticker_symbol, "name": name, "cik": cik, "from": covered_from, "to": today_s,
            "form4_count": len(form4s), "capped": capped, "source": source, **summary}
