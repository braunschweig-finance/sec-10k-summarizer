"""
Offline tests for earnings release tone and ask a filing. SEC and the AI are faked, so these check the plumbing
(finding the releases, cutting the text, choosing passages, quote checking, caching, the rate limit).
Run from api/:  python -m pytest tests
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

import ai_client
import ai_routes
import ask_filing
import earnings_tone as et
import filing_text
import main


def test_html_text_keeps_rows_and_drops_hidden_facts():
    html = ("<html><ix:header><ix:hidden>dei:Junk 123</ix:hidden></ix:header><p>Sales rose&nbsp;10%.</p>"
            "<table><tr><td>2027</td><td>$</td><td>1,500</td></tr><tr><td>2028</td><td>2,250</td></tr></table></html>")
    assert filing_text.html_text(html) == "Sales rose 10%.\n2027 $ 1,500\n2028 2,250"


def test_documents_reads_the_index_table(monkeypatch):
    page = b"""<table class="tableFile"><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr>
    <tr><td>1</td><td>8-K</td><td><a href="/ix?doc=/Archives/edgar/data/18230/000001823025000010/cat-20251030.htm">cat-20251030.htm</a></td><td>8-K</td><td>50</td></tr>
    <tr><td>2</td><td>PRESS RELEASE</td><td><a href="/Archives/edgar/data/18230/000001823025000010/ex991.htm">ex991.htm</a></td><td>EX-99.1</td><td>90</td></tr></table>"""
    monkeypatch.setattr(filing_text.sec_core, "sec_fetch", lambda url: page)
    docs = filing_text.documents(18230, "0000018230-25-000010")
    assert docs == [("8-K", "https://www.sec.gov/Archives/edgar/data/18230/000001823025000010/cat-20251030.htm"),
                    ("EX-99.1", "https://www.sec.gov/Archives/edgar/data/18230/000001823025000010/ex991.htm")]
    monkeypatch.setattr(et.filing_text, "documents", lambda cik, accn: docs)
    assert et.press_release_url({"cik": 18230, "accession": "x"}).endswith("ex991.htm")


def test_earnings_filings_picks_last_quarter():
    subs = [
        {"form": "8-K", "items": "2.02,9.01", "filed": "2026-10-28"},
        {"form": "8-K", "items": "5.02", "filed": "2026-09-01"},
        {"form": "8-K", "items": "2.02", "filed": "2026-09-20"},   # too close: a correction, not last quarter
        {"form": "8-K/A", "items": "2.02", "filed": "2026-08-01"},
        {"form": "8-K", "items": "2.02,7.01,9.01", "filed": "2026-07-29"},
    ]
    latest, prior = et.earnings_filings(subs)
    assert (latest["filed"], prior["filed"]) == ("2026-10-28", "2026-07-29")
    assert et.earnings_filings([{"form": "10-K", "items": "", "filed": "2026-02-01"}]) == (None, None)


RELEASE = """Caterpillar Reports Third-Quarter 2026 Results
Third-quarter sales and revenues were $17.6 billion, up 9% compared with the third quarter of 2025, on strong demand.
2026 2025 Change
Sales 17,600 16,100 9 %
We now expect full-year adjusted profit per share between $19.00 and $20.00, up from $18.00 to $19.00 previously.
This release contains forward-looking statements that may differ materially from actual results and outcomes.
Caterpillar will hold a conference call with securities analysts at 8:30 a.m. Central Time today."""


def test_narrative_drops_tables_and_boilerplate():
    n = et.narrative(RELEASE)
    assert "strong demand" in n and "full-year adjusted profit" in n
    assert "17,600" not in n and "forward-looking" not in n and "conference call" not in n
    # The guidance paragraph survives a tight limit, ahead of the other paragraphs
    assert et.narrative(RELEASE, limit=130).startswith("We now expect")


def test_word_check_counts():
    w = et.word_check("Strong demand and record margins. Some headwinds remain.")
    assert w["words"] == 8 and w["confident_per_1000"] == 250.0 and w["cautious_per_1000"] == 125.0


def tone_reply(prior_quote):
    return json.dumps({
        "overall": "More confident", "summary": "Better.",
        "guidance": {"change": "raised", "detail": "EPS $19-20, from $18-19.",
                     "latest_quote": "We now expect full-year adjusted profit per share between $19.00 and $20.00",
                     "prior_quote": ""},
        "shifts": [{"topic": "demand", "direction": "more confident",
                    "latest_quote": "Third-quarter sales and revenues were $17.6 billion, up 9%",
                    "prior_quote": prior_quote, "why": "Stronger wording."},
                   {"topic": "costs", "direction": "sideways", "latest_quote": "Costs fell sharply across every segment",
                    "prior_quote": "", "why": "Made up."}]})


def test_compare_checks_each_quote_against_its_own_release(monkeypatch):
    prior_text = "Second-quarter sales and revenues were $16.6 billion, down 4%, as demand softened in Europe."
    rel = {"name": "CATERPILLAR INC",
           "latest": {"filed": "2026-10-28", "text": RELEASE, "narrative": et.narrative(RELEASE)},
           "prior": {"filed": "2026-07-29", "text": prior_text, "narrative": prior_text}}
    reply = tone_reply("Second-quarter sales and revenues were $16.6 billion, down 4%")
    monkeypatch.setattr(ai_client, "chat", lambda *a, **k: {"text": f"```json\n{reply}\n```", "model": "m", "provider": "gemini", "seconds": 1})
    out = et.compare(rel)
    assert out["overall"] == "more confident" and out["guidance"]["change"] == "raised"
    assert out["guidance"]["verified"] and out["guidance"]["prior_verified"] is None
    demand, costs = out["shifts"]
    assert demand["verified"] and demand["prior_verified"]
    assert not costs["verified"] and costs["direction"] == "about the same"

    # A prior quote taken from the latest release (wrong release) fails the check
    reply = tone_reply("Third-quarter sales and revenues were $17.6 billion, up 9%")
    assert not et.compare(rel)["shifts"][0]["verified"]


TENK = "\n".join(
    ["TABLE OF CONTENTS Item 1 Business Item 7 Debt maturities Item 8 Employees"] +
    [f"Filler paragraph {i} about operations, products and markets around the world." for i in range(200)] +
    ["As of December 31, 2026, we had approximately 112,900 full-time employees.",
     "Long-term debt maturities for the next five years are as follows:",
     "2027 $ 1,500", "2028 2,250", "2029 900"] +
    [f"More filler {i} on accounting policies and estimates." for i in range(200)])


def test_excerpts_find_the_right_passages():
    found = " ".join(ask_filing.excerpts(TENK, "How much debt is due next year?", 2026, limit=1500))
    assert "2027 $ 1,500" in found
    assert "TABLE OF CONTENTS" not in found
    assert "112,900" in " ".join(ask_filing.excerpts(TENK, "How many employees do they have?", 2026, limit=1500))
    assert "2027" in ask_filing.query_terms("What is due next year?", 2026)


def fake_doc():
    return {"ticker": "CAT", "name": "CATERPILLAR INC", "accession": "0000018230-27-000008",
            "url": "https://www.sec.gov/x.htm", "filed": "2027-02-14", "period": "2026-12-31", "text": TENK}


def test_answer_verifies_the_quote(monkeypatch):
    replies = iter([
        '{"found": true, "answer": "$1,500 million is due in 2027.", "quote": "Long-term debt maturities for the next five years are as follows: 2027 $ 1,500"}',
        '{"found": "true", "answer": "$5 billion.", "quote": "We have $5 billion of debt due in 2027 under our notes."}',
    ])
    monkeypatch.setattr(ai_client, "chat", lambda *a, **k: {"text": next(replies), "model": "m", "provider": "gemini"})
    good = ask_filing.answer(fake_doc(), "How much debt is due next year?")
    assert good["found"] and good["verified"]
    made_up = ask_filing.answer(fake_doc(), "How much debt is due next year?")
    assert made_up["found"] and not made_up["verified"]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(ai_routes, "_answers", ai_routes.Cache(10))
    monkeypatch.setattr(ai_routes, "_tenks", ai_routes.Cache(4))
    monkeypatch.setattr(ai_routes, "_calls", ai_routes.deque())
    monkeypatch.setattr(ai_routes, "sec_read", lambda step, fn, t: fake_doc())
    monkeypatch.setattr(ai_client, "describe", lambda: {"provider": "gemini", "model": None})
    return TestClient(main.app)


def test_ask_route_caches_and_limits(client, monkeypatch):
    calls = []

    def chat(*a, **k):
        calls.append(1)
        return {"text": '{"found": true, "answer": "About 112,900.", "quote": "we had approximately 112,900 full-time employees"}',
                "model": "m", "provider": "gemini"}

    monkeypatch.setattr(ai_client, "chat", chat)
    r = client.post("/api/ask", json={"ticker": "cat", "question": "How many employees?"})
    assert r.status_code == 200 and r.json()["verified"] and not r.json()["cached"]
    r = client.post("/api/ask", json={"ticker": "CAT", "question": "how many  employees"})
    assert r.json()["cached"] and len(calls) == 1

    assert client.post("/api/ask", json={"ticker": "CAT", "question": "hi"}).status_code == 400
    monkeypatch.setattr(ai_routes, "AI_CALLS_PER_MINUTE", 1)
    r = client.post("/api/ask", json={"ticker": "CAT", "question": "What are the risks?"})
    assert r.status_code == 429


def test_ask_route_reports_a_busy_ai(client, monkeypatch):
    def chat(*a, **k):
        raise ai_client.AIError("busy", busy=True)

    monkeypatch.setattr(ai_client, "chat", chat)
    assert client.post("/api/ask", json={"ticker": "CAT", "question": "How much debt is due?"}).status_code == 429


def test_tone_route_with_one_release(client, monkeypatch):
    monkeypatch.setattr(ai_routes, "_releases", ai_routes.Cache(4))
    rel = {"ticker": "NEWCO", "name": "NEWCO", "prior": None,
           "latest": {"accession": "a", "filed": "2026-10-01", "period": "", "url": "u", "filing_url": "f",
                      "text": "t", "narrative": "t", "word_check": {}}}
    monkeypatch.setattr(ai_routes, "sec_read", lambda step, fn, t: rel)
    body = client.get("/api/earnings-tone/NEWCO").json()
    assert body["available"] is False and body["latest"]["url"] == "u" and "text" not in body["latest"]
