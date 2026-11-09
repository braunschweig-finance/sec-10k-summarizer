"""Offline comparison contract against the real screener and FastAPI route.

No lifespan, live cache, or replacement endpoint is used. Comparison tests are
expected to fail until the separately implemented API contract is integrated.
"""
import copy
import importlib
import socket
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def snapshot(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("external access")
        raise AssertionError("Comparison tests must remain offline")

    # Windows event loops need loopback socket pairs for internal wakeups.
    def guarded(original):
        def connect(sock, address):
            if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
                return original(sock, address)
            return forbidden(sock, address)
        return connect

    monkeypatch.setattr(socket.socket, "connect", guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(socket.socket.connect_ex))
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)
    screener = importlib.import_module("screener")
    monkeypatch.setattr(importlib.import_module("prebuilt"), "start", forbidden)

    rows = []
    for ticker, sector, letter, pay, upside in (
        ("MSFT", "Technology", "B", 2, 10),
        ("CAT", "Industrials", "A", 1, 30),
        ("AAPL", "Technology", "A", 3, 20),
        ("BRK.B", "Financials", "C", None, None),
        ("BF-B", "Consumer Staples", "D", 4, -5),
    ):
        rows.append(dict(
            ticker=ticker, name=ticker + " Fixture", sector=sector,
            fy_end="2025-12-31", pay_efficiency_pct=pay, grade=letter,
            grade_score=80, upside_pct=upside, price_date="2026-10-30",
            valuation_confidence="normal" if upside is not None else None,
            sources={"financials_url": "https://www.sec.gov/fixture/" + ticker,
                     "proxy_url": None, "valuation_source": "Fixture filing"},
            missing=["sources.proxy_url: Cached source unavailable."],
        ))
    data = dict(
        available=True, built_at="2026-10-30T12:00:00Z", total=len(rows),
        rows=rows, sectors=sorted({r["sector"] for r in rows}),
        coverage={"pay_efficiency_pct": 4, "grade": 5, "upside_pct": 4},
        warnings=["Synthetic cached snapshot."],
    )
    calls = []

    def cached_snapshot():
        calls.append(None)
        return data  # Deliberately return the same mutable cache every time.

    monkeypatch.setattr(screener, "_snapshot", cached_snapshot)
    yield screener, data, calls
    assert not attempts, "Even a caught external access attempt is a failure"


@pytest.fixture(params=["screen", "route"])
def invoke(request, snapshot):
    screener, _, calls = snapshot
    client = None
    if request.param == "route":
        main = importlib.import_module("main")
        # Do not use a context manager: startup downloads are out of scope.
        client = TestClient(main.app)

    def run(**params):
        before = len(calls)
        if client is None:
            body = screener.screen(**params)
        else:
            response = client.get("/api/screener", params=params)
            assert response.status_code == 200, response.text
            body = response.json()
        assert len(calls) == before + 1, "Each request must use exactly one snapshot"
        return body

    yield run
    if client is not None:
        client.close()


def selected(data, *tickers):
    by_ticker = {row["ticker"]: row for row in data["rows"]}
    return [copy.deepcopy(by_ticker[ticker]) for ticker in tickers]


def test_default_response_and_existing_positional_call(snapshot, invoke):
    screener, data, calls = snapshot
    expected = copy.deepcopy(data)
    expected.update(matched=5, limit=50, offset=0,
                    rows=selected(data, "AAPL", "BF-B", "BRK.B", "CAT", "MSFT"))
    assert invoke() == expected
    assert "comparison" not in expected
    before = len(calls)
    assert screener.screen(None, None, None, None, None, "ticker", "asc", 50, 0) == expected
    assert len(calls) == before + 1
    assert screener.screen(compare=None) == expected


@pytest.mark.parametrize("filters,page_tickers", [
    ({"search": "CAT"}, ["CAT"]),
    ({"sector": "Technology", "grade": "A", "max_pay_efficiency_pct": 3,
      "min_upside_pct": 20}, ["AAPL"]),
    ({"sort": "ticker", "order": "desc", "limit": 1, "offset": 1}, ["CAT"]),
    ({"search": "no matching company", "offset": 99}, []),
])
def test_exact_subset_ignores_filters_and_page(snapshot, invoke, filters, page_tickers):
    _, data, _ = snapshot
    original = copy.deepcopy(data)
    baseline = invoke(**filters)
    result = invoke(compare="MSFT,BRK.B,CAT", **filters)
    assert result.pop("comparison") == {
        "tickers": ["MSFT", "BRK.B", "CAT"],
        "rows": selected(data, "MSFT", "BRK.B", "CAT"), "missing": [],
    }
    assert result == baseline  # Counts, coverage, warnings, and page all unchanged.
    assert [row["ticker"] for row in result["rows"]] == page_tickers
    assert data == original


def test_missing_tickers_are_explicit_and_ordered(snapshot, invoke):
    _, data, _ = snapshot
    result = invoke(compare="ZZZ,CAT,NOPE,AAPL")
    assert result["comparison"] == {
        "tickers": ["ZZZ", "CAT", "NOPE", "AAPL"],
        "rows": selected(data, "CAT", "AAPL"), "missing": ["ZZZ", "NOPE"],
    }
    assert invoke(compare="ZZZ")["comparison"] == {
        "tickers": ["ZZZ"], "rows": [], "missing": ["ZZZ"],
    }


def test_unavailable_snapshot_reports_all_requested_missing(snapshot, invoke):
    _, data, _ = snapshot
    data.update(available=False, total=0, rows=[], sectors=[],
                coverage={"pay_efficiency_pct": 0, "grade": 0, "upside_pct": 0},
                warnings=["Cached screener snapshot unavailable."])
    baseline = invoke()
    result = invoke(compare="CAT,AAPL")
    assert result.pop("comparison") == {
        "tickers": ["CAT", "AAPL"], "rows": [], "missing": ["CAT", "AAPL"],
    }
    assert result == baseline
    assert result["available"] is False


@pytest.mark.parametrize("raw,normalized", [
    (" cat , aapl,Cat, AAPL ,brk.b,bf-b", ["CAT", "AAPL", "BRK.B", "BF-B"]),
    ("CAT,CAT,CAT,CAT,CAT", ["CAT"]),
    ("A" * 15, ["A" * 15]),
    ("0ABC", ["0ABC"]),
    ("CAT" + " " * 125, ["CAT"]),  # Exactly 128 raw characters.
])
def test_normalization_safe_tickers_and_bounds(snapshot, invoke, raw, normalized):
    _, data, _ = snapshot
    present = {row["ticker"] for row in data["rows"]}
    assert invoke(compare=raw)["comparison"] == {
        "tickers": normalized,
        "rows": selected(data, *(t for t in normalized if t in present)),
        "missing": [t for t in normalized if t not in present],
    }


INVALID = [
    "", " ", ",", "CAT,", ",CAT", "CAT,,AAPL", "CAT, ,AAPL",
    "CAT,AAPL,MSFT,BRK.B,BF-B", "A" * 16, "CAT" + " " * 126,
    "CAT,../AAPL", "-CAT", ".CAT", "CAT/AAPL", "CAT\\AAPL", "CAT_A",
    "CAT A", "CAT;AAPL", "CAT\x00", "CÁT", "CAT,$AAPL",
]


@pytest.mark.parametrize("raw", INVALID)
def test_invalid_comparison_raises_value_error(snapshot, raw):
    screener, _, _ = snapshot
    with pytest.raises(ValueError):
        screener.screen(compare=raw)


@pytest.mark.parametrize("raw", INVALID)
def test_invalid_comparison_route_returns_422(snapshot, raw):
    main = importlib.import_module("main")
    client = TestClient(main.app)  # Never enter lifespan.
    try:
        response = client.get("/api/screener", params={"compare": raw})
        assert response.status_code == 422, response.text
        assert response.json().get("detail")
    finally:
        client.close()


def test_comparison_and_filtered_rows_deepcopy_cache(snapshot):
    screener, data, calls = snapshot
    original = copy.deepcopy(data)
    result = screener.screen(search="CAT", compare="CAT,AAPL")
    assert len(calls) == 1
    assert result["rows"] == selected(data, "CAT")
    assert result["comparison"]["rows"] == selected(data, "CAT", "AAPL")
    result["rows"][0]["sources"]["financials_url"] = "changed page source"
    result["rows"][0]["missing"].append("changed page reason")
    result["comparison"]["rows"][0]["sources"]["financials_url"] = "changed comparison source"
    result["comparison"]["rows"][1]["missing"].append("changed comparison reason")
    result["comparison"]["tickers"].append("ZZZ")
    result["comparison"]["missing"].append("NOPE")
    result["coverage"]["grade"] = -1
    result["warnings"].append("changed warning")
    result["sectors"].clear()
    assert data == original
    again = screener.screen(search="CAT", compare="CAT,AAPL")
    assert len(calls) == 2
    assert again["rows"] == selected(original, "CAT")
    assert again["comparison"] == {
        "tickers": ["CAT", "AAPL"],
        "rows": selected(original, "CAT", "AAPL"), "missing": [],
    }
