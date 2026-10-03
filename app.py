import re
import time
import warnings
import pandas as pd
import streamlit as st
from edgar import Company, set_identity
from google import genai

# Suppress internal warnings
warnings.filterwarnings("ignore")

# 1. SEC Identification
set_identity("Jacob Braunschweig jacob.braunschweig@gmail.com")

# 2. Page Configuration (NetAdvantage / Capital IQ Style)
st.set_page_config(page_title="SEC Financial & Corporate Governance Terminal", layout="wide")
st.title("🏛️ SEC Financial & Corporate Governance Terminal")
st.caption("Direct SEC EDGAR Statement Extraction (XBRL), Dynamic Ratios & DEF 14A Governance")

# Sidebar Controls
st.sidebar.header("Terminal Navigation")
ticker = st.sidebar.text_input("Enter Ticker Symbol:", "CAT").upper().strip()
run_analysis = st.sidebar.button("Fetch & Analyze SEC Data", type="primary")

def is_date_or_period_column(col_name):
    """Detects whether a column represents an audited fiscal reporting period."""
    s = str(col_name).strip()
    if re.search(r"\b20[2-3][0-9]", s):
        return True
    if any(tag in s.upper() for tag in ["(FY)", "(CY)", "Q1", "Q2", "Q3", "Q4"]):
        return True
    return False

def clean_statement_df(df):
    """Retains row label and numeric fiscal date period columns, formatting numbers with commas."""
    if df is None or df.empty:
        return None
    
    label_col = None
    for cand in ["label", "standard_concept", "concept"]:
        if cand in df.columns:
            label_col = cand
            break
            
    period_cols = [c for c in df.columns if is_date_or_period_column(c)]
    
    if not period_cols:
        meta_blacklist = {
            "concept", "standard_concept", "level", "abstract", "dimension",
            "dimension_axis", "dimension_member", "dimension_label", 
            "dimension_member_label", "parent_concept", "parent_abstract",
            "balance", "weight", "preferred_sign", "is_breakdown", "decimals"
        }
        period_cols = [c for c in df.columns if str(c).lower() not in meta_blacklist and c != label_col]

    if label_col:
        cols_to_keep = [label_col] + period_cols
        cleaned = df[cols_to_keep].copy()
        cleaned = cleaned.rename(columns={label_col: "Line Item"})
        cleaned = cleaned.set_index("Line Item")
    else:
        cleaned = df[period_cols].copy()

    for col in cleaned.columns:
        def format_val(x):
            try:
                num = float(str(x).replace(",", "").replace("$", "").replace("(", "-").replace(")", "").strip())
                if abs(num) >= 1000:
                    return f"{num:,.0f}"
                return x
            except Exception:
                return x
        cleaned[col] = cleaned[col].apply(format_val)
        
    return cleaned

def parse_num(val):
    if pd.notna(val) and str(val).lower() != "none" and str(val) != "":
        try:
            n = float(str(val).replace(",", "").replace("$", "").replace("(", "-").replace(")", "").strip())
            if abs(n) > 1000:
                return n
        except Exception:
            pass
    return None

def extract_metric(df, concepts, labels):
    """Extracts consolidated metric by matching concepts or exact labels, taking max to avoid division slices."""
    if df is None or df.empty:
        return None
        
    date_cols = [c for c in df.columns if is_date_or_period_column(c)]
    if not date_cols:
        return None
    latest_col = date_cols[0]

    target_df = df.copy()
    if "dimension" in target_df.columns:
        target_df = target_df[~target_df["dimension"].astype(bool)]
    elif "dimension_axis" in target_df.columns:
        target_df = target_df[target_df["dimension_axis"].isna() | (target_df["dimension_axis"] == "None") | (target_df["dimension_axis"] == "")]
    if target_df.empty:
        target_df = df

    vals = []
    # 1. Concept check
    for c_col in ["standard_concept", "concept"]:
        if c_col in target_df.columns:
            for c in concepts:
                subset = target_df[target_df[c_col].astype(str).str.lower().str.endswith(c.lower())]
                for _, r in subset.iterrows():
                    n = parse_num(r[latest_col])
                    if n is not None:
                        vals.append(n)

    # 2. Label check
    if "label" in target_df.columns:
        for lbl in labels:
            for _, r in target_df.iterrows():
                row_lbl = str(r["label"]).lower().strip().rstrip(":")
                if any(bad in row_lbl for bad in ["intersegment", "elimination", "par value"]):
                    continue
                if row_lbl == lbl.lower().strip() or row_lbl.startswith(lbl.lower().strip()):
                    n = parse_num(r[latest_col])
                    if n is not None:
                        vals.append(n)

    return max(vals) if vals else None

def extract_total_debt(df):
    """
    Computes total debt across all balance sheet segments.
    Sums distinct short-term borrowings and long-term debt lines, avoiding double-counting total rows.
    """
    if df is None or df.empty:
        return None
        
    date_cols = [c for c in df.columns if is_date_or_period_column(c)]
    if not date_cols:
        return None
    latest_col = date_cols[0]

    # First check if there is an explicit single 'Total Debt' consolidated line
    explicit_total = extract_metric(df, ["TotalDebt", "DebtInstrumentCarryingAmount"], ["Total debt"])
    if explicit_total and explicit_total > 5000:
        return explicit_total

    # Otherwise aggregate funded debt components (Short-term debt + Long-term debt across operating & finance divisions)
    debt_sum = 0.0
    seen_indices = set()
    label_col = "label" if "label" in df.columns else None

    for idx, r in df.iterrows():
        row_str = (str(r[label_col]) if label_col else "").lower()
        concept_str = (str(r.get("concept", "")) + " " + str(r.get("standard_concept", ""))).lower()
        full_text = f"{row_str} {concept_str}"

        # Match legitimate debt lines
        is_debt_line = any(term in full_text for term in [
            "short-term borrowings", "short-term debt", "commercial paper", 
            "long-term debt due after one year", "long-term debt, including", "long-term debt",
            "term debt", "notes payable", "debtcurrent", "longtermdebtnoncurrent"
        ])

        # Exclude aggregate lines, interest lines, and tax lines
        is_invalid = any(bad in full_text for bad in [
            "total debt", "interest", "tax", "fair value", "fair_value", "guarantee", "intersegment", "elimination"
        ])

        if is_debt_line and not is_invalid and idx not in seen_indices:
            val = parse_num(r[latest_col])
            if val is not None and val > 0:
                debt_sum += val
                seen_indices.add(idx)

    return debt_sum if debt_sum > 0 else None

@st.cache_data(show_spinner=False)
def get_sec_data(ticker_symbol):
    try:
        company = Company(ticker_symbol)
        
        financials = company.get_financials()
        raw_income = financials.income_statement().to_dataframe() if financials else None
        raw_balance = financials.balance_sheet().to_dataframe() if financials else None
        raw_cashflow = financials.cash_flow_statement().to_dataframe() if financials else None

        proxy_filings = company.get_filings(form="DEF 14A")
        governance_sections = {}
        proxy_raw = ""
        
        if proxy_filings:
            latest_proxy_filing = proxy_filings[0]
            try:
                proxy_raw = latest_proxy_filing.text()
            except Exception:
                proxy_raw = str(latest_proxy_filing.obj())
                
            proxy_lower = proxy_raw.lower()
            
            section_targets = {
                "Executive Compensation & Pay Analysis": ["executive compensation", "compensation discussion and analysis", "summary compensation table"],
                "Board of Directors & Committee Independence": ["board of directors", "director independence", "board committees and composition", "directors & governance"],
                "Shareholder Proposals & Voting Items": ["shareholder proposal", "proposal 1", "matters to be voted on", "shareholder voting matters"]
            }
            
            for section_title, keywords in section_targets.items():
                found_pos = -1
                for kw in keywords:
                    pos = proxy_lower.find(kw)
                    if pos != -1:
                        found_pos = pos
                        break
                if found_pos != -1:
                    governance_sections[section_title] = proxy_raw[found_pos : found_pos + 3500].strip()
                else:
                    governance_sections[section_title] = "Specific heading not directly matched in filing text. Full proxy is accessible for LLM synthesis."

        return {
            "name": company.name,
            "income": clean_statement_df(raw_income),
            "balance": clean_statement_df(raw_balance),
            "cashflow": clean_statement_df(raw_cashflow),
            "raw_income": raw_income,
            "raw_balance": raw_balance,
            "gov_sections": governance_sections,
            "proxy_raw": proxy_raw[:8000]
        }, None
    except Exception as e:
        return None, str(e)

if run_analysis or ticker:
    with st.spinner(f"Extracting SEC statements and proxy data for {ticker}..."):
        data, err = get_sec_data(ticker)

    if err:
        st.error(f"Error fetching data: {err}")
    elif data:
        st.subheader(f"{data['name']} ({ticker})")
        
        tab_stmt, tab_ratios, tab_gov, tab_memo = st.tabs([
            "📋 Financial Statements", 
            "📈 Financial Ratios", 
            "🗳️ Corporate Governance (DEF 14A)", 
            "🤖 AI Executive Memo"
        ])

        # TAB 1: FINANCIAL STATEMENTS
        with tab_stmt:
            st.markdown("### Audited Financial Statements (Direct from SEC XBRL)")
            stmt_view = st.radio(
                "Select Statement to Inspect:", 
                ["Income Statement", "Balance Sheet", "Cash Flow"], 
                horizontal=True
            )
            
            selected_df = None
            if stmt_view == "Income Statement":
                selected_df = data["income"]
            elif stmt_view == "Balance Sheet":
                selected_df = data["balance"]
            elif stmt_view == "Cash Flow":
                selected_df = data["cashflow"]

            if selected_df is not None and not selected_df.empty:
                st.dataframe(selected_df, use_container_width=True)
            else:
                st.info("Direct XBRL table not available for this statement.")

        # TAB 2: FINANCIAL RATIOS (Computed with Python)
        with tab_ratios:
            st.markdown("### Deterministic Ratio Analysis")
            st.caption("Computed via Python from audited line items (zero AI token consumption).")
            
            raw_inc = data.get("raw_income")
            raw_bal = data.get("raw_balance")
            
            # 1. Revenue
            revenue = extract_metric(
                raw_inc,
                ["SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
                ["Total sales and revenues", "Total net sales", "Total revenues", "Revenue"]
            )
            # 2. Cost of Goods / Sales
            cogs = extract_metric(
                raw_inc,
                ["CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
                ["Cost of goods sold", "Cost of sales", "Cost of products sold"]
            )
            # 3. Gross Profit
            gross_profit = extract_metric(
                raw_inc,
                ["GrossProfit"],
                ["Gross profit", "Gross margin"]
            )
            if not gross_profit and revenue and cogs:
                gross_profit = revenue - cogs

            # 4. Operating Income
            operating_income = extract_metric(
                raw_inc,
                ["OperatingIncomeLoss"],
                ["Operating profit", "Operating income", "Segment operating profit", "Earnings before income taxes"]
            )
            
            # 5. Current Assets & Current Liabilities (Consolidated Totals)
            current_assets = extract_metric(
                raw_bal,
                ["AssetsCurrent"],
                ["Total current assets", "Current assets"]
            )
            current_liab = extract_metric(
                raw_bal,
                ["LiabilitiesCurrent"],
                ["Total current liabilities", "Current liabilities"]
            )
            
            # 6. Total Debt (Cross-division funded debt aggregation)
            total_debt = extract_total_debt(raw_bal)
            
            # 7. Stockholders' Equity
            stockholders_equity = extract_metric(
                raw_bal,
                ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
                ["Total shareholders' equity", "Total stockholders' equity", "Caterpillar shareholders' equity", "ADM shareholders' equity", "Total equity"]
            )
            
            # Fallbacks if lines are completely non-standard
            total_assets = extract_metric(raw_bal, ["Assets"], ["Total assets", "Assets"])
            total_liab = extract_metric(raw_bal, ["Liabilities"], ["Total liabilities", "Liabilities"])
            
            if (not total_debt or total_debt == 0) and total_liab:
                total_debt = total_liab
                
            if (not stockholders_equity or stockholders_equity <= 0) and total_assets and total_liab:
                stockholders_equity = total_assets - total_liab

            # Calculated Ratios
            gm = f"{(gross_profit / revenue) * 100:.1f}%" if (gross_profit and revenue and revenue > 0) else "N/A"
            om = f"{(operating_income / revenue) * 100:.1f}%" if (operating_income and revenue and revenue > 0) else "N/A"
            cr = f"{(current_assets / current_liab):.2f}x" if (current_assets and current_liab and current_liab > 0) else "N/A"
            de = f"{(total_debt / stockholders_equity):.2f}x" if (total_debt and stockholders_equity and stockholders_equity > 0) else "N/A"
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Gross Margin", gm)
            col2.metric("Operating Margin", om)
            col3.metric("Current Ratio", cr)
            col4.metric("Debt-to-Equity", de)

        # TAB 3: CORPORATE GOVERNANCE (DEF 14A)
        with tab_gov:
            st.markdown("### Corporate Governance Disclosures (Form DEF 14A)")
            if data["gov_sections"]:
                for heading, text_excerpt in data["gov_sections"].items():
                    with st.expander(f"📑 {heading}", expanded=True):
                        st.markdown(text_excerpt[:2500] + ("\n\n*... [continued in filing] ...*" if len(text_excerpt) >= 2500 else ""))
            else:
                st.warning("No DEF 14A proxy filing located for this ticker.")

        # TAB 4: AI RESEARCH MEMO
        with tab_memo:
            st.markdown("### Institutional Research Memo Synthesis")
            st.caption("Synthesizes quantitative statement metrics and qualitative proxy governance into an executive brief.")
            
            if st.button("Generate Institutional Research Memo", type="primary"):
                with st.spinner("Synthesizing 10-K & DEF 14A disclosures with Gemini..."):
                    models_to_try = ["gemini-3.8-flash", "gemini-3.6-flash"]
                    response = None
                    last_error = None
                    
                    memo_prompt = f"""
                    You are a senior equity research analyst preparing an institutional investment and corporate governance memo.
                    Company: {data['name']} ({ticker})
                    
                    QUANTITATIVE AUDITED METRICS:
                    - Gross Margin: {gm}
                    - Operating Margin: {om}
                    - Current Ratio: {cr}
                    - Debt-to-Equity: {de}
                    
                    DEF 14A CORPORATE GOVERNANCE EXCERPT:
                    {data['proxy_raw'][:5000]}
                    
                    DELIVERABLES:
                    Structure your memo in clean Markdown with the following sections:
                    1. Executive Summary & Financial Quality (Interpret margins, working capital liquidity, and capital structure).
                    2. Corporate Governance Evaluation (Analyze executive compensation alignment, board independence, and shareholder proposals from the DEF 14A disclosures).
                    3. Strategic Capital Allocation & Risks (Evaluate R&D reinvestment, share repurchases/dividends, and operational risks).
                    """
                    
                    api_key = st.secrets["GEMINI_API_KEY"]
                    client = genai.Client(api_key=api_key)
                    
                    for model_name in models_to_try:
                        for attempt in range(3):
                            try:
                                response = client.models.generate_content(
                                    model=model_name,
                                    contents=memo_prompt
                                )
                                break
                            except Exception as err:
                                last_error = err
                                if "503" in str(err) or "429" in str(err) or "UNAVAILABLE" in str(err):
                                    time.sleep(2 ** (attempt + 1))
                                else:
                                    break
                        if response:
                            break
                            
                    if not response:
                        st.error(f"Failed to generate memo: {last_error}")
                    else:
                        st.markdown(response.text)
                        if hasattr(response, "usage_metadata"):
                            st.info(f"Tokens Consumed — Input: {response.usage_metadata.prompt_token_count} | Output: {response.usage_metadata.candidates_token_count}")
                        st.download_button(
                            label="📥 Download Research Memo (.txt)",
                            data=response.text,
                            file_name=f"{ticker}_Institutional_Memo.txt",
                            mime="text/plain"
                        )
