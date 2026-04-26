import requests
from bs4 import BeautifulSoup
import json
import logging

logging.basicConfig(level=logging.INFO)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def test_unstop():
    url = "https://unstop.com/api/public/opportunity/search-result?opportunity=competitions&deadline=1&page=1&size=20"
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print("Unstop HTTP", response.status_code)
        if response.status_code == 200:
            print(json.dumps(response.json().get("data", {}).get("data", [])[:2], indent=2))
    except Exception as e:
        print("Error", e)

test_unstop()
