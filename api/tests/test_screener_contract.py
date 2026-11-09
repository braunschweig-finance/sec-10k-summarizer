"""Independent HTTP contract tests; synthetic on-disk caches, never live data.

Run from api/: python -m pytest tests/test_screener_contract.py -q
Missing routes deliberately fail (no skip/xfail).
"""
import importlib
import json
import math
import socket
import sys
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STAMP = "2026-10-30T12:00:00Z"
FILING = "https://www.sec.gov/Archives/edgar/data/1/000000000125000001/"
FIELDS = {"ticker", "name", "sector", "fy_end", "pay_efficiency_pct", "grade",
          "grade_score", "upside_pct", "price_date", "valuation_confidence", "sources", "missing"}


@pytest.fixture
def offline(monkeypatch, tmp_path):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("network/AI/live lookup")
        raise AssertionError("Screener attempted network/AI/live lookup")

    # Guard before importing the app. TestClient's in-process transport needs no sockets.
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    monkeypatch.setenv("PREBUILT_DIR", str(tmp_path))
    prebuilt = importlib.import_module("prebuilt")
    monkeypatch.setattr(prebuilt, "DIR", str(tmp_path))
    monkeypatch.setattr(prebuilt, "start", forbidden)
    ai = importlib.import_module("ai_client")
    monkeypatch.setattr(ai, "chat", forbidden)
    main = importlib.import_module("main")
    for name in ("cached_financials", "cached_governance", "cached_pay_efficiency",
                 "cached_fundamentals", "cached_red_flags", "cached_insiders"):
        if hasattr(main, name):
            monkeypatch.setattr(main, name, forbidden)
    # No lifespan: production startup intentionally starts a download thread.
    client = TestClient(main.app)
    yield client, tmp_path
    client.close()
    assert not attempts, "Even a caught network/AI attempt violates the contract"


def write(root, name, body):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, allow_nan=False), encoding="utf-8")


def snapshot(root):
    """Schemas from sec_core/prebuild and test_valuation, not screener internals."""
    import valuation
    peers = []
    # Four identical $20 peers; AAA at $10 has exactly 100 percentage points upside.
    for ticker, price, pay in (("AAA", 10, 1.18), ("BBB", 20, 0),
                               ("CCC", 20, 1.18), ("DDD", 20, -2),
                               ("EEE", 20, None), ("FFF", 20, None)):
        values = {"Revenue": 1000e6, "Operating Income": 200e6, "Net Income": 150e6,
                  "Depreciation & Amortization": 50e6, "Diluted Shares": 100e6,
                  "Diluted EPS": 1.5, "Long-term Debt (total)": 300e6, "Cash": 100e6,
                  "Shareholders' Equity": 800e6, "Total Assets": 2000e6, "Total Liabilities": 1200e6}
        years = [{"fy_end": f"{y}-12-31", "fiscal_year": y, "filed": f"{y+1}-02-15",
                  "values": {k: {"value": v, "concept": "us-gaap:X", "accn": "0000000001-25-000001",
                                  "url": FILING} for k, v in values.items()}} for y in (2024, 2025)]
        fund = {"ticker": ticker, "name": ticker + " Machines", "cik": ticker,
                "sic": "3560", "industry": "Machinery", "years": years}
        write(root, f"{ticker}/fundamentals.json", fund)
        write(root, f"{ticker}/company.json", {"ticker": ticker, "name": fund["name"],
              "sic": "3560", "industry": "Machinery", "tenk_url": FILING,
              "statements": {}, "ratios": {}, "inputs": {}})
        write(root, f"{ticker}/pay_efficiency.json", {"available": pay is not None,
              "pct": pay, "denominator": "operating", "fy_end": "2025-12-31",
              "proxy_url": FILING + "proxy.htm", "reason": "Synthetic missing pay"})
        if ticker != "FFF":
            peers.append(valuation.build_row(fund, price, date(2026, 10, 30), as_of=date(2026, 10, 30)))
    write(root, "manifest.json", {"built_at": STAMP, "tickers": ["FFF", "EEE", "DDD", "CCC", "BBB", "AAA"], "failures": {}})
    write(root, "valuation.json", {"built_at": STAMP, "source": valuation.SOURCE, "rows": peers, "backtest": None})


def get(client, **params):
    response = client.get("/api/screener", params=params)
    assert response.status_code == 200, f"Endpoint contract unavailable: {response.status_code} {response.text}"
    body = response.json()
    assert {"available", "built_at", "total", "matched", "limit", "offset", "sectors", "coverage", "rows", "warnings"} <= body.keys()
    for row in body["rows"]:
        assert FIELDS <= row.keys()
        assert set(row["sources"]) >= {"financials_url", "proxy_url", "valuation_source"}
        assert isinstance(row["missing"], list)
        assert row["valuation_confidence"] in (None, "normal", "low")
        for key in ("pay_efficiency_pct", "grade_score", "upside_pct"):
            assert row[key] is None or math.isfinite(row[key])
            if row[key] is None:
                assert row["missing"], f"Missing {key} needs a reason"
    return body


def tickers(body):
    return [r["ticker"] for r in body["rows"]]


@pytest.mark.parametrize("manifest", [None, "{broken", '{"__unavailable__":"failed"}'])
def test_no_usable_snapshot(offline, manifest):
    client, root = offline
    if manifest is not None:
        (root / "manifest.json").write_text(manifest, encoding="utf-8")
    body = get(client)
    assert body["available"] is False
    assert body["rows"] == [] and body["total"] == body["matched"] == 0
    assert all(v == 0 for v in body["coverage"].values())
    assert body["warnings"]


def test_metadata_pagination_and_missing_zero(offline):
    client, root = offline
    snapshot(root)
    body = get(client)
    assert body["available"] is True and body["built_at"] == STAMP
    assert (body["total"], body["matched"], body["limit"], body["offset"]) == (6, 6, 50, 0)
    assert tickers(body) == ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    rows = {r["ticker"]: r for r in body["rows"]}
    assert rows["BBB"]["pay_efficiency_pct"] == 0
    assert rows["EEE"]["pay_efficiency_pct"] is None
    assert rows["FFF"]["upside_pct"] is None
    assert rows["AAA"]["pay_efficiency_pct"] == 1.18
    assert rows["DDD"]["pay_efficiency_pct"] == -2
    assert rows["AAA"]["upside_pct"] == pytest.approx(100)
    assert rows["AAA"]["price_date"] == "2026-10-30"
    assert rows["AAA"]["sources"]["financials_url"] == FILING
    assert rows["AAA"]["sources"]["proxy_url"] == FILING + "proxy.htm"
    assert rows["AAA"]["sources"]["valuation_source"]
    assert body["sectors"] == ["Industrials"]
    assert body["coverage"] == {"pay_efficiency_pct": 4, "grade": 0, "upside_pct": 5}
    page = get(client, search="machines", limit=2, offset=2)
    assert tickers(page) == ["CCC", "DDD"] and page["matched"] == 6
    assert (page["limit"], page["offset"]) == (2, 2)
    assert page["coverage"] == body["coverage"]
    assert get(client, offset=99)["rows"] == []
    empty = get(client, search="no such company")
    assert empty["available"] is True and empty["matched"] == 0 and empty["total"] == 6
    assert empty["coverage"] == body["coverage"]


def test_percentage_point_filters(offline):
    client, root = offline
    snapshot(root)
    assert tickers(get(client, max_pay_efficiency_pct=1.18)) == ["AAA", "BBB", "CCC", "DDD"]
    assert tickers(get(client, max_pay_efficiency_pct=0)) == ["BBB", "DDD"]
    assert tickers(get(client, min_upside_pct=50)) == ["AAA"]
    assert tickers(get(client, min_upside_pct=0, max_pay_efficiency_pct=0)) == ["BBB", "DDD"]
    assert tickers(get(client, search="aAa", sector="Industrials")) == ["AAA"]
    assert get(client, sector="Unknown")["matched"] == 0


@pytest.mark.parametrize("sort", ["ticker", "name", "sector", "pay_efficiency_pct", "grade_score", "upside_pct"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sort_nulls_last_and_stable_ties(offline, sort, order):
    client, root = offline
    snapshot(root)
    rows = get(client, sort=sort, order=order)["rows"]
    present = [r for r in rows if r[sort] is not None]
    assert rows == present + [r for r in rows if r[sort] is None]
    assert [r[sort] for r in present] == sorted([r[sort] for r in present], reverse=order == "desc")
    for value in {r[sort] for r in rows}:
        tied = [r["ticker"] for r in rows if r[sort] == value]
        assert tied == sorted(tied)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"limit": "1.5"}, {"offset": -1},
    {"offset": "x"}, {"sort": "price"}, {"order": "sideways"}, {"grade": "E"}] +
    [{key: value} for key in ("max_pay_efficiency_pct", "min_upside_pct")
     for value in ("nan", "NaN", "inf", "-inf", "1e309", "abc")])
def test_invalid_queries_rejected(offline, params):
    client, root = offline
    snapshot(root)
    response = client.get("/api/screener", params=params)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("bad", ["{broken", '{"__unavailable__":"SEC data unavailable"}', "null"])
def test_bad_lookup_files_are_missing_not_zero(offline, bad):
    client, root = offline
    snapshot(root)
    (root / "AAA" / "pay_efficiency.json").write_text(bad, encoding="utf-8")
    row = get(client, search="AAA")["rows"][0]
    assert row["pay_efficiency_pct"] is None and row["missing"]
    assert get(client, search="AAA", max_pay_efficiency_pct=100)["matched"] == 0


def test_file_change_invalidates_snapshot(offline):
    client, root = offline
    snapshot(root)
    assert get(client, search="AAA")["rows"][0]["pay_efficiency_pct"] == 1.18
    write(root, "AAA/pay_efficiency.json", {"available": True, "pct": 27.125,
          "denominator": "operating", "fy_end": "2025-12-31", "proxy_url": FILING})
    assert get(client, search="AAA")["rows"][0]["pay_efficiency_pct"] == 27.125


def test_pretax_pay_is_not_operating_pay(offline):
    client, root = offline
    snapshot(root)
    write(root, "AAA/pay_efficiency.json", {"available": True, "pct": 0,
          "denominator": "pretax", "fy_end": "2025-12-31", "proxy_url": FILING})
    row = get(client, search="AAA")["rows"][0]
    assert row["pay_efficiency_pct"] is None and row["missing"]
    assert get(client, search="AAA", max_pay_efficiency_pct=100)["matched"] == 0


@pytest.mark.parametrize("bad", ["{broken", '{"__unavailable__":"failed"}', "null"])
def test_broken_valuation_does_not_break_pay_snapshot(offline, bad):
    client, root = offline
    snapshot(root)
    (root / "valuation.json").write_text(bad, encoding="utf-8")
    body = get(client)
    assert body["available"] is True and body["total"] == 6
    assert body["coverage"]["upside_pct"] == 0
    assert all(r["upside_pct"] is None and r["missing"] for r in body["rows"])
    assert body["coverage"]["pay_efficiency_pct"] == 4
