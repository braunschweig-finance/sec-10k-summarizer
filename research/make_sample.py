"""Pick the research sample: a random 150 of today's S&P 500 companies,
leaving out the Financials and Real Estate sectors (banks, insurers and REITs
don't fit operating-income ratios).

Source: Wikipedia's "List of S&P 500 companies" constituents table, saved with
the date it was read. Standard library only. Run:  python make_sample.py
Writes sp500_snapshot.csv (full list) and tickers.txt (the sample).
"""
import csv
import random
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
USER_AGENT = "Jacob Braunschweig student research jacob.braunschweig@gmail.com"
HERE = Path(__file__).parent
SAMPLE_SIZE = 150
SEED = 2026  # fixed, so the same sample comes out every time
EXCLUDED_SECTORS = {"Financials", "Real Estate"}


class ConstituentsTable(HTMLParser):
    """Collects the rows of the table with id="constituents"."""

    def __init__(self):
        super().__init__()
        self.depth = 0  # table nesting depth inside the constituents table
        self.rows, self.row, self.cell, self.in_cell = [], None, "", False

    def handle_starttag(self, tag, attrs):
        if tag == "table" and (self.depth or dict(attrs).get("id") == "constituents"):
            self.depth += 1
        elif self.depth == 1 and tag == "tr":
            self.row = []
        elif self.depth == 1 and tag in ("td", "th"):
            self.in_cell, self.cell = True, ""

    def handle_endtag(self, tag):
        if tag == "table" and self.depth:
            self.depth -= 1
        elif self.depth == 1 and tag in ("td", "th") and self.row is not None:
            self.row.append(self.cell.strip())
            self.in_cell = False
        elif self.depth == 1 and tag == "tr" and self.row:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.in_cell:
            self.cell += data


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8")
    parser = ConstituentsTable()
    parser.feed(html)
    header, body = parser.rows[0], parser.rows[1:]
    sym, name, sector = header.index("Symbol"), header.index("Security"), header.index("GICS Sector")
    companies = [(r[sym].replace(".", "-"), r[name], r[sector]) for r in body]
    print(f"Read {len(companies)} constituents from Wikipedia on {date.today()}")

    with open(HERE / "sp500_snapshot.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "company", "gics_sector", "source", "read_on"])
        for c in companies:
            w.writerow([*c, URL, date.today().isoformat()])

    eligible = sorted(c for c in companies if c[2] not in EXCLUDED_SECTORS)
    sample = sorted(random.Random(SEED).sample(eligible, SAMPLE_SIZE))
    (HERE / "tickers.txt").write_text("\n".join(c[0] for c in sample) + "\n", encoding="utf-8")
    print(f"{len(eligible)} non-financial, non-real-estate companies; sampled {len(sample)} into tickers.txt")


if __name__ == "__main__":
    main()
