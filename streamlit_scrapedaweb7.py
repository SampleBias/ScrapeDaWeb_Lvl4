import streamlit as st
import sys
import os
import time
from streamlit_tags import st_tags_sidebar
import pandas as pd
import json
from datetime import datetime
from functools import lru_cache
import asyncio
import aiohttp
import html2text

# Set page config as the first Streamlit command
st.set_page_config(page_title="Universal Web Scraper", page_icon="💀", layout="wide")

# Append the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the custom scraper module
try:
    import scrapedaweb4_Mac as scraper
    scraper_imported = True
except ImportError as e:
    scraper_imported = False
    import_error = str(e)

# Custom CSS to improve the app's appearance
st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; }
    .stButton>button { width: 100%; }
    .stProgress .st-bo { background-color: #f63366; }
    .stTextInput>div>div>input { border-radius: 10px; }
    .stSelectbox>div>div>select { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# Main app layout
st.title("💀 Universal Scrape Da Web")
st.markdown("---")

# Sidebar components
with st.sidebar:
    st.title("Scraper Settings")
    
    if scraper_imported:
        st.success("Custom scraper module (scrapedaweb4_Mac) loaded successfully")
        if hasattr(scraper, 'pricing') and hasattr(scraper, 'model_used'):
            model_options = list(scraper.pricing.keys())
            default_index = model_options.index(scraper.model_used) if scraper.model_used in model_options else 0
            model_selection = st.selectbox("Select Model", options=model_options, index=default_index)
        else:
            st.warning("Custom scraper module missing required attributes. Using default values.")
            model_options = ["Default Model"]
            model_selection = st.selectbox("Select Model", options=model_options)
    else:
        st.error(f"Failed to import custom scraper module (scrapedaweb4_Mac): {import_error}")
        model_selection = "Default Model"

    url_input = st.text_input("Enter URL to Scrape", placeholder="https://example.com")

    tags = st_tags_sidebar(
        label='Enter Fields to Extract:',
        text='Press enter to add a field',
        value=[],
        suggestions=['title', 'price', 'description', 'image_url'],
        maxtags=-1,
        key='tags_input'
    )

    st.markdown("---")
    
    if st.button("Start Scraping", key="scrape_button"):
        if not url_input or not tags:
            st.error("Please enter a URL and at least one field to extract.")
        elif not scraper_imported:
            st.error("Custom scraper module is not available. Please check your installation.")
        else:
            st.session_state.start_scraping = True

# Initialize session state
if 'scrape_results' not in st.session_state:
    st.session_state.scrape_results = None
if 'start_scraping' not in st.session_state:
    st.session_state.start_scraping = False

@lru_cache(maxsize=32)
async def fetch_html_async(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

def perform_scrape(progress_bar):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    progress_bar.progress(10)
    raw_html = asyncio.run(fetch_html_async(url_input))
    progress_bar.progress(30)
    
    if hasattr(scraper, 'html_to_markdown_with_readability'):
        markdown = scraper.html_to_markdown_with_readability(raw_html)
    else:
        h = html2text.HTML2Text()
        h.ignore_links = False
        markdown = h.handle(raw_html)
    progress_bar.progress(50)
    
    save_raw_data = getattr(scraper, 'save_raw_data', lambda md, ts: f"raw_data_{ts}.md")
    create_dynamic_listing_model = getattr(scraper, 'create_dynamic_listing_model', lambda fields: None)
    create_listings_container_model = getattr(scraper, 'create_listings_container_model', lambda model: None)
    format_data = getattr(scraper, 'format_data', lambda md, container: {"data": md})
    save_formatted_data = getattr(scraper, 'save_formatted_data', lambda data, ts: pd.DataFrame({"data": [data]}))
    calculate_price = getattr(scraper, 'calculate_price', lambda md, text, model: (0, 0, 0))

    raw_data_path = save_raw_data(markdown, timestamp)
    progress_bar.progress(60)
    DynamicListingModel = create_dynamic_listing_model(tags)
    DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
    progress_bar.progress(70)
    formatted_data = format_data(markdown, DynamicListingsContainer)
    progress_bar.progress(80)
    df = save_formatted_data(formatted_data, timestamp)
    progress_bar.progress(90)
    
    formatted_data_text = json.dumps(formatted_data) if isinstance(formatted_data, dict) else str(formatted_data)
    input_tokens, output_tokens, total_cost = calculate_price(markdown, formatted_data_text, model=model_selection)
    progress_bar.progress(100)
    
    return {
        'df': df,
        'formatted_data': formatted_data,
        'markdown': markdown,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_cost': total_cost,
        'timestamp': timestamp,
        'raw_data_path': raw_data_path
    }

# Main content area
if st.session_state.start_scraping:
    try:
        with st.spinner('🕷️ Crawling the web... Please wait...'):
            progress_bar = st.progress(0)
            st.session_state.scrape_results = perform_scrape(progress_bar)
        st.success("Scraping completed successfully!")
        st.session_state.start_scraping = False
    except Exception as e:
        st.error(f"An error occurred during scraping: {str(e)}")
        st.exception(e)
        st.session_state.start_scraping = False

# Display results if available
if st.session_state.scrape_results:
    results = st.session_state.scrape_results
    
    st.subheader("📊 Scraped Data")
    st.dataframe(results['df'])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Input Tokens", results['input_tokens'])
    with col2:
        st.metric("Output Tokens", results['output_tokens'])
    with col3:
        st.metric("Total Cost", f"${results['total_cost']:.4f}")

    st.subheader("🔽 Download Options")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.download_button(
            "Download JSON",
            data=json.dumps(results['formatted_data'], indent=4, default=str),
            file_name=f"{results['timestamp']}_data.json",
            mime="application/json"
        )
    
    with col2:
        st.download_button(
            "Download CSV",
            data=results['df'].to_csv(index=False),
            file_name=f"{results['timestamp']}_data.csv",
            mime="text/csv"
        )
    
    with col3:
        st.download_button(
            "Download Markdown",
            data=results['markdown'],
            file_name=f"{results['timestamp']}_data.md",
            mime="text/markdown"
        )

    st.info(f"📁 Raw data saved to: {results['raw_data_path']}")

# Debugging information
with st.expander("🐞 Debugging Information"):
    if scraper_imported:
        st.write("Available attributes in custom scraper module:", dir(scraper))
    else:
        st.error("Custom scraper module not imported")

st.markdown("---")
st.markdown("Made with 🖤 by Your Friendly Neighborhood Code Breaker Data Scraper")

if __name__ == "__main__":
    pass