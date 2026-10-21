"""
Offline tests for the overall company grade (grade.py). Inputs are small made-up lookups, so every score can be
checked by hand. Run from api/:  python -m pytest tests
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import grade

BENCH = {"group": "Industrials", "metrics": {
    "Board Independence": {"p25": 80.0, "median": 88.0, "p75": 92.0},
    "Say-on-Pay Support": {"p25": 88.0, "median": 93.0, "p75": 96.0},
    "CEO Pay Ratio": {"p25": 150.0, "median": 250.0, "p75": 400.0},
    "Pay Efficiency": {"p25": 0.5, "median": 1.0, "p75": 2.0},
}}


def gov(ind=92.0, sop=93.0, ratio=150):
    return {"metrics": {"Board Independence": {"pct": ind}, "Say-on-Pay Support": {"pct": sop}, "CEO Pay Ratio": {"value": ratio}},
            "proxy_url": "https://www.sec.gov/x"}


PAY = {"available": True, "pct": 2.0, "denominator": "operating"}


def test_place_against_sector():
    s = BENCH["metrics"]["CEO Pay Ratio"]
    assert grade.place(250, s) == 50 and grade.place(400, s) == 75 and grade.place(150, s) == 25
    assert grade.place(325, s) == pytest.approx(62.5)            # halfway from median to p75
    assert grade.place(150, s, higher_is_better=False) == 75     # a low pay ratio is good
    assert grade.place(1000, s) == 100 and grade.place(0, s) == 0  # kept within 0-100


def test_governance_part_by_hand():
    res, why = grade.governance_part(gov(), PAY, BENCH)
    scores = {i["metric"]: i["score"] for i in res["items"]}
    # Independence 92 = p75 -> 75; say-on-pay 93 = median -> 50; pay ratio 150 = p25, lower better -> 75;
    # Pay Efficiency 2.0 = p75, lower better -> 25
    assert scores == {"Board Independence": 75, "Say-on-Pay Support": 50, "CEO Pay Ratio": 75, "Pay Efficiency": 25}
    assert res["score"] == pytest.approx(56.25) and why is None


def test_failed_say_on_pay_is_capped():
    res, _ = grade.governance_part(gov(sop=65.0), None, BENCH)
    item = next(i for i in res["items"] if i["metric"] == "Say-on-Pay Support")
    assert item["score"] == 0 and "failed vote" in item["note"]   # far below the sector; never above 20 either way
    res, _ = grade.governance_part(gov(sop=69.0), None, {"metrics": {"Say-on-Pay Support": {"p25": 60.0, "median": 65.0, "p75": 68.0}}})
    assert res["items"][0]["score"] == 20   # above its sector's p75, but still a failed vote


def test_red_flags_points():
    rf = {"flags": [{"flag": "Restatement", "severity": "high"}, {"flag": "Auditor change", "severity": "medium"},
                    {"flag": "Impairment", "severity": "low"}]}
    assert grade.red_flags_part(rf)["score"] == 100 - 35 - 12 - 4   # 49
    assert grade.red_flags_part({"flags": [{"severity": "high"}] * 3})["score"] == 0
    assert grade.red_flags_part({"flags": []})["score"] == 100


def test_insiders():
    none = {"value": 0, "count": 0}
    assert grade.insiders_part({"cluster": {"insiders": 3}, "buys": {"count": 3, "value": 1e6}}, 1e9)["score"] == 85
    assert grade.insiders_part({"buys": {"count": 1, "value": 2e6}, "sells": {"value": 1e6}}, 1e9)["score"] == 70
    # $30M sold outside plans on a $1B company = 3% -> 20; $10M = 1% -> 35; all of it planned -> 50
    assert grade.insiders_part({"buys": none, "sells": {"value": 30e6}, "planned_sells": {"value": 0}}, 1e9)["score"] == 20
    assert grade.insiders_part({"buys": none, "sells": {"value": 10e6}, "planned_sells": {"value": 0}}, 1e9)["score"] == 35
    assert grade.insiders_part({"buys": none, "sells": {"value": 30e6}, "planned_sells": {"value": 30e6}}, 1e9)["score"] == 50


def test_valuation_curve():
    v = lambda gap: grade.valuation_part({"available": True, "upside_pct": gap, "verdict": "", "fair_value": 1, "price": 1})[0]["score"]
    assert v(0) == 50 and v(30) == pytest.approx(50 + 50 * math.tanh(0.5)) and round(v(30), 1) == 73.1
    assert v(-30) == pytest.approx(100 - v(30))


def test_overall_weights_and_missing_parts():
    parts = {"governance": (gov(), PAY, BENCH), "red_flags": {"flags": []},
             "insiders": ({"buys": {"count": 0, "value": 0}, "sells": {"value": 0}}, 1e9),
             "valuation": {"available": True, "upside_pct": 0, "verdict": "fairly valued", "fair_value": 10, "price": 10}}
    g = grade.build("AAA", "AAA Inc.", parts, {})
    # (35 x 56.25 + 35 x 100 + 15 x 50 + 15 x 50) / 100 = 69.69 -> B
    assert g["score"] == pytest.approx(69.6875) and g["letter"] == "B"
    # Without value vs peers, the other weights scale up: (35 x 56.25 + 35 x 100 + 15 x 50) / 85
    del parts["valuation"]
    g = grade.build("AAA", "AAA Inc.", parts, {"valuation": "peer data not loaded"})
    assert g["score"] == pytest.approx((35 * 56.25 + 35 * 100 + 15 * 50) / 85)
    assert [m["part"] for m in g["missing"]] == ["valuation"]
    # Less than half the weight readable: no grade
    g = grade.build("AAA", "AAA Inc.", {"insiders": parts["insiders"]}, {})
    assert not g["available"]


def test_letters():
    assert [grade.letter(s) for s in (95, 80, 79.9, 65, 50, 35, 34.9)] == ["A", "A", "B", "B", "C", "D", "F"]
