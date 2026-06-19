from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(options=options)
url = "https://www.hcpneus.com.br/pneu-165-70r14-85t-goodyear-assurance-maxlife-p988725"

print("Abrindo a página do produto...")
driver.get(url)
time.sleep(5)

print("\n--- Buscando elementos img na div.head ---")
images = driver.find_elements(By.CSS_SELECTOR, "div.head img")
for idx, img in enumerate(images):
    print(f"\n[Imagem {idx}]")
    print(f"Tag HTML: {img.get_attribute('outerHTML')}")
    print(f"src: {img.get_attribute('src')}")
    print(f"data-src: {img.get_attribute('data-src')}")
    print(f"complete: {img.get_attribute('complete')}")
    print(f"naturalWidth: {img.get_attribute('naturalWidth')}")

driver.quit()
