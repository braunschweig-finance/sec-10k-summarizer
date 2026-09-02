import time
import warnings
from edgar import Company, set_identity
from google import genai
import streamlit as st

# Suppress internal library warnings
warnings.filterwarnings("ignore")

# 1. SEC Identification
set_identity("Jacob Braunschweig jacob.braunschweig@gmail.com")

# 2. App Title & Layout
st.set_page_config(page_title="SEC 10-K AI Summarizer", layout="wide")
st.title("📊 SEC 10-K AI Summarizer")

# Sidebar settings
st.sidebar.header("Configuration")
max_chars = st.sidebar.slider("Text Length (Characters)", 2000, 15000, 8000, step=1000)

# Input field
ticker = st.text_input("Enter Stock Ticker:", "AAPL").upper()

# Display quick metric columns
col1, col2 = st.columns(2)
col1.metric("Target Stock", ticker)
col2.metric("Target Document", "Form 10-K")

if st.button("Generate AI Summary"):
    try:
        with st.spinner(f"Fetching 10-K filing for {ticker}..."):
            company = Company(ticker)
            filings = company.get_filings(form="10-K")

            if not filings:
                st.error(f"No 10-K filings found for ticker '{ticker}'.")
            else:
                # Fast extraction of filing text
                latest_10k = filings[0]
                filing_text = str(latest_10k.obj())

                # Read API key securely from Streamlit secrets
                api_key = st.secrets["GEMINI_API_KEY"]
                client = genai.Client(api_key=api_key)

        with st.spinner("Analyzing financial data with Gemini..."):
            # Send request with retry handling for high traffic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=f"You are a financial research assistant. Provide an executive summary with key financial insights for {company.name}:\n\n{filing_text[:max_chars]}",
                    )
                    break
                except Exception as err:
                    if "503" in str(err) and attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        raise err

            st.success("Analysis Complete!")
            
            # Output AI Summary
            st.markdown("### AI Analysis")
            st.write(response.text)

            # Add Download Button
            st.download_button(
                label="📥 Download Summary (.txt)",
                data=response.text,
                file_name=f"{ticker}_10K_Summary.txt",
                mime="text/plain"
            )

    except Exception as e:
        st.error(f"Exception Type: {type(e).__name__}")
        st.error(f"Details: {e}")
        st.exception(e)