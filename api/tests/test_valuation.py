"""
Offline tests for the fair value estimate (valuation.py) and the split handling of share prices (prices.py).
Companies are small made-up 10-K inputs, so every expected value can be checked by hand.
Run from api/:  python -m pytest tests
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import prices
import valuation


def hit(v):
    return {"value": v, "concept": "us-gaap:X", "accn": "0000000000-25-000001", "url": ""} if v is not None else None


def fund(ticker, sic="3560", revenue=1000e6, ebit=200e6, ni=150e6, da=50e6, shares=100e6, debt=300e6, cash=100e6,
         equity=800e6, assets=2000e6, liabilities=1200e6, prior_revenue=900e6, cik=None, filed="2026-02-15"):
    def year(fy_end, rev, filed_on):
        vals = {"Revenue": rev, "Operating Income": ebit, "Net Income": ni, "Depreciation & Amortization": da,
                "Diluted Shares": shares, "Diluted EPS": ni / shares if ni and shares else None, "Total Assets": assets,
                "Total Liabilities": liabilities, "Shareholders' Equity": equity, "Cash": cash, "Long-term Debt (total)": debt}
        return {"fy_end": fy_end, "fiscal_year": int(fy_end[:4]), "filed": filed_on, "values": {k: hit(v) for k, v in vals.items()}}
    return {"ticker": ticker, "name": ticker + " Inc.", "cik": cik or ticker, "sic": sic, "industry": "",
            "years": [year("2024-12-31", prior_revenue, "2025-02-15"), year("2025-12-31", revenue, filed)]}


def test_row_market_value_multiples_and_features():
    r = valuation.build_row(fund("AAA"), 20.0, date(2026, 6, 30))
    # Market cap 20 x 100M = 2,000M; EV = 2,000 + 300 debt - 100 cash = 2,200M
    assert r["market_cap"] == pytest.approx(2000e6) and r["ev"] == pytest.approx(2200e6)
    m = r["multiples"]
    assert m["EV/EBITDA"] == pytest.approx(2200 / 250)   # 8.8x
    assert m["EV/EBIT"] == pytest.approx(2200 / 200)     # 11.0x
    assert m["EV/Sales"] == pytest.approx(2.2)
    assert m["P/E"] == pytest.approx(2000 / 150)         # 13.33x
    assert m["P/B"] == pytest.approx(2.5)
    f = r["features"]
    assert f["growth"] == pytest.approx(1000 / 900 - 1) and f["margin"] == pytest.approx(0.2) and f["leverage"] == pytest.approx(0.6)
    assert r["sector"] == "Industrials" and r["sane"]


def test_debt_rules():
    y = {"values": {"Long-term Debt (noncurrent)": hit(500), "Debt (current)": hit(80), "Short-term Borrowings": hit(30),
                    "Cash": hit(40), "Short-term Investments": hit(10)}}
    # DebtCurrent already includes short-term borrowings, so they are not added again
    debt, cash, parts = valuation.debt_and_cash(y)
    assert (debt, cash) == (580, 50)
    y = {"values": {"Long-term Debt (noncurrent)": hit(500), "Long-term Debt (current)": hit(40), "Commercial Paper": hit(20)}}
    assert valuation.debt_and_cash(y)[0] == 560


def test_fair_value_from_identical_peers_equals_their_price():
    # Two identical houses: peers with the same numbers trading at $20 value the company at $20, whatever its own price
    universe = [valuation.build_row(fund(t), 20.0, date(2026, 6, 30)) for t in ("P1", "P2", "P3", "P4")]
    target = valuation.build_row(fund("AAA"), 10.0, date(2026, 6, 30))
    est = valuation.value(target, universe)
    assert est["available"] and [m["method"] for m in est["methods"] if m["used"]] == ["EV/EBITDA", "EV/EBIT", "EV/Sales", "P/E"]
    assert est["fair_value"] == pytest.approx(20.0) and est["low"] == pytest.approx(20.0) and est["high"] == pytest.approx(20.0)
    assert est["upside_pct"] == pytest.approx(100.0) and est["verdict"] == "undervalued"


def test_fair_value_by_hand():
    # Peers at $16, $20, $24 with AAA's numbers: EV/EBIT = (P x 100 + 200) / 200 -> 9, 11, 13; median 11, p25 10, p75 12.
    universe = [valuation.build_row(fund(t), p, date(2026, 6, 30)) for t, p in (("P1", 16.0), ("P2", 20.0), ("P3", 24.0))]
    target = valuation.build_row(fund("AAA"), 25.0, date(2026, 6, 30))
    est = valuation.value(target, universe)
    ebit = next(m for m in est["methods"] if m["method"] == "EV/EBIT")
    assert (ebit["peer_median"], ebit["peer_p25"], ebit["peer_p75"]) == pytest.approx((11.0, 10.0, 12.0))
    # Value per share = (11 x 200M - 300M debt + 100M cash) / 100M shares = $20; range $18-$22
    assert (ebit["value"], ebit["low"], ebit["high"]) == pytest.approx((20.0, 18.0, 22.0))
    # Every method agrees here because the peers share AAA's numbers, so the estimate is $20 in an $18-$22 range
    assert est["fair_value"] == pytest.approx(20.0) and (est["low"], est["high"]) == pytest.approx((18.0, 22.0))
    assert est["verdict"] == "overvalued"


def test_peer_choice_prefers_similar_companies_and_same_industry():
    near = fund("NEAR", revenue=1100e6, prior_revenue=1000e6)
    far = fund("FAR", revenue=90000e6, ebit=-5000e6, prior_revenue=50000e6, liabilities=1900e6)
    other_industry = fund("OTHER", sic="3711")  # same numbers, different SIC: Consumer Discretionary, not a candidate
    same_sector_diff_sic = fund("SIBLING", sic="3590")
    rows = [valuation.build_row(f, 20.0, date(2026, 6, 30)) for f in (near, far, other_industry, same_sector_diff_sic)]
    target = valuation.build_row(fund("AAA"), 20.0, date(2026, 6, 30))
    chosen = [r["ticker"] for _, r in valuation.choose_peers(target, rows, k=3)]
    assert chosen[0] == "SIBLING" or chosen[0] == "NEAR"
    assert "OTHER" not in chosen and chosen[-1] == "FAR"


def test_same_company_other_share_class_is_not_a_peer():
    rows = [valuation.build_row(fund("GOOG", cik="1652044"), 20.0, date(2026, 6, 30))]
    target = valuation.build_row(fund("GOOGL", cik="1652044"), 20.0, date(2026, 6, 30))
    assert valuation.choose_peers(target, rows) == []


def test_financials_use_pe_and_pb():
    universe = [valuation.build_row(fund(t, sic="6022"), 20.0, date(2026, 6, 30)) for t in ("B1", "B2", "B3")]
    target = valuation.build_row(fund("BANK", sic="6022"), 20.0, date(2026, 6, 30))
    est = valuation.value(target, universe)
    assert [m["method"] for m in est["methods"]] == ["P/E", "P/B"] and est["verdict"] == "fairly valued"


def test_back_test_uses_only_filings_public_at_the_time():
    f = fund("AAA", filed="2026-08-01")  # FY2025 10-K filed after June 30, 2026
    y, _ = valuation.pick_years(f, as_of=date(2026, 6, 30))
    assert y["fy_end"] == "2024-12-31"
    assert valuation.pick_years(f, as_of=date(2027, 3, 31))[0]["fy_end"] == "2025-12-31"
    # Too old: the latest public 10-K ended more than 550 days earlier
    assert valuation.pick_years(f, as_of=date(2028, 12, 31)) == (None, None)


def test_mismatched_share_class_is_flagged():
    # Market value 0.01 x sales (like Berkshire Class B priced on Class A-equivalent shares)
    r = valuation.build_row(fund("BRK-B", shares=1e6, ni=150e6), 10.0, date(2026, 6, 30))
    assert not r["sane"]


def test_raw_close_undoes_later_splits():
    h = {"days": [date(2024, 6, 7), date(2024, 6, 10)], "close": [120.0, 121.0], "adjclose": [119.0, 120.0],
         "splits": [(date(2024, 6, 10), 10.0)]}
    assert prices.raw_close(h, 0) == pytest.approx(1200.0)   # traded at $1,200 before a 10-for-1 split
    assert prices.raw_close(h, 1) == pytest.approx(121.0)
    assert prices.on_or_before(h, date(2024, 6, 9)) == 0 and prices.on_or_before(h, date(2024, 6, 1)) is None


def test_spearman_and_quintiles():
    assert valuation.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert valuation.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    items = [{"ticker": str(i), "sector": "X", "gap": i / 10, "verdict": "undervalued" if i > 7 else "overvalued" if i < 3 else "fairly valued",
              "ret": i / 100} for i in range(10)]
    s = valuation.summarize_cohort(date(2020, 6, 30), items)
    assert s["quintile_returns"][0] == pytest.approx(0.085) and s["quintile_returns"][4] == pytest.approx(0.005)
    assert s["spread"] == pytest.approx(0.08) and s["rank_correlation"] == pytest.approx(1.0)
    assert s["verdicts"]["undervalued"]["count"] == 2


def test_value_as_first_reported_across_tags():
    import sec_core
    row = lambda val, filed: {"val": val, "start": "2016-01-01", "end": "2016-12-31", "accn": filed, "filed": filed, "form": "10-K"}
    # The newer revenue tag shows FY2016 only as a comparative in the 2019 10-K; the old tag was public in 2017
    gaap = {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [row(105, "2019-02-26")]}},
            "SalesRevenueNet": {"units": {"USD": [row(100, "2017-02-20"), row(101, "2018-02-20")]}}}
    val, tag, _, filed = sec_core.tenk_flow(gaap, ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"], "2016-12-31")
    assert (val, tag, filed) == (100, "SalesRevenueNet", "2017-02-20")


def test_wide_peer_range_is_low_confidence_and_convertibles_count_as_debt():
    universe = [valuation.build_row(fund(t), p, date(2026, 6, 30)) for t, p in (("P1", 5.0), ("P2", 20.0), ("P3", 60.0))]
    est = valuation.value(valuation.build_row(fund("AAA"), 20.0, date(2026, 6, 30)), universe)
    assert est["high"] > 3 * est["low"] and est["confidence"] == "low"
    y = {"values": {"Convertible Debt": hit(400), "Cash": hit(50)}}
    assert valuation.debt_and_cash(y)[:2] == (400, 50)
    y = {"values": {"Long-term Debt (total)": hit(900), "Convertible Debt": hit(400)}}   # already inside the total
    assert valuation.debt_and_cash(y)[0] == 900
