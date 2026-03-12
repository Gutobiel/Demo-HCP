import requests
from bs4 import BeautifulSoup
import json

url = "https://www.hcpneus.com.br/pesquisa?t=16"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}
print(f"Buscando {url}...")
response = requests.get(url, headers=headers)
print("Status:", response.status_code)

soup = BeautifulSoup(response.text, 'html.parser')

items = soup.find_all(class_='showcase-item')

if not items:
    items = soup.find_all(class_='product')
if not items:
    # Try generic ones
    items = soup.select('div[class*="product"]')
    
print(f"Achados: {len(items)}")

for i in items[:2]:
    # Dump just the text to see what we have
    print("----- PRODUTO -----")
    print(i.text.strip()[:200])
    
if len(items) == 0:
    print("\n--- HTML Snippet ---\n")
    print(soup.text[:800])
