"""Test whether Pay Efficiency in year t predicts performance in year t+1.

Input:  data/pay_efficiency_data.csv (from pull_pay_efficiency.py)
Output: results/pay_efficiency_results.md, results/analysis_panel.csv

Pay Efficiency = CEO compensation actually paid / operating income (same year).
Outcomes (t+1): one-year stock return from the PvP TSR table, and change in ROA
(net income / total assets, both from the 10-K).

Run:  python analyze_pay_efficiency.py
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "pay_efficiency_data.csv"
OUT = ROOT / "results"


def build_panel(d, metric, include_pretax=False):
    d = d.copy()
    d["roa"] = d["net_income"] / d["assets"]
    d["leverage"] = d["liabilities"] / d["assets"]
    d["log_assets"] = np.log(d["assets"])
    d["sic_division"] = d["sic"].astype(str).str[0]

    nxt = d[["ticker", "fiscal_year", "tsr_1y", "roa"]].copy()
    nxt["fiscal_year"] -= 1
    d = d.merge(nxt, on=["ticker", "fiscal_year"], how="left", suffixes=("", "_next"))
    d["next_return"] = d["tsr_1y_next"]
    d["d_roa_next"] = d["roa_next"] - d["roa"]

    keep = ~d["financial_firm"] & d[metric].notna() & (d["operating_income"] > 0)
    keep &= d["denominator"].isin(["operating", "pretax"] if include_pretax else ["operating"])
    p = d[keep].copy()
    # Rank within each year, so a year when every CEO's pay jumped doesn't drive the result.
    p["pct_rank"] = p.groupby("fiscal_year")[metric].rank(pct=True)
    p["tercile"] = p.groupby("fiscal_year")[metric].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["Low", "Mid", "High"]))
    return p


def tercile_table(p, outcome):
    s = p.dropna(subset=[outcome])
    g = s.groupby("tercile", observed=True)[outcome].agg(["count", "mean", "median"])
    hi, lo = s.loc[s.tercile == "High", outcome], s.loc[s.tercile == "Low", outcome]
    t, pval = stats.ttest_ind(hi, lo, equal_var=False)
    rho, rho_p = stats.spearmanr(s["pct_rank"], s[outcome])
    return g, hi.mean() - lo.mean(), t, pval, rho, rho_p, len(s)


def regression(p, outcome):
    s = p.dropna(subset=[outcome, "log_assets", "leverage", "roa"]).copy()
    # Clip extreme outcomes at the 1st/99th percentile so a few firms can't dominate.
    lo, hi = s[outcome].quantile([0.01, 0.99])
    s[outcome] = s[outcome].clip(lo, hi)
    f = f"{outcome} ~ pct_rank + log_assets + leverage + roa + C(fiscal_year) + C(sic_division)"
    m = smf.ols(f, data=s).fit(cov_type="cluster", cov_kwds={"groups": s["ticker"]})
    return m, len(s), s["ticker"].nunique()


def fmt_pct(x):
    return f"{x * 100:.2f}%"


def section(d, metric, label, include_pretax=False):
    p = build_panel(d, metric, include_pretax)
    lines = [f"### {label}", ""]
    for outcome, name in [("next_return", "Next-year stock return"), ("d_roa_next", "Next-year change in ROA")]:
        g, diff, t, pval, rho, rho_p, n = tercile_table(p, outcome)
        lines.append(f"**{name}** ({n} firm-years)")
        lines.append("")
        lines.append("| Pay Efficiency third | Firm-years | Mean | Median |")
        lines.append("|---|---|---|---|")
        for idx, r in g.iterrows():
            lines.append(f"| {idx} | {int(r['count'])} | {fmt_pct(r['mean'])} | {fmt_pct(r['median'])} |")
        lines.append("")
        lines.append(f"High minus Low: {fmt_pct(diff)} (Welch t = {t:.2f}, p = {pval:.3f}). "
                     f"Spearman rank correlation: {rho:.3f} (p = {rho_p:.3f}).")
        m, nobs, nfirms = regression(p, outcome)
        b, se, pv = m.params["pct_rank"], m.bse["pct_rank"], m.pvalues["pct_rank"]
        lines.append(f"Regression (controls: size, leverage, current ROA, year and industry; "
                     f"SEs clustered by firm; {nobs} obs, {nfirms} firms): moving from lowest to "
                     f"highest Pay Efficiency rank changes the outcome by {fmt_pct(b)} "
                     f"(SE {fmt_pct(se)}, p = {pv:.3f}). R-squared {m.rsquared:.3f}.")
        lines.append("")
    return lines, p


def main():
    OUT.mkdir(exist_ok=True)
    d = pd.read_csv(DATA, dtype={"cik": str})
    out = ["# Pay Efficiency: results", "",
           f"Source data: {DATA.name}, {len(d)} firm-years, {d['ticker'].nunique()} companies. "
           "Pay Efficiency in year t is compared with outcomes in year t+1 (t = 2022-2024).",
           "Excluded: financial firms (SIC 6000-6799), operating income of zero or less, and "
           "missing values. Thirds are formed within each fiscal year.", ""]
    main_lines, panel = section(d, "pay_efficiency", "Main test: compensation actually paid / operating income")
    out += main_lines
    out += section(d, "pay_efficiency_sct", "Robustness 1: Summary Compensation Table total / operating income")[0]
    out += section(d, "pay_efficiency", "Robustness 2: include firms where pretax income replaces operating income", True)[0]
    (OUT / "pay_efficiency_results.md").write_text("\n".join(out), encoding="utf-8")
    panel.to_csv(OUT / "analysis_panel.csv", index=False)
    print("\n".join(out))


if __name__ == "__main__":
    main()
