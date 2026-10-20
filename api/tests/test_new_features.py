"""
Offline tests for the governance numbers, risk factor summary, year-end prices, sector medians and error messages.
Inputs are small hand-made texts, HTML and price data, so every expected value can be checked by hand.
Run from api/:  python -m pytest tests
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import benchmarks
import governance_metrics as gm
import prices
import risk_factors
import sec_core


# ---------- Governance numbers ----------

PROXY = (
    "Board Composition. Our Board has determined that 11 of our 12 director nominees are independent under NYSE rules. "
    "Pay Ratio. For 2025, the ratio of the annual total compensation of our CEO to the median of the annual total "
    "compensation of all employees other than our CEO was 389 to 1. "
    "Shareholder Engagement. At our 2025 Annual Meeting, approximately 93.6% of the votes cast were in favor of our say-on-pay proposal. "
    "Our 2023 revenue grew 12 to 1 analysts' surprise."
)


def test_governance_numbers_with_evidence():
    m = gm.extract(PROXY)
    assert m["CEO Pay Ratio"]["value"] == 389 and "median" in m["CEO Pay Ratio"]["evidence"]
    b = m["Board Independence"]
    assert (b["independent"], b["total"]) == (11, 12) and b["pct"] == pytest.approx(11 / 12 * 100)   # 91.67%
    s = m["Say-on-Pay Support"]
    assert s["pct"] == 93.6 and s["approximate"] and s["meeting_year"] == 2025


def test_governance_number_words_and_colon_ratio():
    m = gm.extract("Eleven of the thirteen directors have been determined by the Board to be independent. "
                   "Our 2024 pay ratio, based on the median employee, was 1,047:1.")
    assert m["CEO Pay Ratio"]["value"] == 1047
    assert (m["Board Independence"]["independent"], m["Board Independence"]["total"]) == (11, 13)
    assert m["Say-on-Pay Support"] is None


def test_governance_numbers_not_guessed():
    # A ratio with no "median" nearby, a percentage that isn't a vote: nothing is taken
    m = gm.extract("Our debt to equity ratio was 2 to 1. Revenue rose 94% in 2024. We value independent thinking.")
    assert m == {"CEO Pay Ratio": None, "Board Independence": None, "Say-on-Pay Support": None}


# Sentences from real 2026 proxies that the first live check got wrong or right, kept as regression tests
REAL = [
    # Pfizer: the 10-year average must not win over the 2025 vote
    ("After strong executive compensation program support averaging 93.5% from 2015 through 2024, in 2025, our Say-on-Pay "
     "vote received 54.7% support, lower than historical levels.", "Say-on-Pay Support", 54.7),
    # Caterpillar: a small table of votes by year; the latest year's number
    ("SAY ON PAY SUPPORT 2025 94% 2024 93% 2023 93% The CHRC conducts an ongoing review.", "Say-on-Pay Support", 94.0),
    ("Last year, the Company's say-on-pay proposal received support from approximately 92% of the votes cast.", "Say-on-Pay Support", 92.0),
    # Citigroup: "pages 17 to 19" is not a ratio; the ratio sits in the next sentence
    ("For 2025, the median annual total compensation of all employees was $73,145, and the annual total compensation of our CEO "
     "was $95,774,814, excluding the Special Award described on pages 17 to 19. The ratio of these amounts was 1,309 to 1.", "CEO Pay Ratio", 1309),
    ("Therefore, our Fiscal 2026 CEO to median employee pay ratio was 129:1.", "CEO Pay Ratio", 129),
    # Dick's: no verb before "independent"; the committees' 100% must not count as the board's
    ("Board Refreshment and Independence § 10 of 12 directors independent (1) § All committees are 100% independent", "Board Independence", 10 / 12 * 100),
    ("Of our 12 director nominees, 11 are independent.", "Board Independence", 11 / 12 * 100),
    # NVIDIA: independent count plus the non-independent ones
    ("Our nominees include 9 independent directors, as defined by the rules and regulations of Nasdaq, and one NVIDIA officer: "
     "Mr. Huang.", "Board Independence", 90.0),
]


def test_votes_quoted_around_the_number_and_floors_skipped():
    # Uber: "85% or higher for each of the past five years" is a floor across years, not last year's vote
    assert gm.say_on_pay("Since our Say-on-Pay vote in May 2020, we have obtained positive Say-on-Pay results of approximately "
                         "85% or higher for each of the past five years.") is None
    long = "Topics we discussed include strategy and pay. " + "Board oversight of many matters, " * 40 + \
        "and at our 2025 annual meeting our say-on-pay vote received 91% support."
    got = gm.say_on_pay(long.replace(". ", ", "))
    assert got["pct"] == 91.0 and "91%" in got["evidence"] and got["evidence"].startswith("…")


def test_abbreviations_do_not_split_sentences():
    got = gm.board_independence("All director nominees are independent, except Mr. Decker, our Chair and CEO.")
    assert got["except"] == "Mr. Decker"
    cases = {
        "The Board has determined that all of our current Directors (other than Dr. Albert Bourla) are independent.": "Dr. Albert Bourla",
        "Nearly All Directors Are Independent All of our director nominees are independent, with the exception of our CEO.": "our CEO",
        "With the exception of Mr. Decker, our Chair, President and CEO, each director was independent throughout Fiscal 2025.": "Mr. Decker",
    }
    for text, name in cases.items():
        assert gm.board_independence(text)["except"] == name, text


@pytest.mark.parametrize("text,metric,expected", REAL)
def test_real_proxy_sentences(text, metric, expected):
    got = gm.extract(text)[metric]
    value = got.get("value", got.get("pct"))
    assert value == pytest.approx(expected)


def test_pay_mix_percentages_are_not_votes():
    # Citigroup's pay mix table sits next to its say-on-pay discussion
    assert gm.say_on_pay("Performance Share Units CEO: 50% Other NEOs: 30% of total incentive. Say on pay vote.") is None
    assert gm.board_independence("All of our director nominees other than Tim Cook are independent.")["except"] == "Tim Cook"


# ---------- Risk factors ----------

def tenk(risks, categories=True, toc=True):
    """A small 10-K: a table of contents that also says Item 1A, then Item 1A with bold categories and italic headings."""
    parts = ["<html><body>"]
    if toc:
        parts.append("<table><tr><td>Item 1A.</td><td>Risk Factors</td><td>12</td></tr><tr><td>Item 1B.</td><td>Unresolved</td></tr></table>")
    parts.append('<div><span style="font-weight:700">Item&#160;1A. Risk Factors</span></div><p>Investing involves risk.</p>')
    for cat, items in risks:
        if categories:
            parts.append(f'<p><b>{cat}</b></p>')
        for h in items:
            parts.append(f'<p><span style="font-style:italic;font-weight:bold">{h}</span></p><p>{"Body text. " * 30}</p>')
    parts.append('<div><span style="font-weight:700">Item 1B. Unresolved Staff Comments</span></div><p>None.</p></body></html>')
    return "".join(parts)


THIS_YEAR = [
    ("Risks Related to Our Business", [
        "Demand for our products is cyclical and could decline sharply in a global economic downturn.",
        "We depend on a limited number of suppliers for key components, and a disruption could hurt production.",
        "Changes in trade policy, including new tariffs on imported steel, could raise our costs significantly.",
    ]),
    ("Legal and Regulatory Risks", [
        "We are subject to complex laws in many countries, and violations could result in large fines.",
        "New rules on artificial intelligence could increase our compliance costs and limit product features.",
    ]),
]
LAST_YEAR = [
    ("Risks Related to Our Business", [
        "Demand for our products is cyclical and could decline sharply in a global economic downturn.",
        "We depend on a small number of suppliers for important components, and a disruption could hurt production.",
        "Changes in trade policy, including tariffs, could raise our costs.",
    ]),
    ("Legal and Regulatory Risks", [
        "We are subject to complex laws in many countries, and violations could result in large fines.",
        "The phase-out of LIBOR could affect our financing arrangements and interest costs.",
    ]),
]


def test_item_1a_skips_table_of_contents_and_reads_headings():
    frag = risk_factors.item_1a_html(tenk(THIS_YEAR))
    assert "Item 1B. Unresolved" not in frag and "Investing involves risk" in frag
    h = risk_factors.headings(frag)
    assert h["categories"] == ["Risks Related to Our Business", "Legal and Regulatory Risks"]
    assert [r["title"] for r in h["risks"]] == THIS_YEAR[0][1] + THIS_YEAR[1][1]
    assert h["risks"][3]["category"] == "Legal and Regulatory Risks"


def test_cross_reference_in_mdna_is_not_item_1a():
    # MD&A says "see Item 1A. Risk Factors" inside a sentence and runs on to Item 8: that stretch must not be chosen
    html = tenk(THIS_YEAR) .replace("</body></html>", "") + (
        '<div><b>Item 7. Management\'s Discussion</b></div><p>Results depend on many things; see <i>Item 1A. Risk Factors</i> above.</p>'
        + '<p><b>Comparison of the Years Ended December 31, 2025 and 2024</b></p>' + "<p>Revenue rose.</p>" * 400
        + '<div><b>Item 8. Financial Statements</b></div></body></html>')
    h = risk_factors.headings(risk_factors.item_1a_html(html))
    assert [r["title"] for r in h["risks"]] == THIS_YEAR[0][1] + THIS_YEAR[1][1]


def test_run_in_headings():
    html = ('<p><b>Item 1A. Risk Factors</b></p>' + "".join(
        f'<p><b>{h}</b> {"Plain explanation follows here. " * 10}</p>' for h in THIS_YEAR[0][1]) + '<p><b>Item 2. Properties</b></p>')
    h = risk_factors.headings(risk_factors.item_1a_html(html))
    assert [r["title"] for r in h["risks"]] == THIS_YEAR[0][1]


def test_toc_link_finds_item_1a_when_heading_sits_in_a_table():
    # Microsoft: the real "Item 1A" heading is in a table cell, so only the table of contents links say where it is
    body = "".join(f'<p><b>{h}</b></p><p>{"Body text. " * 30}</p>' for h in THIS_YEAR[0][1] + THIS_YEAR[1][1])
    html = ('<table><tr><td>Item 1A.</td><td><a href="#risk">Risk Factors</a></td></tr>'
            '<tr><td>Item 1B.</td><td><a href="#unres">Unresolved Staff Comments</a></td></tr></table>'
            '<table><tr><td><span id="risk">ITEM 1A. RISK FACTORS</span></td></tr></table>' + body +
            '<table><tr><td><span id="unres">ITEM 1B. UNRESOLVED STAFF COMMENTS</span></td></tr></table><p>None.</p>')
    h = risk_factors.headings(risk_factors.item_1a_html(html))
    assert [r["title"] for r in h["risks"]] == THIS_YEAR[0][1] + THIS_YEAR[1][1]


def test_short_topic_headings_and_bullets():
    # Pfizer titles each risk with a short topic; Lilly put a bullet before each heading one year
    topics = ["MANAGED CARE TRENDS", "PRICING PRESSURE", "COMPETITIVE PRODUCTS", "PATENT PROTECTION", "GLOBAL OPERATIONS", "CYBERSECURITY"]
    html = "<p><b>Item 1A. Risk Factors</b></p><p><b>Risks Related to Our Business</b></p>" + "".join(
        f'<p><b>{t}</b></p><p>{"Body text. " * 30}</p>' for t in topics) + "<p><b>Item 1B. Unresolved</b></p>"
    h = risk_factors.headings(risk_factors.item_1a_html(html))
    assert [r["title"] for r in h["risks"]] == topics and h["categories"] == ["Risks Related to Our Business"]
    assert risk_factors._clean("\u2022We face intense competition.") == "We face intense competition."


def test_compare_marks_new_reworded_unchanged_removed():
    cur = risk_factors.headings(risk_factors.item_1a_html(tenk(THIS_YEAR)))["risks"]
    old = risk_factors.headings(risk_factors.item_1a_html(tenk(LAST_YEAR)))["risks"]
    status, removed = risk_factors.compare(cur, old)
    # The tariff heading gained detail but kept its wording (78% similar): reworded. The AI rule is new; LIBOR was dropped.
    assert [s for s, _, _ in status] == ["unchanged", "reworded", "reworded", "unchanged", "new"]
    assert status[1][1] == 1 and status[2][1] == 2                               # matched to last year's 2nd and 3rd headings
    assert removed == ["The phase-out of LIBOR could affect our financing arrangements and interest costs."]


def test_risk_summary_end_to_end(monkeypatch):
    f = lambda accn, date, doc: SimpleNamespace(form="10-K", cik=18230, accession_no=accn, primary_document=doc, filing_date=date,
                                                period_of_report=date[:4] + "-12-31", url=f"https://sec/{accn}")
    filings = [f("0000018230-26-000010", "2026-02-13", "cat-2025.htm"), f("0000018230-25-000008", "2025-02-14", "cat-2024.htm")]
    company = SimpleNamespace(name="Caterpillar Inc.", cik=18230, get_filings=lambda form, trigger_full_load=True: filings)
    monkeypatch.setattr(sec_core, "Company", lambda t: company)
    docs = {"cat-2025.htm": tenk(THIS_YEAR), "cat-2024.htm": tenk(LAST_YEAR)}
    monkeypatch.setattr(sec_core, "sec_fetch", lambda url: docs[url.rsplit("/", 1)[1]].encode())
    r = sec_core.get_risk_summary("CAT")
    assert r["available"] and r["count"] == 5 and r["prior"]["count"] == 5
    assert r["changes"] == {"new": 1, "reworded": 2, "unchanged": 2} and len(r["removed"]) == 1
    assert r["risks"][1]["prior_title"].startswith("We depend on a small number")
    assert r["tenk_url"] == "https://sec/0000018230-26-000010"


def test_no_10k_is_data_unavailable(monkeypatch):
    company = SimpleNamespace(name="TAIWAN SEMICONDUCTOR", get_filings=lambda form, trigger_full_load=True: [])
    monkeypatch.setattr(sec_core, "Company", lambda t: company)
    with pytest.raises(sec_core.DataUnavailable, match="20-F"):
        sec_core.get_risk_summary("TSM")


# ---------- Year-end prices ----------

def yahoo(days):
    """Yahoo chart JSON for {iso date: close}, timestamps at 9:30 New York time (gmtoffset -4h)."""
    from datetime import datetime, timezone
    ts = [int(datetime.fromisoformat(d + "T13:30:00").replace(tzinfo=timezone.utc).timestamp()) for d in days]
    return {"chart": {"result": [{"meta": {"gmtoffset": -14400}, "timestamp": ts,
                                  "indicators": {"quote": [{"close": list(days.values())}]}}]}}


def test_year_end_close_is_last_trading_day_on_or_before(monkeypatch):
    body = yahoo({"2024-12-30": 360.0, "2024-12-31": 362.76, "2025-01-02": 370.0, "2025-12-31": 572.87, "2026-01-02": 580.0})
    monkeypatch.setattr(prices.httpx, "get", lambda *a, **k: SimpleNamespace(raise_for_status=lambda: None, json=lambda: body))
    p = prices.year_end_closes("CAT", ["2024-12-31", "2025-12-31", "2026-01-03"])
    assert p["available"]
    assert [(y["date"], y["close"]) for y in p["years"]] == [("2024-12-31", 362.76), ("2025-12-31", 572.87), ("2026-01-02", 580.0)]


def test_prices_fail_softly(monkeypatch):
    def boom(*a, **k):
        raise OSError("blocked")
    monkeypatch.setattr(prices.httpx, "get", boom)
    p = prices.year_end_closes("CAT", ["2025-12-31"])
    assert p["available"] is False and "Yahoo" in p["reason"]


# ---------- Sector medians ----------

def test_benchmarks_by_sector_by_hand(tmp_path):
    def company(t, gp, op, rev, sic="3531"):
        d = tmp_path / t
        d.mkdir()
        inputs = {"Revenue": {"value_m": rev}, "Gross Profit": {"value_m": gp}, "Operating Income": {"value_m": op},
                  "Current Assets": {"value_m": 10}, "Current Liabilities": {"value_m": 5}, "Total Liabilities": {"value_m": 30},
                  "Shareholders' Equity": {"value_m": 10}}
        (d / "company.json").write_text(json.dumps({"ticker": t, "sic": sic, "inputs": inputs}))
        (d / "governance.json").write_text(json.dumps({"metrics": {"CEO Pay Ratio": {"value": op}, "Board Independence": None}}))
    # Five industrials (SIC 3531, construction machinery) with operating margins 10, 20, 30, 40, 50% (revenue 100)
    for i, op in enumerate([10, 20, 30, 40, 50]):
        company(f"I{i}", 40, op, 100)
    company("T0", 60, 25, 100, sic="3674")                                  # semiconductors: Information Technology
    (tmp_path / "X0").mkdir()
    (tmp_path / "X0" / "company.json").write_text(json.dumps({"__unavailable__": "no 10-K"}))
    members = {t: "" for t in ["I0", "I1", "I2", "I3", "I4", "T0", "X0", "MISSING"]}

    b = benchmarks.build(str(tmp_path), members)
    ind = b["sectors"]["Industrials"]["metrics"]
    assert ind["Operating Margin"] == {"median": 30, "p25": 20, "p75": 40, "n": 5}
    assert ind["Gross Margin"]["median"] == 40 and ind["Current Ratio"]["median"] == 2 and ind["Total Liabilities-to-Equity"]["median"] == 3
    assert ind["CEO Pay Ratio"]["median"] == 30 and ind["Board Independence"] is None     # no values: no median
    assert b["sectors"]["Information Technology"]["metrics"]["Operating Margin"] is None    # 1 company is under the minimum of 5
    assert b["all"]["metrics"]["Operating Margin"]["n"] == 6 and b["all"]["metrics"]["Operating Margin"]["median"] == 27.5

    path = tmp_path / "benchmarks.json"
    path.write_text(json.dumps(b))
    assert benchmarks.for_company("3537", str(path))["group"] == "Industrials"    # any company, in the index or not
    other = benchmarks.for_company("9995", str(path))
    assert other["group"] == "Russell 1000" and not other["is_sector"] and other["note"]
    assert benchmarks.for_company("3531", str(tmp_path / "none.json")) is None


def test_ratio_values_match_compute_ratios_rules():
    v = sec_core.ratio_values({"Revenue": {"value_m": 200}, "Gross Profit": {"value_m": 50}, "Operating Income": None,
                               "Current Assets": {"value_m": 3}, "Current Liabilities": {"value_m": 0},
                               "Total Liabilities": {"value_m": 9}, "Shareholders' Equity": {"value_m": -1}})
    assert v == {"Gross Margin": 25, "Operating Margin": None, "Current Ratio": None, "Total Liabilities-to-Equity": None}


# ---------- Error messages ----------

def test_unavailable_data_gets_a_plain_422(monkeypatch):
    from fastapi.testclient import TestClient
    import main

    def no_company(t):
        raise sec_core.DataUnavailable("SEC EDGAR has no company with the ticker ZZZZQ.")
    monkeypatch.setattr(main, "isolated", lambda fn, t: no_company(t))
    monkeypatch.setattr(main.prebuilt, "get", lambda kind, t: {"__unavailable__": "SPY doesn't file 10-K annual reports"} if t == "SPY" else None)
    for f in main.CACHES:
        f.cache_clear()
    client = TestClient(main.app)
    r = client.get("/api/company/zzzzq")
    assert r.status_code == 422 and r.json()["detail"] == "SEC data unavailable for ZZZZQ: SEC EDGAR has no company with the ticker ZZZZQ."
    r = client.get("/api/risks/SPY")
    assert r.status_code == 422 and "doesn't file 10-K" in r.json()["detail"]
