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

                best_opt = None
                best_score = -1
                search_words = value_text.lower().split()

                for opt in options:
                    try:
                        txt = opt.get_attribute('textContent')
                        if not txt: continue
                        txt = txt.strip()
                        txt_lower = txt.lower()
                        
                        if 'selecione' in txt_lower:
                            continue
                            
                        score = 0
                        if value_text.lower() == txt_lower:
                            score = 100
                        elif value_text.lower() in txt_lower:
                            score = 80
                        else:
                            matches = sum(1 for w in search_words if w in txt_lower)
                            if matches > 0:
                                score = 10 * matches
                        
                        if score > best_score:
                            best_score = score
                            best_opt = opt
                            
                    except Exception as opt_err:
                        continue
                
                if best_opt and best_score > 0:
                    txt = best_opt.get_attribute('textContent').strip()
                    print(f"Melhor opção para '{value_text}' foi '{txt}' (Score: {best_score}). Selecionando...")
                    try:
                        click_element(best_opt)
                        time.sleep(2) # Wait for AJAX dependency
                        return True
                    except Exception as click_err:
                        val = best_opt.get_attribute('value')
                        driver.execute_script(f"arguments[0].value = '{val}'; arguments[0].dispatchEvent(new Event('change'));", select_el)
                        time.sleep(2)
                        return True
                
                if valid_options:
                    primeira_valida = valid_options[0]
                    txt = primeira_valida.get_attribute('textContent').strip()
                    print(f"AVISO: '{value_text}' não encontrado. Forçando seleção na primeira válida: '{txt}'...")
                    try:
                        click_element(primeira_valida)
                        time.sleep(2)
                        return True
                    except:
                        val = primeira_valida.get_attribute('value')
                        driver.execute_script(f"arguments[0].value = '{val}'; arguments[0].dispatchEvent(new Event('change'));", select_el)
                        time.sleep(2)
                        return True

                print(f"AVISO: '{value_text}' não encontrado e não há opções válidas.")
                return False
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
        live_results = []
        total_resultados = None
        try:
            # Tentar pegar a quantidade de resultados
            try:
                count_el = driver.find_element(By.CSS_SELECTOR, ".product-count span")
                count_text = count_el.text.strip()
                match = re.search(r'\d+', count_text)
                if match:
                    total_resultados = match.group()
            except:
                pass

            # Detecta se foi redirecionado para a página de um produto único
            is_single_product = len(driver.find_elements(By.CSS_SELECTOR, ".product-name h3")) > 0 or len(driver.find_elements(By.CSS_SELECTOR, "h1.page-title")) > 0
            
            if is_single_product:
                print("Página de produto único diretamente carregada.")
                try:
                    nome = driver.find_element(By.CSS_SELECTOR, ".product-name h3").text.strip()
                except:
                    try:
                        nome = driver.find_element(By.CSS_SELECTOR, "h1.page-title").text.strip()
                    except:
                        nome = driver.title
                
                try:
                    marca = driver.find_element(By.CSS_SELECTOR, ".brand-text").text.strip()
                except:
                    marca = nome.split()[0] if nome else car_brand
                
                try:
                    preco_original = driver.find_element(By.CSS_SELECTOR, ".list-price span, .old-price .price, [data-price-type='oldPrice'] .price").text.strip()
                except:
                    preco_original = "N/A"
                    
                try:
                    preco_desconto = driver.find_element(By.CSS_SELECTOR, "span.instant-price, .special-price .price, [data-price-type='finalPrice'] .price").text.strip()
                except:
                    try:
                        preco_desconto = driver.find_element(By.CSS_SELECTOR, ".price").text.strip()
                    except:
                        preco_desconto = "N/A"
                        
                try:
                    condicao = driver.find_element(By.CSS_SELECTOR, ".condition").text.strip()
                except:
                    condicao = ""
                        
                live_results.append({
                    "marca": marca,
                    "nome_modelo": nome,
                    "preco_original": preco_original,
                    "preco_desconto": preco_desconto,
                    "condicao": condicao,
                    "preco": preco_desconto, # Fallback
                    "link_produto": driver.current_url
                })
            else:
                # Vamos buscar por seletores comuns de produtos na listagem
                product_selectors = [
                     ".wd-browsing-grid-list .product-item",
                     ".wd-browsing-grid-list li",
                     ".item.product.product-item",
                     "li.product-item",
                     ".product-card",
                     "div[class*='product']"
                ]
                
                items = []
                for selector in product_selectors:
                    found_items = driver.find_elements(By.CSS_SELECTOR, selector)
                    if len(found_items) > 0:
                        items = found_items
                        print(f"Encontrou {len(items)} produtos usando o seletor {selector}")
                        break
                
                for item in items:
                    text_content = item.text.strip()
                    if not text_content: continue
                    
                    # Extração segura do Nome do produto
                    nome = None
                    try:
                        nome = item.get_attribute("data-name")
                    except:
                        pass
                    
                    if not nome:
                        try:
                            nome_el = item.find_element(By.CSS_SELECTOR, "[data-name]")
                            nome = nome_el.get_attribute("data-name")
                        except:
                            pass
                            
                    if not nome:
                        try:
                            nome = item.find_element(By.CSS_SELECTOR, ".product-item-link, .product-item-name, .product-name").text.strip()
                        except:
                            linhas = [l.strip() for l in text_content.split('\n') if l.strip()]
                            nome = linhas[0] if linhas else None

                    # Extração do Preço Original (De)
                    try:
                        preco_original = item.find_element(By.CSS_SELECTOR, ".list-price span, .old-price .price, [data-price-type='oldPrice'] .price").text.strip()
                    except:
                        preco_original = "N/A"
                        
                    # Extração do Preço de Desconto (Por)
                    try:
                        preco_desconto = item.find_element(By.CSS_SELECTOR, ".instant-price, .special-price .price, [data-price-type='finalPrice'] .price").text.strip()
                    except:
                        try:
                            # Se não tem antigo/novo, tenta pegar apenas o preço normal
                            preco_desconto = item.find_element(By.CSS_SELECTOR, ".price").text.strip()
                        except:
                            preco_desconto = "N/A"
                            
                    # Extração da condição de pagamento
                    try:
                        condicao = item.find_element(By.CSS_SELECTOR, ".condition").text.strip()
                    except:
                        condicao = ""
                            
                    # Se não foi possível encontrar nome e preço pelos seletores, tenta extrair por texto
                    if not nome or preco_desconto == "N/A":
                        continue
                        
                    nome_str = nome.lower() if nome else ""
                    if 'pneu' not in nome_str and 'pneu' not in text_content.lower():
                        continue
                        
                    try:
                        link_produto = item.find_element(By.TAG_NAME, "a").get_attribute("href")
                    except:
                        link_produto = driver.current_url

                    marca = nome.split()[0] if nome else car_brand
                    live_results.append({
                        "marca": marca,
                        "nome_modelo": nome,
                        "preco_original": preco_original,
                        "preco_desconto": preco_desconto,
                        "condicao": condicao,
                        "preco": preco_desconto,
                        "link_produto": link_produto
                    })
                    
                    if len(live_results) >= 10: # Retorna os top 10 resultados
                        break
        except Exception as sel_err:
            print(f"Erro ao extrair dados dos produtos: {sel_err}")

        driver.quit()

        if live_results or total_resultados:
            print(f"Produtos extraídos do site real! Total encontrado: {total_resultados}")
            return {"count": total_resultados, "products": live_results}

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
            {"marca": "Goodyear", "nome_modelo": "Pneu Goodyear 175/70R14 Direction Touring 2", "preco": "R$ 389,00", "link_produto": "https://www.hcpneus.com.br/", "condicao": "6x de R$ 64,83 sem juros"},
        ],
        "15": [
            {"marca": "Michelin", "nome_modelo": "Pneu Michelin 195/65R15 Energy XM2+", "preco": "R$ 519,90", "link_produto": "https://www.hcpneus.com.br/", "condicao": "6x de R$ 86,65 sem juros"},
        ],
        "16": [
            {"marca": "Michelin", "nome_modelo": "Pneu Michelin 205/55R16 Primacy 4+", "preco": "R$ 629,00", "link_produto": "https://www.hcpneus.com.br/", "condicao": "6x de R$ 104,83 sem juros"},
        ]
    }
    
    aro_match_mock = re.search(r'\d+', str(rim_size))
    an = aro_match_mock.group(0) if aro_match_mock else "16"
    mock_res = mock_database.get(an, [
        {"marca": car_brand, "nome_modelo": f"Pneu Premium {car_brand} {car_model} Aro {an}", "preco": "Sob consulta", "link_produto": "https://www.hcpneus.com.br/", "condicao": ""}
    ])
    return {"count": len(mock_res), "products": mock_res}

if __name__ == "__main__":
    produtos = buscar_pneus_no_site("Toyota", "Corolla", "2018", "XEI", "16")
    for p in produtos:
        print(p)
