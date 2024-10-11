import os
import time
import re
import json
from datetime import datetime
from typing import List, Dict, Type

import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field, create_model
import html2text
import tiktoken

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from openai import OpenAI

load_dotenv()

def setup_selenium():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def fetch_html_selenium(url):
    driver = setup_selenium()
    try:
        driver.get(url)
        time.sleep(5)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)
        return driver.page_source
    finally:
        driver.quit()

def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    for element in soup.find_all(['header', 'footer']):
        element.decompose()
    return str(soup)

def html_to_markdown_with_readability(html_content):
    cleaned_html = clean_html(html_content)
    markdown_converter = html2text.HTML2Text()
    markdown_converter.ignore_links = False
    return markdown_converter.handle(cleaned_html)

pricing = {
    "gpt-4o-mini": {
        "input": 0.150 / 1_000_000,
        "output": 0.600 / 1_000_000,
    },
    "gpt-4o-2024-08-06": {
        "input": 2.5 / 1_000_000,
        "output": 10 / 1_000_000,
    },
}

model_used = "gpt-4o-mini"

def save_raw_data(raw_data, timestamp, output_folder='output'):
    os.makedirs(output_folder, exist_ok=True)
    raw_output_path = os.path.join(output_folder, f'rawData_{timestamp}.md')
    with open(raw_output_path, 'w', encoding='utf-8') as f:
        f.write(raw_data)
    return raw_output_path

def create_dynamic_listing_model(field_names: List[str]) -> Type[BaseModel]:
    field_definitions = {field: (str, ...) for field in field_names}
    return create_model('DynamicListingModel', **field_definitions)

def create_listings_container_model(listing_model: Type[BaseModel]) -> Type[BaseModel]:
    return create_model('DynamicListingsContainer', listings=(List[listing_model], ...))

def trim_to_token_limit(text, model, max_tokens=200000):
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(text)
    if len(tokens) > max_tokens:
        return encoder.decode(tokens[:max_tokens])
    return text

def format_data(data, DynamicListingsContainer):
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    system_message = """You are an intelligent text extraction and conversion assistant. Your task is to extract structured information 
                        from the given text and convert it into a pure JSON format. The JSON should contain only the structured data extracted from the text, 
                        with no additional commentary, explanations, or extraneous information. 
                        You could encounter cases where you can't find the data of the fields you have to extract or the data will be in a foreign language.
                        Please process the following text and provide the output in pure JSON format with no words before or after the JSON:"""
    user_message = f"Extract the following information from the provided text:\nPage content:\n\n{data}"
    completion = client.beta.chat.completions.parse(
        model=model_used,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        response_format=DynamicListingsContainer
    )
    return completion.choices[0].message.parsed

def save_formatted_data(formatted_data, timestamp, output_folder='output'):
    os.makedirs(output_folder, exist_ok=True)
    formatted_data_dict = formatted_data.dict() if hasattr(formatted_data, 'dict') else formatted_data
    json_output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.json')
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(formatted_data_dict, f, indent=4)

    if isinstance(formatted_data_dict, dict):
        data_for_df = next(iter(formatted_data_dict.values())) if len(formatted_data_dict) == 1 else formatted_data_dict
    elif isinstance(formatted_data_dict, list):
        data_for_df = formatted_data_dict
    else:
        raise ValueError("Formatted data is neither a dictionary nor a list, cannot convert to DataFrame")

    try:
        df = pd.DataFrame(data_for_df)
        excel_output_path = os.path.join(output_folder, f'sorted_data_{timestamp}.xlsx')
        df.to_excel(excel_output_path, index=False)
        return df
    except Exception as e:
        print(f"Error creating DataFrame or saving Excel: {str(e)}")
        return None

def calculate_price(input_text, output_text, model=model_used):
    encoder = tiktoken.encoding_for_model(model)
    input_token_count = len(encoder.encode(input_text))
    output_token_count = len(encoder.encode(output_text))
    input_cost = input_token_count * pricing[model]["input"]
    output_cost = output_token_count * pricing[model]["output"]
    total_cost = input_cost + output_cost
    return input_token_count, output_token_count, total_cost

def suggest_fields_to_scrape(markdown_content):
    patterns = {
        'Name': r'\b[A-Z][a-z]+ (?:[A-Z][a-z]+ )?[A-Z][a-z]+\b',
        'Product': r'\b[A-Z][a-z]+(?: [A-Z][a-z]+)* (?:Model|Version|Edition|Series)\b|\b[A-Z0-9]+-[A-Z0-9]+\b',
        'Price': r'\$\d+(?:\.\d{2})?|\d+(?:\.\d{2})? USD',
        'Email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'Phone': r'\b(?:\+\d{1,2}\s?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b',
        'Address': r'\d+\s+(?:North|South|East|West|NW|SW|NE|SE)?\s*[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Plaza|Pl|Terrace|Ter|Circle|Cir)\.?(?:,\s*[A-Z][a-z]+(?:,\s*[A-Z]{2})?)?\s*\d{5}(?:-\d{4})?'
    }
    
    suggested_fields = []
    for field, pattern in patterns.items():
        if re.search(pattern, markdown_content):
            suggested_fields.append(field)
    
    return suggested_fields