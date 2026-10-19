"""Step 1 of the Pay Efficiency data pull: check which Pay Versus Performance
(ecd) XBRL tags SEC actually publishes for a few companies.

Uses SEC's free companyfacts API (one JSON file per company). Standard library
only, so nothing to install. Run:  python check_pvp_tags.py
Writes pvp_tag_check.txt next to this script.
"""
import json
import time
import urllib.request
from pathlib import Path

# SEC asks every script to identify itself with a name and email.
USER_AGENT = "Jacob Braunschweig student research jacob.braunschweig@gmail.com"

# Caterpillar, Apple, Johnson & Johnson (CIKs from SEC's company list).
COMPANIES = {"CAT": "0000018230", "AAPL": "0000320193", "JNJ": "0000200406"}

WANTED = [
    "ecd:PeoTotalCompAmt",
    "ecd:PeoActuallyPaidCompAmt",
    "ecd:TotalShareholderRtnAmt",
    "us-gaap:OperatingIncomeLoss",
    "us-gaap:NetIncomeLoss",
    "us-gaap:Assets",
]


def get_facts(cik):
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def main():
    out = []
    for ticker, cik in COMPANIES.items():
        facts = get_facts(cik)["facts"]
        out.append(f"=== {ticker} (CIK {cik}) ===")
        out.append("Taxonomies: " + ", ".join(sorted(facts)))
        # Any concept with pay/TSR-like names, wherever SEC filed it.
        for tax, concepts in sorted(facts.items()):
            for name in sorted(concepts):
                if tax == "ecd" or "Peo" in name or "ShareholderRtn" in name:
                    out.append(f"  found {tax}:{name}")
        for tag in WANTED:
            tax, name = tag.split(":")
            concept = facts.get(tax, {}).get(name)
            if not concept:
                out.append(f"  MISSING {tag}")
                continue
            for unit, rows in concept["units"].items():
                for r in rows[-4:]:
                    out.append(
                        f"  {tag} [{unit}] {r.get('start', '')}..{r['end']} = {r['val']}"
                        f"  form={r['form']} accn={r['accn']} filed={r['filed']}"
                    )
        time.sleep(0.5)  # stay well under SEC's 10 requests/second limit
    text = "\n".join(out)
    Path(__file__).with_name("pvp_tag_check.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
