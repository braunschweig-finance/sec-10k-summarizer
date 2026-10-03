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
            # Model fallback list if high-demand 503/429 occurs
            models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]
            response = None
            last_error = None

            for model_name in models_to_try:
                for attempt in range(3):
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=f"You are a financial research assistant. Provide an executive summary with key financial insights for {company.name}:\n\n{filing_text[:max_chars]}",
                        )
                        break
                    except Exception as err:
                        last_error = err
                        err_str = str(err)
                        if ("503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str) and attempt < 2:
                            time.sleep(2 ** (attempt + 1))  # Exponential backoff: 2s, 4s
                        else:
                            break
                if response:
                    break

            if not response:
                raise last_error

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
