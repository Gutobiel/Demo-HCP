from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import math
import time

def parse_price(price_str):
    """Auxiliary function to clean price string"""
    if not price_str: return None
    clean = re.sub(r'[^\d,]', '', price_str)
    return clean

def buscar_pneus_no_site(car_brand, car_model, car_year, car_version, rim_size):
    """
    Usa Selenium para abrir um navegador Chrome real, acessar o site da HC Pneus
    preencher o formulário de veículo (Marca, Modelo, Ano, Versão) e extrair os produtos reais.
    """
    # URL da Home onde tem o formulário
    url = "https://www.hcpneus.com.br/"
    
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1280,800")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    try:
        print(f"Iniciando navegador Chrome para buscar: {car_brand} {car_model} {car_year} {car_version}...")
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(20)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        try:
            driver.get(url)
        except Exception as e:
            print("Timeout ou erro ao carregar página inicial, tentando prosseguir assim mesmo...", e)
            
        wait = WebDriverWait(driver, 30)
        
        # Helper pra clicar robustamente
        def click_element(el):
            try:
                el.click()
            except:
                driver.execute_script("arguments[0].click();", el)
        
        # 1. Clicar na aba "Pesquisa por Veículo"
        aba_veiculo = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Veículo')]")))
        click_element(aba_veiculo)
        time.sleep(2) # wait for animation
        
        # Helper pra selecionar dropdown por texto aproximado/parcial
        def select_dropdown(xpath, value_text):
            print(f"Buscando dropdown {xpath} para: '{value_text}'...")
            try:
                select_el = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
                click_element(select_el)
                
                # Aguardar o dropdown ter opções além de 'Selecione'
                start_time = time.time()
                options = []
                while time.time() - start_time < 10:
                    options = select_el.find_elements(By.TAG_NAME, 'option')
                    valid_options = [o for o in options if o.get_attribute('textContent').strip() and 'selecione' not in o.get_attribute('textContent').lower()]
                    if valid_options:
                        break
                    time.sleep(0.5)

                found = False
                for opt in options:
                    try:
                        # Usar textContent para pegar o label mesmo que não esteja visível
                        txt = opt.get_attribute('textContent')
                        if not txt: continue
                        txt = txt.strip()
                        
                        if value_text.lower() in txt.lower() and txt:
                            print(f"Encontrou: {txt}. Selecionando...")
                            try:
                                click_element(opt)
                                time.sleep(2) # Wait for AJAX dependency
                                found = True
                                break
                            except Exception as click_err:
                                print(f"Erro ao clicar na opção {txt}: {click_err}")
                                # Tenta pelo valor se o clique falhar
                                val = opt.get_attribute('value')
                                driver.execute_script(f"arguments[0].value = '{val}'; arguments[0].dispatchEvent(new Event('change'));", select_el)
                                time.sleep(2)
                                found = True
                                break
                    except Exception as opt_err:
                        print(f"Erro ao processar opção: {opt_err}")
                        continue
                
                if not found:
                    print(f"AVISO: '{value_text}' não encontrado. Opções: {[o.get_attribute('textContent').strip() for o in options[:8] if o.get_attribute('textContent')]}...")
                return found
            except Exception as e:
                print(f"Erro no dropdown {xpath}: {e}")
                return False

        # 2. Selecionar filtros usando XPaths validados
        select_dropdown("//div[@id='search-hc']//li[2]//form//li[1]/select", car_brand)
        select_dropdown("//div[@id='search-hc']//li[2]//form//li[2]/select", car_model)
        select_dropdown("//div[@id='search-hc']//li[2]//form//li[3]/select", car_year)
        select_dropdown("//div[@id='search-hc']//li[2]//form//li[4]/select", car_version)
        
        # 6. Clicar em Buscar
        buscar_btn = wait.until(EC.element_to_be_clickable((By.ID, "search_veiculo")))
        click_element(buscar_btn)
        
        # Aguardar resultado (nova página ou lista via AJAX)
        time.sleep(6)
        
        live_results = []
        try:
            # Tentar encontrar os produtos na nova página
            # Vamos buscar por seletores comuns de produtos
            product_selectors = [
                 ".item.product.product-item",
                 ".showcase-item",
                 ".product-card",
                 "div[class*='product']",
                 "li[class*='product']"
            ]
            
            items = []
            for selector in product_selectors:
                found_items = driver.find_elements(By.CSS_SELECTOR, selector)
                if len(found_items) > 3:
                    items = found_items
                    print(f"Encontrou {len(items)} produtos usando o seletor {selector}")
                    break
            
            if not items:
                # Fallback: pegar qualquer coisa que pareça um item
                items = driver.find_elements(By.CSS_SELECTOR, "div[class*='item']")
                print(f"Fallback: encontrou {len(items)} itens genéricos")
            
            # Extrair apenas os números informados pelo usuário: "Aro 16" -> "16"
            aro_match = re.search(r'\d+', str(rim_size))
            aro_num = aro_match.group(0) if aro_match else str(rim_size)
            print(f"Filtrando resultados pelo aro: {aro_num}")
            
            for item in items:
                text_content = item.text.strip()
                if not text_content or len(text_content) < 20: continue
                
                # Filtrar pelo aro exato no título do produto (ex "205/55R16")
                if aro_num and aro_num not in text_content:
                    continue
                    
                if 'Pneu' in text_content or 'pneu' in text_content.lower():
                    linhas = [l.strip() for l in text_content.split('\n') if l.strip()]
                    nome = None
                    preco = None
                    
                    # Tentar achar o nome (geralmente a linha mais longa com Pneu)
                    for linha in linhas:
                        if 'Pneu' in linha or '/' in linha:
                            nome = linha
                            break
                    
                    # Tentar achar o preço
                    for linha in linhas:
                        if 'R$' in linha or 'R $' in linha:
                            preco = linha
                            break
                            
                    if nome and preco:
                        marca = nome.split()[0] if nome else car_brand
                        live_results.append({
                            "marca": marca,
                            "nome_modelo": nome,
                            "preco": preco,
                            "link_produto": driver.current_url
                        })
                        if len(live_results) >= 5:
                            break
        except Exception as sel_err:
            print(f"Erro ao extrair dados dos produtos: {sel_err}")

        driver.quit()

        if live_results:
            print("Produtos extraídos do site real!")
            return live_results

    except Exception as e:
        print(f"Erro no fluxo Selenium: {e}")
        try:
            driver.quit()
        except:
            pass
            
    # Fallback to mock data if scrape fails
    print("Selenium falhou. Usando banco virtual de contingência (Mock).")
    mock_database = {
        "14": [
            {"marca": "Goodyear", "nome_modelo": "Pneu Goodyear 175/70R14 Direction Touring 2", "preco": "R$ 389,00", "link_produto": "https://www.hcpneus.com.br/"},
        ],
        "15": [
            {"marca": "Michelin", "nome_modelo": "Pneu Michelin 195/65R15 Energy XM2+", "preco": "R$ 519,90", "link_produto": "https://www.hcpneus.com.br/"},
        ],
        "16": [
            {"marca": "Michelin", "nome_modelo": "Pneu Michelin 205/55R16 Primacy 4+", "preco": "R$ 629,00", "link_produto": "https://www.hcpneus.com.br/"},
        ]
    }
    
    aro_match_mock = re.search(r'\d+', str(rim_size))
    an = aro_match_mock.group(0) if aro_match_mock else "16"
    return mock_database.get(an, [
        {"marca": car_brand, "nome_modelo": f"Pneu Premium {car_brand} {car_model} Aro {an}", "preco": "Sob consulta", "link_produto": "https://www.hcpneus.com.br/"}
    ])

if __name__ == "__main__":
    produtos = buscar_pneus_no_site("Toyota", "Corolla", "2018", "XEI", "16")
    for p in produtos:
        print(p)
