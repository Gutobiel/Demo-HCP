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
    import platform
    if platform.system() == "Linux":
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-setuid-sandbox")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    chrome_options.add_argument("--window-size=1280,900")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.page_load_strategy = 'eager'  # Não esperar TUDO carregar
    chrome_options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)  # Timeout maior para sites pesados
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

        # Esperar a imagem principal carregar completamente (checar se foi baixada e renderizada)
        try:
            img_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.head img.image")))
            start_time = time.time()
            while time.time() - start_time < 8:
                is_loaded = driver.execute_script(
                    "return arguments[0].complete && typeof arguments[0].naturalWidth != 'undefined' && arguments[0].naturalWidth > 0", 
                    img_el
                )
                if is_loaded:
                    print("[Screenshot] Imagem principal carregada com sucesso!")
                    break
                time.sleep(0.5)
            time.sleep(1)  # Pequena folga para garantir renderização de outros componentes
        except Exception as img_err:
            print(f"[Screenshot] Erro ao aguardar carregamento da imagem: {img_err}")
            time.sleep(3)

        # Salvar na pasta media/screenshots/ do projeto Django
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        screenshot_dir = os.path.join(base_dir, "media", "screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)

        # Gerar nome único para o arquivo
        filename = f"produto_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(screenshot_dir, filename)

        # Ocultar banners de cookies, LGPD ou popups que fiquem sobrepostos no elemento .head
        try:
            driver.execute_script("""
                var selectors = [
                    '.lgpd', '.cookie-consent', '[id*="lgpd"]', '[class*="lgpd"]',
                    'section footer', '.seller-modal', 'div[class*="modal"]',
                    '.cookies', '.cookies-consent', '.privacy-policy'
                ];
                selectors.forEach(function(sel) {
                    document.querySelectorAll(sel).forEach(function(el) {
                        el.style.setProperty('display', 'none', 'important');
                    });
                });
            """)
            time.sleep(0.5)
        except Exception as e_hide:
            print(f"[Screenshot] Erro ao ocultar overlays: {e_hide}")

        # Obter logs do console antes de fechar o driver
        try:
            browser_logs = driver.get_log('browser')
            print("\n========== [Screenshot] CHROME CONSOLE LOGS ==========")
            for entry in browser_logs:
                print(f"[Chrome Console] {entry.get('level')}: {entry.get('message')}")
            print("======================================================\n")

            # Salvar logs em arquivo
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_filepath = os.path.join(base_dir, "chrome_console.log")
            with open(log_filepath, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n--- SUCCESS SCRAPING LOG FOR {link_produto} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
                if browser_logs:
                    for entry in browser_logs:
                        log_file.write(f"[{entry.get('level')}] {entry.get('message')}\n")
                else:
                    log_file.write("No console logs retrieved.\n")
        except Exception as log_err:
            print(f"[Screenshot] Erro ao capturar logs do console: {log_err}")

        # Screenshot apenas do elemento .head
        head_element.screenshot(filepath)
        print(f"Screenshot do produto salvo em: {filepath}")
        return filepath

    except Exception as e:
        print(f"Erro ao fazer screenshot do produto: {e}")
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            log_filepath = os.path.join(base_dir, "chrome_console.log")
            with open(log_filepath, "a", encoding="utf-8") as log_file:
                log_file.write(f"\n--- ERROR SCRAPING LOG FOR {link_produto} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ---\n")
                log_file.write(f"Error: {e}\n")
                if driver:
                    try:
                        browser_logs = driver.get_log('browser')
                        for entry in browser_logs:
                            log_file.write(f"[{entry.get('level')}] {entry.get('message')}\n")
                    except Exception as dev_err:
                        log_file.write(f"Failed to get browser logs: {dev_err}\n")
        except Exception as e_log:
            print(f"[Screenshot] Erro ao gravar logs de erro em arquivo: {e_log}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
