import streamlit as st
from streamlit_tags import st_tags_sidebar
import pandas as pd
import json
from datetime import datetime
import sys
import os
from functools import lru_cache
import asyncio
import aiohttp

# Append the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the entire scraper module
try:
    import scraper
    st.sidebar.success("Scraper module imported successfully")
except ImportError as e:
    st.sidebar.error(f"Failed to import scraper module: {e}")
    scraper = None

# Initialize Streamlit app
st.set_page_config(page_title="Universal Web Scraper", page_icon="🦑")

# Sidebar components
st.sidebar.title("Web Scraper Settings")

# Check if scraper module and necessary attributes exist
if scraper and hasattr(scraper, 'pricing') and hasattr(scraper, 'model_used'):
    model_options = list(scraper.pricing.keys())
    default_index = model_options.index(scraper.model_used) if scraper.model_used in model_options else 0
    model_selection = st.sidebar.selectbox("Select Model", options=model_options, index=default_index)
else:
    st.sidebar.warning("Scraper module missing required attributes. Using default values.")
    model_options = ["Default Model"]
    model_selection = st.sidebar.selectbox("Select Model", options=model_options)

url_input = st.sidebar.text_input("Enter URL")

# Tags input in the sidebar
tags = st_tags_sidebar(
    label='Enter Fields to Extract:',
    text='Press enter to add a tag',
    value=[],
    suggestions=[],
    maxtags=-1,
    key='tags_input'
)

st.sidebar.markdown("---")

# Process tags into a list
fields = tags

# Initialize session state for scraping results
if 'scrape_results' not in st.session_state:
    st.session_state.scrape_results = None

@lru_cache(maxsize=32)
async def fetch_html_async(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

def perform_scrape():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Use asyncio to run the async function
    raw_html = asyncio.run(fetch_html_async(url_input))
    
    if not scraper:
        raise ImportError("Scraper module is not available")

    markdown = scraper.html_to_markdown_with_readability(raw_html)
    raw_data_path = scraper.save_raw_data(markdown, timestamp)
    DynamicListingModel = scraper.create_dynamic_listing_model(fields)
    DynamicListingsContainer = scraper.create_listings_container_model(DynamicListingModel)
    formatted_data = scraper.format_data(markdown, DynamicListingsContainer)
    df = scraper.save_formatted_data(formatted_data, timestamp)
    formatted_data_text = json.dumps(formatted_data.dict())
    input_tokens, output_tokens, total_cost = scraper.calculate_price(markdown, formatted_data_text, model=model_selection)
    
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

# Main app layout
st.title("Universal Scrape Da Web 🦑")

# Handling button press for scraping
if st.sidebar.button("Scrape"):
    if not url_input or not fields:
        st.error("Please enter a URL and select fields to extract before scraping.")
    else:
        try:
            with st.spinner('Please wait... Data is being scraped.'):
                st.session_state.scrape_results = perform_scrape()
        except Exception as e:
            st.error(f"An error occurred during scraping: {str(e)}")
            st.exception(e)

# Display results if available
if st.session_state.scrape_results:
    results = st.session_state.scrape_results
    
    st.write("Scraped Data:", results['df'])
    
    st.sidebar.markdown("## Token Usage")
    st.sidebar.markdown(f"**Input Tokens:** {results['input_tokens']}")
    st.sidebar.markdown(f"**Output Tokens:** {results['output_tokens']}")
    st.sidebar.markdown(f"**Total Cost:** :green[${results['total_cost']:.4f}]")

    # Create columns for download buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.download_button(
            "Download JSON",
            data=json.dumps(results['formatted_data'].dict(), indent=4),
            file_name=f"{results['timestamp']}_data.json"
        )
    
    with col2:
        st.download_button(
            "Download CSV",
            data=results['df'].to_csv(index=False),
            file_name=f"{results['timestamp']}_data.csv"
        )
    
    with col3:
        st.download_button(
            "Download Markdown",
            data=results['markdown'],
            file_name=f"{results['timestamp']}_data.md"
        )

    # Display raw data path
    st.info(f"Raw data saved to: {results['raw_data_path']}")

# Debugging information
st.sidebar.markdown("## Debugging Info")
if scraper:
    st.sidebar.write("Available attributes in scraper module:", dir(scraper))
else:
    st.sidebar.error("Scraper module not imported")

if __name__ == "__main__":
    pass