"""
SEC data logic shared by the web API.

The functions below are copied unchanged from app.py (the Streamlit app), plus the duplicate
segment-row fix from PR #3, so the new site and the Streamlit site compute the same numbers.
app.py can't be imported directly because it runs the Streamlit page as soon as it loads.
"""
import io
import json
import re
import xml.etree.ElementTree as ET
from datetime import date
import threading
from collections import OrderedDict

import httpx
import pandas as pd
from docx import Document
from edgar import Company, set_identity

import peers

# SEC Compliance Identity
SEC_IDENTITY = "Jacob Braunschweig jacob.braunschweig@gmail.com"
set_identity(SEC_IDENTITY)

def is_date_or_period_column(col_name):
    """Detects whether a column represents an audited fiscal reporting period."""
    s = str(col_name).strip()
    if re.search(r"\b20[2-3][0-9]", s):
        return True
    if any(tag in s.upper() for tag in ["(FY)", "(CY)", "Q1", "Q2", "Q3", "Q4"]):
        return True
    return False

def latest_period_column(df):
    """Returns the most recent fiscal-year column (by end date), not just the first column."""
    period_cols = [c for c in df.columns if is_date_or_period_column(c)]
    if not period_cols:
        return None
    fy_cols = [c for c in period_cols if "(FY)" in str(c).upper()] or period_cols
    def end_date(c):
        m = re.search(r"\d{4}-\d{2}-\d{2}", str(c))
        return m.group(0) if m else ""
    return max(fy_cols, key=end_date)

def parse_num(val):
    """Converts an XBRL cell to float. Keeps zero, negatives and small values; returns None for blanks."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    if s.lower() in ["none", "nan", ""]:
        return None
    try:
        return float(s.replace(",", "").replace("$", "").replace("(", "-").replace(")", "").strip())
    except Exception:
        return None

def unit_kind(unit):
    """Classifies an XBRL unit name ("usd", "u_usd", "usdPerShare", "perShare", "shares", ...)."""
    u = str(unit).lower() if unit is not None and not pd.isna(unit) else "usd"
    if "share" in u:
        return "per_share" if "per" in u else "shares"
    if "usd" in u:
        return "usd"
    return "other"

def format_cell(val, unit):
    """Formats one statement value by its XBRL unit: USD in $ millions, per-share in $, shares in millions."""
    num = parse_num(val)
    if num is None:
        return ""
    kind = unit_kind(unit)
    if kind == "usd":
        return f"${num / 1_000_000:,.0f}"
    if kind == "per_share":
        return f"${num:,.2f}"
    if kind == "shares":
        return f"{num / 1_000_000:,.1f}M sh"
    return f"{num:,.2f}"

def clean_statement_df(df):
    """
    Cleans XBRL statements to match Capital IQ:
    - Retains row label and numeric fiscal date periods
    - Removes abstract category header rows that have no numeric values
    - Scales dollar values to millions ($M); per-share and share counts keep their own units
    """
    if df is None or df.empty:
        return None

    label_col = None
    for cand in ["label", "standard_concept", "concept"]:
        if cand in df.columns:
            label_col = cand
            break

    period_cols = [c for c in df.columns if is_date_or_period_column(c)]
    if not period_cols:
        return None

    work = df.copy()
    if "abstract" in work.columns:
        work = work[~work["abstract"].fillna(False).astype(bool)]

    # Drop header rows where every period value is blank or zero
    has_number = work[period_cols].apply(
        lambda row: any((parse_num(v) or 0) != 0 for v in row), axis=1
    )
    work = work[has_number]

    # Drop segment rows that just repeat their consolidated line (e.g., CAT's interest expense,
    # which is all Financial Products), so the same amount doesn't appear twice
    if "dimension" in work.columns and "concept" in work.columns:
        is_dim = work["dimension"].fillna(False).astype(bool)
        parent_values = {
            r["concept"]: tuple(r[c] for c in period_cols)
            for _, r in work[~is_dim].iterrows()
        }
        repeats = work[is_dim].apply(
            lambda r: parent_values.get(r["concept"]) == tuple(r[c] for c in period_cols), axis=1
        )
        work = work.drop(repeats[repeats].index)

    units = work["unit"] if "unit" in work.columns else pd.Series("usd", index=work.index)
    cleaned = pd.DataFrame(index=work.index)
    cleaned["Line Item"] = work[label_col] if label_col else work.index.astype(str)
    for col in period_cols:
        cleaned[col] = [format_cell(v, u) for v, u in zip(work[col], units)]
    return cleaned.set_index("Line Item")

def _norm_label(s):
    return str(s).lower().replace("’", "'").strip().rstrip(":").strip()

def extract_metric(df, concepts, labels):
    """
    Finds one consolidated line item in the latest fiscal year.
    Order: exact XBRL concepts in priority order, then exact row labels on company-specific
    (non us-gaap) concepts only, since labels on standard concepts can be misleading.
    Segment (dimensional), abstract and non-USD rows are skipped. Returns {"value", "concept", "label", "period"} or None.
    """
    if df is None or df.empty:
        return None
    period = latest_period_column(df)
    if period is None:
        return None

    rows = df
    if "dimension" in rows.columns:
        rows = rows[~rows["dimension"].fillna(False).astype(bool)]
    if "abstract" in rows.columns:
        rows = rows[~rows["abstract"].fillna(False).astype(bool)]
    if "unit" in rows.columns:
        rows = rows[rows["unit"].map(unit_kind) == "usd"]
    if rows.empty:
        return None

    # "us-gaap_Revenues" -> "Revenues"
    concept_names = rows["concept"].astype(str).str.split(r"[_:]", n=1).str[-1] if "concept" in rows.columns else None

    def first_hit(mask):
        for _, r in rows[mask].iterrows():
            n = parse_num(r[period])
            if n is not None:
                return {"value": n, "concept": str(r.get("concept", "")), "label": str(r.get("label", "")), "period": str(period)}
        return None

    if concept_names is not None:
        for c in concepts:
            hit = first_hit(concept_names == c)
            if hit:
                return hit
    if "label" in rows.columns:
        row_labels = rows["label"].map(_norm_label)
        custom = ~rows["concept"].astype(str).str.startswith("us-gaap") if "concept" in rows.columns else True
        for lbl in labels:
            hit = first_hit((row_labels == _norm_label(lbl)) & custom)
            if hit:
                return hit
    return None

def compute_ratios(raw_inc, raw_bal):
    """Pulls the ratio inputs from the latest 10-K and computes the four ratios. Returns (ratios, inputs)."""
    revenue = extract_metric(raw_inc, ["Revenues", "RevenuesNetOfInterestExpense"], [])
    if revenue is None:
        # Banks without a total revenue line: net interest income + noninterest income
        nii = extract_metric(raw_inc, ["InterestIncomeExpenseNet"], [])
        nonint = extract_metric(raw_inc, ["NoninterestIncome"], [])
        if nii and nonint:
            revenue = {"value": nii["value"] + nonint["value"], "concept": "Derived: Net interest income + Noninterest income",
                       "label": "Net interest income + Total noninterest income", "period": nii["period"]}
    if revenue is None:
        revenue = extract_metric(
            raw_inc,
            ["RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
            ["Total sales and revenues", "Total net sales", "Total revenues", "Total net revenue", "Net sales", "Revenues", "Revenue"]
        )

    inputs = {
        "Revenue": revenue,
        "Cost of Revenue": extract_metric(
            raw_inc,
            ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"],
            ["Cost of goods sold", "Cost of sales", "Cost of products sold", "Cost of revenue", "Total cost of revenue", "Total cost of sales"]
        ),
        "Gross Profit": extract_metric(raw_inc, ["GrossProfit"], ["Gross profit", "Gross margin"]),
        "Operating Income": extract_metric(
            raw_inc,
            ["OperatingIncomeLoss"],
            ["Operating profit", "Operating income", "Operating income (loss)", "Income from operations"]
        ),
        "Current Assets": extract_metric(raw_bal, ["AssetsCurrent"], ["Total current assets"]),
        "Current Liabilities": extract_metric(raw_bal, ["LiabilitiesCurrent"], ["Total current liabilities"]),
        "Total Liabilities": extract_metric(raw_bal, ["Liabilities"], ["Total liabilities"]),
        "Shareholders' Equity": extract_metric(
            raw_bal,
            ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
            ["Total shareholders' equity", "Total stockholders' equity", "Total equity"]
        ),
    }

    # Derived inputs are labeled as such so every number still traces to filed line items
    rev, cogs = inputs["Revenue"], inputs["Cost of Revenue"]
    if inputs["Gross Profit"] is None and rev and cogs:
        inputs["Gross Profit"] = {"value": rev["value"] - cogs["value"], "concept": "Derived: Revenue - Cost of Revenue",
                                  "label": "Revenue - Cost of Revenue", "period": rev["period"]}
    if inputs["Total Liabilities"] is None:
        liab_and_eq = extract_metric(raw_bal, ["LiabilitiesAndStockholdersEquity"], ["Total liabilities and shareholders' equity", "Total liabilities and stockholders' equity", "Total liabilities and equity"])
        total_eq = extract_metric(
            raw_bal,
            ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"],
            ["Total equity", "Total shareholders' equity", "Total stockholders' equity"]
        )
        if liab_and_eq and total_eq:
            inputs["Total Liabilities"] = {"value": liab_and_eq["value"] - total_eq["value"],
                                           "concept": "Derived: Total liabilities & equity - Total equity",
                                           "label": "Total liabilities & equity - Total equity", "period": liab_and_eq["period"]}

    def v(name):
        return inputs[name]["value"] if inputs[name] else None

    def pct(num, den):
        return f"{num / den * 100:.1f}%" if num is not None and den is not None and den > 0 else "N/A"

    def times(num, den):
        return f"{num / den:.2f}x" if num is not None and den is not None and den > 0 else "N/A"

    equity = v("Shareholders' Equity")
    ratios = {
        "Gross Margin": pct(v("Gross Profit"), v("Revenue")),
        "Operating Margin": pct(v("Operating Income"), v("Revenue")),
        "Current Ratio": times(v("Current Assets"), v("Current Liabilities")),
        # Negative equity makes the ratio meaningless, so say so instead of showing a negative multiple
        "Total Liabilities-to-Equity": "N/M (negative equity)" if equity is not None and equity < 0
                                       else times(v("Total Liabilities"), equity),
    }
    return ratios, inputs

def clean_governance_text(raw_text):
    """
    Cleans raw SEC proxy text (works for any filer):
    - Removes underscores, horizontal lines, dashes, and boilerplate rules
    - Removes running "Proxy Statement" page headers and mailing addresses
    - Collapses whitespace
    """
    if not raw_text:
        return ""
    text = raw_text
    # Drop invisible characters and unify dashes/apostrophes so keyword searches match
    text = re.sub(r"[\u00ad\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"[\u2010\u2011\u2012\u2013]", "-", text)
    text = text.replace("\u2019", "'")
    # Remove lines of underscores, dashes, equals signs
    text = re.sub(r"_{2,}", " ", text)
    text = re.sub(r"-{3,}", " ", text)
    text = re.sub(r"={3,}", " ", text)
    # Remove running SEC headers/footers and addresses
    text = re.sub(r"\b\d{4}\s+Proxy Statement\s+\d{1,3}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"Proxy Statement\s*\d{4}\s*\d{1,3}", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"c/o Corporate Secretary.{0,200}?\d{5}", " ", text, flags=re.IGNORECASE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text

# Keyword checks for the governance tiles. A hit means the proxy discusses the topic; the matching
# sentence is shown as evidence so the reader can confirm what the filing actually says.
GOVERNANCE_CHECKS = {
    "Lead Independent Director": [r"lead independent director", r"\blead director\b", r"presiding (?:independent )?director"],
    "Clawback Policy": [r"clawback", r"(?:incentive )?compensation recovery policy"],
    "Anti-Hedging Policy": [r"anti-hedging", r"hedging (?:and|or) pledging", r"prohibit\w*[^.]{0,200}hedg"],
    "Say-on-Pay Vote": [r"advisory vote to approve (?:the )?(?:compensation of (?:our )?named executive officers|(?:named )?executive (?:officer )?compensation)",
                        r"say[- ]on[- ]pay"],
}

def html_to_plain_text(html):
    """Strips tags from an HTML document, keeping block breaks as newlines."""
    from bs4 import BeautifulSoup
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # Inline XBRL proxies hide header facts in ix:header; drop them so they don't pollute the text
    for tag in soup.find_all(["ix:header"]):
        tag.decompose()
    return soup.get_text("\n")

def get_proxy_text(filing):
    """
    Returns (text, source) for a DEF 14A. Reads the filing's primary HTML document directly; if that comes back
    too short to be a full proxy, reads every HTML document in the filing, since some proxies are split across
    several files. (edgartools' filing.text() loads the whole submission, images included: Goldman Sachs' proxy
    took over 500 MB that way, more than the free server has.)
    """
    text, source = "", "none"
    try:
        doc = getattr(filing, "primary_document", "")
        if doc and doc.lower().endswith((".htm", ".html")):
            url = f"https://www.sec.gov/Archives/edgar/data/{int(filing.cik)}/{filing.accession_no.replace('-', '')}/{doc}"
            text = html_to_plain_text(sec_fetch(url))
            source = "primary document"
    except Exception:
        text = ""
    if len(text) >= 50000:
        return text, source

    parts = []
    try:
        for att in filing.attachments:
            if not att.is_html() or att.is_report() or att.empty:
                continue
            content = att.download()
            if content:
                parts.append(html_to_plain_text(content))
    except Exception:
        pass
    combined = "\n\n".join(parts)
    if len(combined) > len(text):
        return combined, f"{len(parts)} HTML document(s) in the filing"
    return text, source

def find_evidence(text, patterns):
    """Returns the sentence around the first pattern match in the proxy, or None."""
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            start = max(text.rfind(". ", 0, m.start()) + 2, m.start() - 300, 0)
            end = text.find(". ", m.end())
            end = min(end + 1 if end != -1 else len(text), m.end() + 300)
            return text[start:end].strip()
    return None

def build_word_memo(ticker_sym, company_nm, ratios_dict, gov_dict, memo_body):
    """Generates a structured Word (.docx) Institutional Research Memo."""
    doc = Document()
    doc.add_heading(f"Institutional Research & Corporate Governance Brief", level=0)
    doc.add_paragraph(f"Company: {company_nm} ({ticker_sym}) | Source: Audited SEC EDGAR 10-K & DEF 14A")

    doc.add_heading("1. Executive Summary & Audited Ratios", level=1)
    table = doc.add_table(rows=1, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = "Financial Ratio"
    hdr_cells[1].text = "Audited Metric Value"
    for metric_name, val in ratios_dict.items():
        row_cells = table.add_row().cells
        row_cells[0].text = metric_name
        row_cells[1].text = str(val)

    doc.add_heading("2. Qualitative Corporate Governance Disclosures (DEF 14A)", level=1)
    for section_title, section_content in gov_dict.items():
        doc.add_heading(section_title, level=2)
        doc.add_paragraph(section_content[:1500] + ("..." if len(section_content) > 1500 else ""))

    doc.add_heading("3. Institutional Equity Research Synthesis", level=1)
    doc.add_paragraph(memo_body)

    file_buffer = io.BytesIO()
    doc.save(file_buffer)
    return file_buffer.getvalue()

def latest_filings(company, form):
    """A company's filings of one form, newest first. SEC's first page of a filing history covers at least the last
    year, which always holds the latest 10-K and proxy. Loading the full history instead costs big issuers a lot of
    memory: JPMorgan files thousands of note prospectuses a year, and its full list took about 75 MB."""
    found = company.get_filings(form=form, trigger_full_load=False)
    if found is not None and len(found) > 0:
        return found
    return company.get_filings(form=form)


def statement_frames(statement):
    """Returns (display_df, raw_df) for one statement, or (None, None) if the filing lacks it."""
    if statement is None:
        return None, None
    # standard=False keeps the filer's own line-item labels instead of edgartools' standardized ones
    display_df = statement.to_dataframe(view="standard", include_unit=True, standard=False)
    raw_df = statement.to_dataframe(presentation=False, include_unit=True, standard=False)
    return display_df, raw_df

SECTION_TARGETS = {
    "Board Leadership & Lead Independent Director Structure": [
        "board leadership structure", "lead independent director", "director independence"
    ],
    "Executive Compensation & Pay-for-Performance (CD&A)": [
        "compensation discussion and analysis", "executive compensation program",
        "compensation philosophy", "summary compensation table"
    ],
    "Annual Meeting Agenda & Shareholder Voting Items": [
        "matters to be voted on", "proposals to be voted on", "election of directors",
        "shareholder proposals", "stockholder proposals"
    ],
    "Clawback Policies, Anti-Hedging & Risk Oversight": [
        "clawback policy", "compensation recovery policy",
        "anti-hedging", "hedging and pledging", "risk oversight"
    ]
}

def statement_json(df):
    """Turns a cleaned statement table into {"periods": [...], "rows": [{"label", "values"}]} for the web page."""
    if df is None or df.empty:
        return None
    return {
        "periods": [str(c) for c in df.columns],
        "rows": [{"label": str(label), "values": [str(v) for v in row]} for label, row in df.iterrows()],
    }

def section_passage(text_body):
    """Shows the passage as filed, cut at the last full sentence (same rule as app.py after PR #3)."""
    passage = text_body[:2000]
    last_stop = passage.rfind(". ")
    if len(text_body) > 2000 and last_stop > 500:
        passage = passage[:last_stop + 1]
    return passage

def get_financial_report(ticker_symbol):
    """The 10-K half of the page: statements, ratios and their source line items. Same steps as get_sec_data in app.py."""
    company = Company(ticker_symbol)

    financials = company.get_financials()
    print(f"[{ticker_symbol}] 10-K financials loaded", flush=True)
    disp_income, raw_income = statement_frames(financials.income_statement() if financials else None)
    disp_balance, raw_balance = statement_frames(financials.balance_sheet() if financials else None)
    disp_cashflow, _ = statement_frames(financials.cash_flow_statement() if financials else None)

    ratios, inputs = compute_ratios(raw_income, raw_balance)
    tenk_filings = latest_filings(company, "10-K")

    return {
        "ticker": ticker_symbol,
        "name": company.name,
        "tenk_url": tenk_filings[0].url if tenk_filings else "",
        "statements": {
            "income": statement_json(clean_statement_df(disp_income)),
            "balance": statement_json(clean_statement_df(disp_balance)),
            "cashflow": statement_json(clean_statement_df(disp_cashflow)),
        },
        "ratios": ratios,
        # Values in $ millions, with the filed line item and XBRL concept each one came from
        "inputs": {
            name: ({"value_m": hit["value"] / 1_000_000, "label": hit["label"], "concept": hit["concept"], "period": hit["period"]}
                   if hit else None)
            for name, hit in inputs.items()
        },
    }


def get_governance_report(ticker_symbol):
    """The DEF 14A half of the page: topic checks with quoted evidence and the four proxy passages."""
    company = Company(ticker_symbol)
    proxy_filings = latest_filings(company, "DEF 14A")

    governance = {"checks": {}, "sections": {}, "proxy_url": "", "proxy_date": "", "proxy_chars": 0, "proxy_source": ""}
    if proxy_filings:
        latest_proxy = proxy_filings[0]
        proxy_raw, proxy_source = get_proxy_text(latest_proxy)
        print(f"[{ticker_symbol}] DEF 14A read ({len(proxy_raw):,} characters)", flush=True)
        proxy_flat = clean_governance_text(proxy_raw)
        governance.update(proxy_url=latest_proxy.url, proxy_date=str(latest_proxy.filing_date),
                          proxy_chars=len(proxy_raw), proxy_source=proxy_source)
        for check, patterns in GOVERNANCE_CHECKS.items():
            governance["checks"][check] = find_evidence(proxy_flat, patterns)

        # Prefer matches after the first 15,000 characters to bypass the table of contents and cover page
        proxy_lower = proxy_flat.lower()
        body_start = 15000 if len(proxy_flat) > 25000 else 0
        for section_title, keywords in SECTION_TARGETS.items():
            found_pos = -1
            for kw in keywords:
                pos = proxy_lower.find(kw, body_start)
                if pos == -1:
                    pos = proxy_lower.find(kw)
                if pos != -1:
                    found_pos = pos
                    break
            governance["sections"][section_title] = (
                section_passage(proxy_flat[found_pos : found_pos + 3000]) if found_pos != -1
                else "No matching section heading was found in the proxy text."
            )
    return governance


# ---------- Pay Efficiency (ported from finance-research/scripts/pull_pay_efficiency.py) ----------
# CEO pay isn't in SEC's companyfacts summary, so it's read from the proxy's own XBRL file
# (Pay Versus Performance table, ecd: tags). Operating income comes from companyfacts for the same fiscal year.

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
PVP_TAGS = {"PeoTotalCompAmt": "peo_total_comp", "PeoActuallyPaidCompAmt": "peo_cap"}
OP_TAGS = ["OperatingIncomeLoss"]
PRETAX_TAGS = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
]


def sec_fetch(url):
    r = httpx.get(url, headers={"User-Agent": SEC_IDENTITY}, timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.content


def days_apart(a, b):
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def instance_url(cik, accn):
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}"
    names = [i["name"] for i in json.loads(sec_fetch(folder + "/index.json"))["directory"]["item"]]
    # SEC extracts inline XBRL into a file ending in _htm.xml
    for n in names:
        if n.endswith("_htm.xml"):
            return f"{folder}/{n}"
    for n in names:
        if n.endswith(".xml") and "FilingSummary" not in n and not n.endswith(("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml")):
            return f"{folder}/{n}"
    return None


def pvp_from_xml(xml_bytes):
    """Pay Versus Performance numbers by fiscal year end: {fy_end: {"peo_cap", "peo_total_comp", "ceo_count", "ceos", "flags"}}."""
    root = ET.fromstring(xml_bytes)
    contexts = {}
    for ctx in root.iter(XBRLI + "context"):
        p = ctx.find(XBRLI + "period")
        end = p.findtext(XBRLI + "endDate") or p.findtext(XBRLI + "instant")
        members = tuple(sorted(f"{m.get('dimension')}={m.text}" for m in ctx.iter(XBRLDI + "explicitMember")))
        contexts[ctx.get("id")] = (end, members)

    facts = []
    for el in root:
        if "}" not in el.tag or "/ecd/" not in el.tag.split("}")[0]:
            continue
        end, members = contexts.get(el.get("contextRef"), (None, ()))
        try:
            val = float((el.text or "").strip())
        except ValueError:
            continue
        facts.append((el.tag.split("}")[1], end, members, val))

    # Fiscal year ends = end dates of the company's own TSR (no dimension)
    fy_ends = sorted({end for name, end, members, val in facts if name == "TotalShareholderRtnAmt" and not members})
    out = {fy: {"flags": []} for fy in fy_ends}

    def fy_for(end):
        # A CEO who left mid-year has an earlier end date; map it to the next fiscal year end
        for fy in fy_ends:
            if date.fromisoformat(fy) >= date.fromisoformat(end) or days_apart(fy, end) <= 10:
                return fy
        return None

    for tag, col in PVP_TAGS.items():
        per_ceo = {}  # (fy, individual) -> value
        for name, end, members, val in facts:
            if name != tag or end is None:
                continue
            if [m for m in members if not m.startswith("ecd:IndividualAxis=")]:
                continue  # adjustment breakdowns, not the headline number
            fy = fy_for(end)
            if fy is None:
                continue
            who = members[0].split("=", 1)[1] if members else ""
            if who and val == 0:
                continue  # a former or future CEO shown as $0 for a year they weren't CEO
            key = (fy, who)
            if key in per_ceo and per_ceo[key] != val:
                # Some filings repeat a figure rounded (e.g. 54.7M for 54,746,734); keep the exact one
                if len(str(int(abs(val))).rstrip("0")) > len(str(int(abs(per_ceo[key]))).rstrip("0")):
                    per_ceo[key] = val
            per_ceo.setdefault(key, val)
        for fy in out:
            people = {who: v for (f, who), v in per_ceo.items() if f == fy}
            if "" in people and len(people) != 1:
                out[fy]["flags"].append(f"{tag}: filing tags both a total and per-CEO amounts; used the total")
                people = {"": people[""]}
            if people:
                out[fy][col] = sum(people.values())
                if col == "peo_cap":
                    out[fy]["ceo_count"] = len(people)
                    out[fy]["ceos"] = [ceo_name(who) for who in people if who]
    return out


def ceo_name(member):
    """"CAT:Mr.UmplebyMember" -> "Mr. Umpleby" (the filer's own label for the CEO)."""
    name = re.sub(r"Member$", "", member.split(":")[-1])
    name = re.sub(r"(?<=[a-z.])(?=[A-Z])", " ", name)
    return name.strip()


def tenk_value(gaap, tags, fy_end):
    """First-filed 10-K value of a full-year income statement item for fy_end: (value, tag, accession)."""
    for tag in tags:
        hits = [r for r in gaap.get(tag, {}).get("units", {}).get("USD", [])
                if r.get("form") == "10-K" and days_apart(r["end"], fy_end) <= 10
                and "start" in r and 340 <= days_apart(r["start"], r["end"]) <= 390]
        if hits:
            first = min(hits, key=lambda r: r["filed"])
            return first["val"], tag, first["accn"]
    return None, None, None


def get_pay_efficiency(ticker_symbol):
    """CEO compensation actually paid / operating income for the latest year in the newest proxy's Pay Versus Performance table."""
    company = Company(ticker_symbol)
    cik = str(company.cik).zfill(10)
    proxies = latest_filings(company, "DEF 14A")
    if not proxies:
        return {"available": False, "reason": "No DEF 14A proxy statement on EDGAR for this company."}
    proxy = proxies[0]
    accn = proxy.accession_no
    url = instance_url(cik, accn)
    if not url:
        return {"available": False, "reason": "The latest proxy has no XBRL data, so the Pay Versus Performance table can't be read."}
    pvp = {fy: v for fy, v in pvp_from_xml(sec_fetch(url)).items() if v.get("peo_cap") is not None}
    print(f"[{ticker_symbol}] Pay Versus Performance read ({len(pvp)} years)", flush=True)
    if not pvp:
        return {"available": False, "reason": "The latest proxy doesn't tag CEO compensation actually paid (ecd:PeoActuallyPaidCompAmt)."}
    fy_end = max(pvp)
    v = pvp[fy_end]

    gaap = companyfacts(cik)
    years = [pay_efficiency_year(gaap, cik, fy, pvp[fy]) for fy in sorted(pvp)]
    latest = years[-1]
    return {
        "available": True,
        **latest,
        "ceo_count": v.get("ceo_count", 1),
        "ceos": v.get("ceos", []),
        "sct_total_m": v["peo_total_comp"] / 1_000_000 if v.get("peo_total_comp") is not None else None,
        "pay_concept": "ecd:PeoActuallyPaidCompAmt",
        "proxy_url": proxy.url,
        "proxy_date": str(proxy.filing_date),
        "proxy_accn": accn,
        # Every year in the proxy's Pay Versus Performance table (up to five), oldest first, for the trend chart
        "history": [{k: y[k] for k in HISTORY_KEYS} for y in years],
        "peers": peers.rank(ticker_symbol, latest["fy_end"], latest["pct"], latest["denominator"]),
    }


HISTORY_KEYS = ["fy_end", "value", "pct", "ceo_pay_m", "op_income_m", "op_concept", "denominator", "tenk_accn"]


def pay_efficiency_year(gaap, cik, fy_end, v):
    """Pay Efficiency for one fiscal year of the Pay Versus Performance table, with its 10-K source."""
    denominator = "operating"
    op, op_tag, op_accn = tenk_value(gaap, OP_TAGS, fy_end)
    if op is None:
        op, op_tag, op_accn = tenk_value(gaap, PRETAX_TAGS, fy_end)
        denominator = "pretax" if op is not None else ""
    flags = list(v["flags"])
    if denominator == "pretax":
        flags.append("No us-gaap:OperatingIncomeLoss tag in the 10-K, so pretax income is used instead.")
    if v.get("ceo_count", 1) > 1:
        flags.append(f"{v['ceo_count']} people served as CEO this year; their pay is added together.")

    cap = v["peo_cap"]
    pct = None
    if op is None:
        value = "N/A"
        flags.append("No operating or pretax income found in a 10-K for this fiscal year.")
    elif op <= 0:
        value = "N/M (operating loss)"
    else:
        pct = cap / op * 100
        value = f"{pct:.2f}%"
    return {
        "value": value,
        "pct": pct,
        "fy_end": fy_end,
        "ceo_pay_m": cap / 1_000_000,
        "op_income_m": op / 1_000_000 if op is not None else None,
        "op_concept": f"us-gaap:{op_tag}" if op_tag else "",
        "denominator": denominator,
        "tenk_accn": op_accn or "",
        "tenk_url": filing_folder(cik, op_accn),
        "flags": flags,
    }


def filing_folder(cik, accn):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/" if accn else ""


FACT_KEYS = ("val", "start", "end", "accn", "filed", "form")
_facts = OrderedDict()
_facts_lock = threading.Lock()
FACTS_CACHE_SIZE = 16


def used_tags():
    return set(OP_TAGS + PRETAX_TAGS + ["InterestIncomeExpenseNet", "NoninterestIncome"]
               + [t for tags in TREND_TAGS.values() for t in tags])


def slim_facts(us_gaap):
    """Keeps only the full-year 10-K rows of the tags this app reads, in the same shape as companyfacts."""
    keep = used_tags()
    out = {}
    for tag, body in us_gaap.items():
        if tag not in keep:
            continue
        rows = [{k: r.get(k) for k in FACT_KEYS} for r in body.get("units", {}).get("USD", [])
                if r.get("form") == "10-K" and "start" in r and 340 <= days_apart(r["start"], r["end"]) <= 390]
        if rows:
            out[tag] = {"units": {"USD": rows}}
    return out


def companyfacts(cik):
    """The us-gaap facts this app uses from SEC's companyfacts file. The full file can be tens of MB, so it is
    read one company at a time (the free server has 512 MB) and only the few tags needed are kept, which makes
    the cache small enough to hold several companies and lets the trends lookup reuse the Pay Efficiency read."""
    with _facts_lock:
        if cik in _facts:
            _facts.move_to_end(cik)
            return _facts[cik]
        raw = sec_fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        slim = slim_facts(json.loads(raw)["facts"].get("us-gaap", {}))
        del raw
        _facts[cik] = slim
        while len(_facts) > FACTS_CACHE_SIZE:
            _facts.popitem(last=False)
        return slim


# ---------- Multi-year trends (same companyfacts file, each year's own 10-K) ----------

TREND_TAGS = {
    "Revenue": ["Revenues", "RevenuesNetOfInterestExpense", "RevenueFromContractWithCustomerExcludingAssessedTax",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "Cost of Revenue": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold",
                        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization"],
    "Gross Profit": ["GrossProfit"],
    "Operating Income": OP_TAGS,
    "Net Income": ["NetIncomeLoss"],
}
TREND_YEARS = 5


def fiscal_year_ends(gaap, tags):
    """End dates of full fiscal years reported in 10-Ks for any of the tags, newest last. Dates within 10 days count as one year."""
    ends = sorted({r["end"] for tag in tags for r in gaap.get(tag, {}).get("units", {}).get("USD", [])
                   if r.get("form") == "10-K" and "start" in r and 340 <= days_apart(r["start"], r["end"]) <= 390})
    merged = []
    for e in ends:
        if merged and days_apart(merged[-1], e) <= 10:
            merged[-1] = e
        else:
            merged.append(e)
    return merged


def trend_year(gaap, cik, fy_end):
    """One fiscal year's income-statement lines (as first reported in a 10-K) and the margins computed from them."""
    lines = {}
    for name, tags in TREND_TAGS.items():
        val, tag, accn = tenk_value(gaap, tags, fy_end)
        lines[name] = {"value_m": val / 1_000_000, "concept": f"us-gaap:{tag}", "accn": accn, "url": filing_folder(cik, accn)} if val is not None else None
    if lines["Revenue"] is None:
        # Banks: net interest income + noninterest income, the same rule as the ratio cards
        nii, _, accn = tenk_value(gaap, ["InterestIncomeExpenseNet"], fy_end)
        nonint, _, _ = tenk_value(gaap, ["NoninterestIncome"], fy_end)
        if nii is not None and nonint is not None:
            lines["Revenue"] = {"value_m": (nii + nonint) / 1_000_000, "concept": "Derived: InterestIncomeExpenseNet + NoninterestIncome",
                                "accn": accn, "url": filing_folder(cik, accn)}
    rev, cogs = lines["Revenue"], lines["Cost of Revenue"]
    if lines["Gross Profit"] is None and rev and cogs:
        lines["Gross Profit"] = {"value_m": rev["value_m"] - cogs["value_m"], "concept": "Derived: Revenue - Cost of Revenue",
                                 "accn": rev["accn"], "url": rev["url"]}

    def margin(name):
        line = lines[name]
        return line["value_m"] / rev["value_m"] * 100 if line and rev and rev["value_m"] > 0 else None

    return {
        "fy_end": fy_end,
        "fiscal_year": peers.fiscal_year(fy_end),
        "lines": lines,
        "margins": {"Gross Margin": margin("Gross Profit"), "Operating Margin": margin("Operating Income"), "Net Margin": margin("Net Income")},
    }


def get_trends(ticker_symbol):
    """The last five fiscal years of revenue, profits and margins, each from the 10-K that first reported it."""
    company = Company(ticker_symbol)
    cik = str(company.cik).zfill(10)
    gaap = companyfacts(cik)
    ends = fiscal_year_ends(gaap, TREND_TAGS["Revenue"] + TREND_TAGS["Net Income"])[-TREND_YEARS:]
    print(f"[{ticker_symbol}] trends: {len(ends)} fiscal years", flush=True)
    return {"ticker": ticker_symbol, "years": [trend_year(gaap, cik, e) for e in ends]}
