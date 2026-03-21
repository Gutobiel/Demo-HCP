from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import uuid

def screenshot_produto(link_produto, data_name=None):
    """
    Abre a página do produto no Chrome, faz screenshot da seção .head
    (imagem + descrição + preço) e retorna o caminho do arquivo PNG.
    Salva na pasta media/screenshots/ do projeto Django.
    Retorna None se falhar.
    """
    if not link_produto or "hcpneus.com.br" not in link_produto:
        return None
    
    # Rejeitar URLs genéricas (homepage) que vêm do mock data — não são páginas de produto
    if link_produto.rstrip("/") == "https://www.hcpneus.com.br" or link_produto.rstrip("/") == "http://www.hcpneus.com.br":
        print("Screenshot ignorado: URL é a homepage genérica (mock data), não uma página de produto.")
        return None

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1280,900")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.page_load_strategy = 'eager'  # Não esperar TUDO carregar
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)  # Timeout maior para sites pesados
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        driver.get(link_produto)

        wait = WebDriverWait(driver, 15)

        # Aceitar cookies se o banner aparecer
        try:
            cookie_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/section/footer/div[1]/div/div/button"))
            )
            cookie_btn.click()
            time.sleep(1)
        except:
            pass  # Se não aparecer, segue normalmente

        # Navegar para o detalhe clicando no pneu listado, se a URL recaiu em pesquisa
        if data_name and ("busca" in driver.current_url or "catalogsearch" in driver.current_url or "pesquisa" in driver.current_url or driver.current_url.endswith(".com.br/")):
            try:
                item_el = None
                # Method 1: Tentar achar por data-name
                try:
                    xpath_data_name = f"//li[.//div[@data-name='{data_name}']] | //*[@data-name='{data_name}']"
                    item_el = wait.until(EC.presence_of_element_located((By.XPATH, xpath_data_name)))
                except:
                    # Method 2: Backwards Fallback por texto contido
                    dn_lower = data_name.lower()
                    # xpath que ignora o case sensitive
                    xpath_text = f"//li[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{dn_lower}')]"
                    item_el = wait.until(EC.presence_of_element_located((By.XPATH, xpath_text)))

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item_el)
                time.sleep(1)
                
                try:
                    a_tag = item_el.find_element(By.TAG_NAME, "a")
                    href = a_tag.get_attribute("href")
                    if href:
                        driver.get(href)
                except:
                    item_el.click()
                
                # Aguarda carregamento da página de detalhes do produto
                time.sleep(3)
            except Exception as obj_err:
                print(f"Aviso: Fallbacks de detecção falharam para {data_name}: {obj_err}")

        # Localizar a seção .head que contém imagem + descrição + preço
        head_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.head")))

        # Esperar a imagem principal carregar
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.head img.image")))
            time.sleep(2)  # Aguardar renderização completa
        except:
            time.sleep(3)

        # Salvar na pasta media/screenshots/ do projeto Django
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        screenshot_dir = os.path.join(base_dir, "media", "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)

        # Gerar nome único para o arquivo
        filename = f"produto_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(screenshot_dir, filename)

        # Screenshot apenas do elemento .head
        head_element.screenshot(filepath)
        print(f"Screenshot do produto salvo em: {filepath}")
        return filepath

    except Exception as e:
        print(f"Erro ao fazer screenshot do produto: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
