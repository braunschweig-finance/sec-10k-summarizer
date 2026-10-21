"""
Offline tests for the red flags (red_flags.py) and insider trades (insiders.py). The inputs are small hand-made
filings, so every expected number can be worked out by hand.
Run from api/:  python -m pytest tests
"""
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import insiders
import red_flags

CIK = "0000320193"


# ---------- Red flags ----------

EIGHT_K_502 = (
    "Item 5.02 Departure of Directors or Certain Officers. On April 9, 2026, Jane Roe informed the Board that she will "
    "resign as Chief Financial Officer of the Company, effective May 1, 2026. Ms. Roe's decision was not the result of any "
    "disagreement with the Company. In the event of a qualifying termination, the Chief Executive Officer would receive "
    "two times salary. The Board elected John Doe as a director. Item 9.01 Financial Statements and Exhibits. 104 Cover Page."
)
EIGHT_K_502_RETIRE = (
    "Item 5.02 Departure of Directors. The Company announced that Bob Smith, Chairman and Chief Executive Officer, will "
    "retire from the Company at the end of the year. The Board appointed Ann Lee as Chief Executive Officer, effective January 1."
)
EIGHT_K_502_BOARD = (
    "Item 5.02 Election of Directors. The Board increased its size to 12 and elected Mary Major as a director. "
    "Ms. Major will participate in the director compensation program, including a retirement plan for directors."
)
EIGHT_K_401 = (
    "Item 4.01 Changes in Registrant's Certifying Accountant. On March 2, 2026, the Audit Committee dismissed Old & Co. LLP "
    "as the Company's independent registered public accounting firm. There were no disagreements with Old & Co. "
    "Item 9.01 Exhibits. Exhibit 16.1 Letter from Old & Co."
)


def filing(form, items="", acc="0000320193-26-000001", filed="2026-04-10"):
    return {"form": form, "filed": filed, "accession": acc, "items": items, "doc": "doc.htm"}


def test_cfo_resignation_is_flagged_but_severance_boilerplate_is_not():
    found = red_flags.leadership_departures(EIGHT_K_502)
    assert [(r, k) for r, k, _ in found] == [("CFO", "resignation or exit")]
    assert "will resign as Chief Financial Officer" in found[0][2]


def test_ceo_retirement_and_board_only_502():
    assert [(r, k) for r, k, _ in red_flags.leadership_departures(EIGHT_K_502_RETIRE)] == [("CEO", "retirement")]
    assert red_flags.leadership_departures(EIGHT_K_502_BOARD) == []


def test_flags_from_filings():
    texts = {"a": EIGHT_K_502, "b": EIGHT_K_401, "c": EIGHT_K_502_BOARD, "d": "Item 2.02 Results of Operations."}
    filings = [
        filing("8-K", "5.02,9.01", "a"), filing("8-K", "4.01,9.01", "b"), filing("8-K", "5.02", "c"),
        filing("8-K", "2.02,9.01", "d"), filing("8-K/A", "4.02", "e"), filing("NT 10-K", "", "f"), filing("10-Q", "", "g"),
    ]
    flags = red_flags.flags_from_filings(CIK, filings, read=lambda cik, f: texts[f["accession"]])
    assert [(f["flag"], f["severity"]) for f in flags] == [
        ("CFO leaving", "medium"), ("Auditor change", "medium"), ("Late filing", "high")]
    assert "dismissed Old & Co. LLP" in flags[1]["quote"]
    assert flags[0]["url"] == "https://www.sec.gov/Archives/edgar/data/320193/a/a-index.htm"


def test_item_section_stops_at_next_item():
    s = red_flags.item_section(EIGHT_K_401, "4.01")
    assert "dismissed" in s and "Exhibit 16.1" not in s


# ---------- Insider trades ----------

FORM4 = b"""<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0001</rptOwnerCik><rptOwnerName>Cook Timothy</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>1</isOfficer><officerTitle>CEO</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <aff10b5One>true</aff10b5One>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-10-02</value></transactionDate>
      <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><footnoteId id="F1"/></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-10-02</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>600</value></transactionShares>
        <transactionPricePerShare><value>250.00</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-10-03</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>400</value></transactionShares>
        <transactionPricePerShare><value>255.00</value></transactionPricePerShare></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""


def test_parse_form4_keeps_only_open_market_trades():
    rows = insiders.parse_form4(FORM4, "acc-1", "2026-10-04")
    assert [(r["code"], r["shares"], r["price"]) for r in rows] == [("S", 600, 250.0), ("S", 400, 255.0)]
    assert rows[0]["plan"] and rows[0]["owners"][0]["role"] == "CEO, Director"


def buy(acc, who, day, shares, price):
    return {"accession": acc, "filed": day, "date": day, "code": "P", "shares": shares, "price": price, "plan": False,
            "owners": [{"cik": who, "name": f"Insider {who}", "role": "Director"}]}


def test_summary_totals_and_cluster():
    trades = insiders.parse_form4(FORM4, "acc-1", "2026-10-04") + [
        buy("b1", "A", "2026-06-01", 1000, 10.0),   # $10,000
        buy("b2", "B", "2026-06-10", 2000, 11.0),   # $22,000
        buy("b3", "C", "2026-06-25", 500, 12.0),    # $6,000
        buy("b4", "D", "2025-01-01", 9999, 1.0),    # before the window
    ]
    s = insiders.summarize(trades, CIK, "2025-10-21", "2026-10-21")
    # One sale filing: 600 x 250 + 400 x 255 = 150,000 + 102,000 = 252,000 over 1,000 shares = $252.00 average
    sale = s["top_sales"][0]
    assert (sale["shares"], sale["value"], sale["avg_price"], sale["plan"]) == (1000, 252000.0, 252.0, True)
    assert s["sells"] == {"count": 1, "insiders": 1, "shares": 1000, "value": 252000.0}
    assert s["buys"] == {"count": 3, "insiders": 3, "shares": 3500, "value": 38000.0}
    assert s["net_value"] == 38000.0 - 252000.0
    assert s["planned_sells"]["value"] == 252000.0
    # Only the sale (Oct 2-3) falls in the last 90 days
    assert s["last_90_days"]["buys"]["count"] == 0 and s["last_90_days"]["sells"]["value"] == 252000.0
    assert s["cluster"] == {"from": "2026-06-01", "to": "2026-06-25", "insiders": 3, "value": 38000.0}
    assert s["signal"].startswith("Cluster buying: 3 insiders")


def test_signal_wording():
    none = {"count": 0, "value": 0}
    assert insiders.signal(none, none, none, None).startswith("No open-market")
    sells = {"count": 4, "value": 100}
    assert insiders.signal(none, sells, {"count": 3, "value": 80}, None).startswith("Selling, mostly under preset")
    assert insiders.signal(none, sells, {"count": 0, "value": 0}, None).startswith("Selling only")
    assert insiders.signal({"count": 1, "value": 10}, sells, {"count": 0, "value": 0}, None).startswith("Net selling")


def test_bulk_rows_match_xml_fields():
    def tsv(header, *rows):
        return "\t".join(header) + "\n" + "".join("\t".join(r) + "\n" for r in rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("SUBMISSION.tsv", tsv(["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK", "AFF10B5ONE"],
                                         ["acc-1", "04-OCT-2026", "4", "320193", "1"], ["acc-2", "05-OCT-2026", "4/A", "320193", "0"]))
        z.writestr("REPORTINGOWNER.tsv", tsv(["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME", "RPTOWNER_RELATIONSHIP", "RPTOWNER_TITLE"],
                                             ["acc-1", "0001", "Cook Timothy", "Director,Officer", "CEO"]))
        z.writestr("NONDERIV_TRANS.tsv", tsv(["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_SHARES", "TRANS_PRICEPERSHARE"],
                                             ["acc-1", "02-OCT-2026", "M", "1000", ""], ["acc-1", "02-OCT-2026", "S", "600.0", "250.00"],
                                             ["acc-1", "03-OCT-2026", "S", "400.0", "255.00"], ["acc-2", "03-OCT-2026", "S", "1", "1"]))
    bulk = insiders.bulk_rows(buf.getvalue())
    xml = insiders.parse_form4(FORM4, "acc-1", "2026-10-04")
    assert list(bulk) == [CIK]
    assert bulk[CIK] == xml


@pytest.mark.parametrize("name,end", [("2025q4", "2025-12-31"), ("2026q1", "2026-03-31"), ("2026q2", "2026-06-30"), ("2026q3", "2026-09-30")])
def test_quarter_end(name, end):
    assert insiders._quarter_end(name).isoformat() == end


# Sentences from real 8-Ks that mention a CEO but aren't this company's CEO or CFO leaving
@pytest.mark.parametrize("text,name", [
    ("Marianne Lake, current CEO of CCB, has decided to retire from the Firm after more than 25 years of service.", "JPMORGAN CHASE & CO"),
    ("Theodore Colbert III ceased to serve as an elected officer and as President and Chief Executive Officer of Boeing Defense, Space & Security, effective September 20, 2024.", "BOEING CO"),
    ("Following his retirement from Collins Aerospace, Mr. Ortberg served as a special advisor to the office of the Chief Executive Officer for RTX Corporation.", "BOEING CO"),
    ("Ravi Ahuja notified the Board of his intention to resign as a director due to the time commitment required of his role as President and CEO of Sony Pictures Entertainment.", "Roku, Inc."),
    ("In connection with Mr. Tan's appointment as Chief Executive Officer, Ms. Holthaus and Mr. Zinsner will cease to serve as the Company's Interim Co-Chief Executive Officers.", "INTEL CORP"),
    ("Mr. Meurice was President and Chief Executive Officer of ASML Holding N.V. from 2004 until his retirement in 2013.", "INTEL CORP"),
])
def test_not_a_company_ceo_departure(text, name):
    assert red_flags.leadership_departures(text, name) == []


@pytest.mark.parametrize("text,name,want", [
    ("Calhoun decided to step down as President and Chief Executive Officer at the end of 2024.", "BOEING CO", ("CEO", "resignation or exit")),
    ("Theodore Colbert III ceased to serve as President and Chief Executive Officer of The Boeing Company, effective today.", "BOEING CO", ("CEO", "resignation or exit")),
    ("On October 14, 2026, the Board appointed Mark Long as Chief Financial Officer of the Company, effective immediately, at which time David Weigand ceased serving in that role.", "Super Micro Computer, Inc.", ("CFO", "resignation or exit")),
    ("Mr. Bonfield will continue to serve as Chief Financial Officer until May 1, 2026, at which point he will remain an employee through his retirement from the Company on October 1, 2026.", "CATERPILLAR INC", ("CFO", "retirement")),
])
def test_company_ceo_or_cfo_departure(text, name, want):
    assert [(r, k) for r, k, _ in red_flags.leadership_departures(text, name)] == [want]


def test_one_flag_per_role_and_retirement_wins():
    text = ("John Donahoe will retire as the Company's President and CEO. Under the letter agreement, he will continue to serve "
            "as President and CEO until the Effective Date, and he will resign from the Board.")
    assert [(r, k) for r, k, _ in red_flags.leadership_departures(text, "NIKE, Inc.")] == [("CEO", "retirement")]


def test_voluntary_exchange_transfer_is_not_a_delisting_flag():
    moving = ("Item 3.01 Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard; Transfer of Listing. "
              "On August 26, 2026, the Company notified the NYSE of its intention to transfer the listing of its common stock to Nasdaq.")
    failing = ("Item 3.01 Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard. On May 9, 2024, the Company "
               "received a notice from Nasdaq stating that it is not in compliance with Listing Rule 5250(c)(1).")
    texts = {"m": moving, "f": failing}
    flags = red_flags.flags_from_filings(CIK, [filing("8-K", "3.01", "m"), filing("8-K", "3.01", "f")],
                                         read=lambda cik, f: texts[f["accession"]])
    assert [f["flag"] for f in flags] == ["Delisting notice"]
    assert flags[0]["quote"].startswith("On May 9, 2024")
