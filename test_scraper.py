from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import json

options = Options()
options.add_argument("--headless=new")
driver = webdriver.Chrome(options=options)

driver.get("https://www.hcpneus.com.br/busca?q=pneu+aro+14")
time.sleep(5)

items = driver.find_elements(By.CSS_SELECTOR, "li")
results = []
for i, item in enumerate(items):
    content = item.get_attribute('innerHTML')
    if "data-name" in content or "product" in content.lower():
        try:
            a_tag = item.find_element(By.TAG_NAME, "a")
            href = a_tag.get_attribute("href")
            data_name = ""
            try:
                data_name = item.find_element(By.CSS_SELECTOR, "[data-name]").get_attribute("data-name")
            except: pass
            results.append({"index": i, "href": href, "data_name": data_name})
        except:
            pass

print(json.dumps(results[:5], indent=2))
driver.quit()
