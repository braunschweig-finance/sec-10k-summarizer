"""Step 1b: read the Pay Versus Performance numbers straight from each
company's latest DEF 14A XBRL file. SEC's companyfacts summary leaves out
CEO (PEO) pay, so we go to the filing itself.

Standard library only. Run:  python check_pvp_def14a.py
Writes pvp_def14a_check.txt next to this script.
"""
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

USER_AGENT = "Jacob Braunschweig student research jacob.braunschweig@gmail.com"
COMPANIES = {"CAT": "0000018230", "AAPL": "0000320193", "JNJ": "0000200406"}
XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    time.sleep(0.3)  # stay well under SEC's 10 requests/second limit
    return data


def latest_def14a(cik):
    sub = json.loads(fetch(f"https://data.sec.gov/submissions/CIK{cik}.json"))
    recent = sub["filings"]["recent"]
    for form, accn, filed in zip(recent["form"], recent["accessionNumber"], recent["filingDate"]):
        if form == "DEF 14A":
            return accn, filed
    return None, None


def instance_url(cik, accn):
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}"
    items = json.loads(fetch(folder + "/index.json"))["directory"]["item"]
    names = [i["name"] for i in items]
    # SEC extracts inline XBRL into a file ending in _htm.xml.
    for n in names:
        if n.endswith("_htm.xml"):
            return f"{folder}/{n}"
    for n in names:
        if n.endswith(".xml") and "FilingSummary" not in n and not n.endswith(("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            return f"{folder}/{n}"
    return None


def main():
    out = []
    for ticker, cik in COMPANIES.items():
        accn, filed = latest_def14a(cik)
        out.append(f"=== {ticker} DEF 14A accn={accn} filed={filed} ===")
        if not accn:
            out.append("  no DEF 14A found in recent filings")
            continue
        url = instance_url(cik, accn)
        out.append(f"  instance: {url}")
        if not url:
            out.append("  no XBRL instance file in this filing")
            continue
        root = ET.fromstring(fetch(url))
        contexts = {}
        for ctx in root.iter(XBRLI + "context"):
            p = ctx.find(XBRLI + "period")
            start, end, inst = (p.findtext(XBRLI + t) for t in ("startDate", "endDate", "instant"))
            members = [f"{m.get('dimension')}={m.text}" for m in ctx.iter(XBRLDI + "explicitMember")]
            members += [f"{m.get('dimension')}=(typed)" for m in ctx.iter(XBRLDI + "typedMember")]
            contexts[ctx.get("id")] = (f"{start or ''}..{end or inst}", members)
        count = 0
        for el in root:
            tag = el.tag
            if "}" not in tag or "/ecd/" not in tag.split("}")[0]:
                continue
            name = "ecd:" + tag.split("}")[1]
            val = (el.text or "").strip()
            if len(val) > 60:  # shorten long text blocks, keep numbers and flags
                val = val[:60] + "..."
            period, members = contexts.get(el.get("contextRef"), ("?", []))
            dims = " | ".join(members) if members else "(no dimension)"
            out.append(f"  {name} {period} = {val}  [{dims}]")
            count += 1
        out.append(f"  {count} ecd facts")
    text = "\n".join(out)
    Path(__file__).with_name("pvp_def14a_check.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
