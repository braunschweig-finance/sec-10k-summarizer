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

def clean_statement_df(df):
    """Filters all XBRL dimensional axes, taxonomy metadata, and sets line labels as row index."""
    if df is None or df.empty:
        return None
    # Strip all raw taxonomy, dimension, and structural columns
    cols_to_drop = [
        c for c in [
            "concept", "standard_concept", "level", "abstract", 
            "dimension", "dimension_axis", "dimension_member", "is_breakdown"
        ] if c in df.columns
    ]
    cleaned = df.drop(columns=cols_to_drop)
    
    if "label" in cleaned.columns:
        cleaned = cleaned.set_index("label")
    return cleaned

def extract_metric(df, keywords):
    """Searches statement index for keywords and extracts the latest reported numeric value."""
    if df is None or df.empty:
        return None
    for idx in df.index:
        row_str = str(idx).lower()
        if any(kw.lower() in row_str for kw in keywords):
            series = df.loc[idx]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[0]
            # Search backward from the latest reported period
            for col in series.index:
                val = series[col]
                if pd.notna(val) and val != "":
                    try:
                        clean_num = float(str(val).replace(",", "").replace("$", "").replace("(", "-").replace(")", "").strip())
                        if abs(clean_num) > 1000:
                            return clean_num
                    except (ValueError, TypeError):
                        continue
    return None

@st.cache_data(show_spinner=False)
def get_sec_data(ticker_symbol):
    try:
        company = Company(ticker_symbol)
        
        # 1. Direct Financial Statements via XBRL
        financials = company.get_financials()
        income_df = clean_statement_df(financials.income_statement().to_dataframe()) if financials else None
        balance_df = clean_statement_df(financials.balance_sheet().to_dataframe()) if financials else None
        cashflow_df = clean_statement_df(financials.cash_flow_statement().to_dataframe()) if financials else None

        # 2. Extract Text from Form DEF 14A (Proxy Statement)
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
            "income": income_df,
            "balance": balance_df,
            "cashflow": cashflow_df,
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
            
            income = data["income"]
            balance = data["balance"]
            
            # Universal Revenue and Cost Parsing
            revenue = extract_metric(income, ["total sales and revenues", "total net sales", "total revenues", "revenue", "sales"])
            cost_of_goods = extract_metric(income, ["cost of goods sold", "cost of sales", "cost of products sold", "operating costs"])
            gross_profit = extract_metric(income, ["gross margin", "gross profit"])
            
            if not gross_profit and revenue and cost_of_goods:
                gross_profit = revenue - cost_of_goods
                
            operating_income = extract_metric(income, ["operating income", "operating profit", "operating earnings"])
            current_assets = extract_metric(balance, ["total current assets"])
            current_liab = extract_metric(balance, ["total current liabilities"])
            
            # Robust Debt Resolution across Industrials and Tech
            st_debt = extract_metric(balance, ["short-term debt", "commercial paper", "current portion of long-term debt", "notes payable"]) or 0
            lt_debt = extract_metric(balance, ["long-term debt due after one year", "long-term debt", "term debt", "total debt"]) or 0
            total_debt = (st_debt + lt_debt) if (st_debt + lt_debt) > 0 else extract_metric(balance, ["total debt", "total liabilities"])
            
            stockholders_equity = extract_metric(balance, [
                "total shareholders' equity", "total stockholders' equity", 
                "shareholders' equity", "stockholders' equity", "total equity", "caterpillar shareholders' equity"
            ])
            
            # Calculate ratios
            gm = f"{(gross_profit / revenue) * 100:.1f}%" if (gross_profit and revenue and revenue != 0) else "N/A"
            om = f"{(operating_income / revenue) * 100:.1f}%" if (operating_income and revenue and revenue != 0) else "N/A"
            cr = f"{(current_assets / current_liab):.2f}x" if (current_assets and current_liab and current_liab != 0) else "N/A"
            de = f"{(total_debt / stockholders_equity):.2f}x" if (total_debt and stockholders_equity and stockholders_equity != 0) else "N/A"
            
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
                        st.download_button(
                            label="📥 Download Research Memo (.txt)",
                            data=response.text,
                            file_name=f"{ticker}_Institutional_Memo.txt",
                            mime="text/plain"
                        )
