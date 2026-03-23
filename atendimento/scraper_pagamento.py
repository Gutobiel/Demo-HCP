from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os
import uuid
import urllib.request


def finalizar_compra_pix(link_produto, possui_cadastro, dados_checkout, endereco_dados=None):
    """
    Automatiza o checkout completo no site HC Pneus via PIX.
    
    Parâmetros:
        link_produto (str): URL do produto no HC Pneus
        possui_cadastro (str): "sim" ou "nao"
        dados_checkout (dict): Dados do cliente
            - Login: {"email": "...", "senha": "..."}
            - Cadastro: {"nome": "...", "cpf": "...", "nascimento": "...", 
                         "telefone": "...", "sexo": "...", "email": "..."}
        endereco_dados (dict, optional): Dados de endereço
            {"cep": "...", "numero": "...", "complemento": "...", "identificacao": "..."}
    
    Retorna:
        dict com codigo_pix, qr_code_path, numero_pedido, total_compra, senha_gerada
        ou None em caso de erro
    """
    if not link_produto or "hcpneus.com.br" not in link_produto:
        print("Erro: Link do produto inválido.")
        return None

    chrome_options = Options()
    # chrome_options.add_argument("--headless=new")  # Visível para debug
    chrome_options.add_argument("--window-size=1280,900")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.page_load_strategy = 'eager'
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    driver = None
    resultado = None
    senha_gerada = None

    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        wait = WebDriverWait(driver, 20)

        def click_element(el):
            try:
                el.click()
            except:
                driver.execute_script("arguments[0].click();", el)

        # ============================================================
        # ETAPA 1: Abrir a página do produto
        # ============================================================
        print(f"[Pagamento] Abrindo produto: {link_produto}")
        driver.get(link_produto)
        time.sleep(3)

        # Aceitar cookies se aparecer
        try:
            cookie_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/section/footer/div[1]/div/div/button"))
            )
            cookie_btn.click()
            time.sleep(1)
        except:
            pass

        # ============================================================
        # ETAPA 2: Clicar "Adicionar ao carrinho" (abre modal de estoque)
        # ============================================================
        print("[Pagamento] Clicando em 'Adicionar ao carrinho'...")
        try:
            add_cart_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-buy"))
            )
            click_element(add_cart_btn)
            time.sleep(3)
        except Exception as e:
            print(f"[Pagamento] Erro ao clicar Adicionar ao carrinho: {e}")
            return None

        # ============================================================
        # ETAPA 3: Selecionar estado e buscar lojas disponíveis
        # ============================================================
        print("[Pagamento] Selecionando estado no modal de estoque...")
        try:
            # Selecionar "Distrito Federal" no dropdown de estados (padrão HC Pneus)
            from selenium.webdriver.support.ui import Select
            estado_select = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "select[name='select-website']"))
            )
            select_obj = Select(estado_select)
            select_obj.select_by_visible_text("Distrito Federal")
            time.sleep(1)

            # Clicar "Buscar" para carregar as lojas
            buscar_btn = driver.find_element(By.CSS_SELECTOR, "button.btn-search")
            click_element(buscar_btn)
            time.sleep(3)
        except Exception as e:
            print(f"[Pagamento] Erro ao selecionar estado: {e}")

        # ============================================================
        # ETAPA 4: Selecionar loja com maior estoque
        # ============================================================
        print("[Pagamento] Selecionando loja com maior estoque...")
        try:
            # Aguardar os sellers carregarem
            time.sleep(2)
            stock_elements = driver.find_elements(By.CSS_SELECTOR, ".stock-value")
            
            if stock_elements:
                best_stock = -1
                best_label = None
                
                for stock_el in stock_elements:
                    try:
                        stock_val = int(stock_el.text.strip())
                        # Subir até o label pai para clicar
                        label_el = stock_el.find_element(By.XPATH, "./ancestor::label")
                        if stock_val > best_stock:
                            best_stock = stock_val
                            best_label = label_el
                    except:
                        continue
                
                if best_label:
                    seller_name = ""
                    try:
                        seller_name = best_label.find_element(By.CSS_SELECTOR, "strong.title").text.strip()
                    except:
                        pass
                    print(f"[Pagamento] Melhor loja: {seller_name} (estoque: {best_stock})")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", best_label)
                    time.sleep(1)
                    click_element(best_label)
                    time.sleep(2)
            else:
                print("[Pagamento] Nenhum seletor de estoque encontrado, prosseguindo...")
        except Exception as e:
            print(f"[Pagamento] Erro ao selecionar loja: {e}")

        # ============================================================
        # ETAPA 3: Clicar "Comprar"
        # ============================================================
        print("[Pagamento] Clicando em 'Comprar'...")
        try:
            comprar_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.continue"))
            )
            click_element(comprar_btn)
            time.sleep(3)
        except Exception as e:
            print(f"[Pagamento] Erro ao clicar Comprar: {e}")
            return None

        # ============================================================
        # ETAPA 4: Clicar "Finalizar compra" (carrinho)
        # ============================================================
        print("[Pagamento] Clicando em 'Finalizar compra' no carrinho...")
        try:
            finalizar_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.bt-checkout"))
            )
            click_element(finalizar_btn)
            time.sleep(5)
        except Exception as e:
            print(f"[Pagamento] Erro ao finalizar compra no carrinho: {e}")
            return None

        # ============================================================
        # ETAPA 5: Login ou Cadastro
        # ============================================================
        if possui_cadastro == "sim":
            # ------- LOGIN -------
            print("[Pagamento] Fazendo login com credenciais existentes...")
            try:
                email_input = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='Login.Key']"))
                )
                email_input.clear()
                email_input.send_keys(dados_checkout.get("email", ""))
                time.sleep(0.5)

                senha_input = driver.find_element(By.CSS_SELECTOR, "input[name='Login.Password']")
                senha_input.clear()
                senha_input.send_keys(dados_checkout.get("senha", ""))
                time.sleep(0.5)

                entrar_btn = driver.find_element(By.CSS_SELECTOR, "button.signin-submit")
                click_element(entrar_btn)
                time.sleep(5)
                print("[Pagamento] Login realizado!")
            except Exception as e:
                print(f"[Pagamento] Erro no login: {e}")
                return None
        else:
            # ------- NOVO CADASTRO -------
            print("[Pagamento] Iniciando novo cadastro...")
            try:
                # Clicar "Cadastre-se agora"
                cadastro_link = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='#signup']"))
                )
                click_element(cadastro_link)
                time.sleep(3)

                # Gerar senha padrão
                senha_gerada = "HCpneus2024!"

                # Preencher nome
                nome_input = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[data-bind*='FullName']"))
                )
                nome_input.clear()
                nome_input.send_keys(dados_checkout.get("nome", ""))
                time.sleep(0.3)

                # Preencher CPF
                cpf_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.Cpf']")
                cpf_input.clear()
                cpf_input.send_keys(dados_checkout.get("cpf", ""))
                time.sleep(0.3)

                # Preencher data de nascimento
                nasc_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.BirthDate']")
                nasc_input.clear()
                nasc_input.send_keys(dados_checkout.get("nascimento", ""))
                time.sleep(0.3)

                # Preencher telefone
                tel_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.Contact.Phone']")
                tel_input.clear()
                tel_input.send_keys(dados_checkout.get("telefone", ""))
                time.sleep(0.3)

                # Selecionar sexo
                sexo = dados_checkout.get("sexo", "").strip().lower()
                if sexo in ["masculino", "m", "masc"]:
                    sexo_radio = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.Gender'][value='M']")
                else:
                    sexo_radio = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.Gender'][value='F']")
                click_element(sexo_radio)
                time.sleep(0.3)

                # Preencher email
                email_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.Email']")
                email_input.clear()
                email_input.send_keys(dados_checkout.get("email", ""))
                time.sleep(0.3)

                # Preencher senha
                senha_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.Password']")
                senha_input.clear()
                senha_input.send_keys(senha_gerada)
                time.sleep(0.3)

                # Repetir senha
                senha_check = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetCustomer.Password_Check']")
                senha_check.clear()
                senha_check.send_keys(senha_gerada)
                time.sleep(0.3)

                # Clicar "Cadastrar"
                cadastrar_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'].btn-wide.btn-big.base")
                click_element(cadastrar_btn)
                time.sleep(5)
                print(f"[Pagamento] Cadastro realizado! Senha gerada: {senha_gerada}")
            except Exception as e:
                print(f"[Pagamento] Erro no cadastro: {e}")
                return None

        # ============================================================
        # ETAPA 7: Preencher formulário de endereço
        # ============================================================
        print("[Pagamento] Preenchendo endereço...")
        if not endereco_dados:
            endereco_dados = {}
        try:
            # Aguardar o formulário de endereço aparecer
            cep_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='AddOrSetAddress[0].PostalCode']"))
            )
            cep_input.clear()
            cep_input.send_keys(endereco_dados.get("cep", ""))
            time.sleep(1)

            # Número
            num_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetAddress[0].Number']")
            num_input.clear()
            num_input.send_keys(endereco_dados.get("numero", ""))
            time.sleep(0.3)

            # Complemento
            comp_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetAddress[0].AddressNotes']")
            comp_input.clear()
            complemento = endereco_dados.get("complemento", "")
            if complemento:
                comp_input.send_keys(complemento)
            time.sleep(0.3)

            # Identificação (Casa, Apartamento, etc.)
            ident_input = driver.find_element(By.CSS_SELECTOR, "input[name='AddOrSetAddress[0].Name']")
            ident_input.clear()
            ident_input.send_keys(endereco_dados.get("identificacao", "Casa"))
            time.sleep(0.3)

            # Clicar "Enviar para este endereço"
            enviar_btn = driver.find_element(By.CSS_SELECTOR, "button.new-address-submit")
            click_element(enviar_btn)
            time.sleep(3)
            print("[Pagamento] Endereço preenchido e enviado!")
        except Exception as e:
            print(f"[Pagamento] Erro ao preencher endereço: {e}")
            # Tentar fechar o popup se não conseguir preencher
            try:
                close_btn = driver.find_element(By.CSS_SELECTOR, "a.close")
                click_element(close_btn)
                time.sleep(2)
            except:
                pass

        # ============================================================
        # ETAPA 7: Clicar "Continuar → (Pagamento)"
        # ============================================================
        print("[Pagamento] Clicando em 'Continuar → Pagamento'...")
        try:
            continuar_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a.go-payment"))
            )
            click_element(continuar_btn)
            time.sleep(3)
        except Exception as e:
            print(f"[Pagamento] Erro ao clicar Continuar: {e}")
            return None

        # ============================================================
        # ETAPA 8: Selecionar PIX como forma de pagamento
        # ============================================================
        print("[Pagamento] Selecionando PIX...")
        try:
            pix_btn = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='pix']"))
            )
            click_element(pix_btn)
            time.sleep(3)
        except Exception as e:
            print(f"[Pagamento] Erro ao selecionar PIX: {e}")
            return None

        # ============================================================
        # ETAPA 9: Clicar "Finalizar compra" (pagamento final)
        # ============================================================
        print("[Pagamento] Finalizando compra...")
        try:
            finalizar_pagamento = wait.until(
                EC.element_to_be_clickable((By.ID, "form-checkout-submit"))
            )
            click_element(finalizar_pagamento)
            time.sleep(8)  # Aguardar processamento e geração do PIX
        except Exception as e:
            print(f"[Pagamento] Erro ao finalizar pagamento: {e}")
            return None

        # ============================================================
        # ETAPA 10: Extrair dados do PIX
        # ============================================================
        print("[Pagamento] Extraindo dados do PIX...")
        
        codigo_pix = ""
        qr_code_path = None
        numero_pedido = ""
        total_compra = ""

        # Extrair código PIX do botão de copiar
        try:
            copiar_btn = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "button[onclick*='clipboard.writeText']"))
            )
            onclick = copiar_btn.get_attribute("onclick")
            # Extrair o código PIX do onclick: navigator.clipboard.writeText('CODIGO_PIX')
            if "writeText('" in onclick:
                codigo_pix = onclick.split("writeText('")[1].split("')")[0]
            print(f"[Pagamento] Código PIX: {codigo_pix[:30]}...")
        except Exception as e:
            print(f"[Pagamento] Erro ao extrair código PIX: {e}")

        # Extrair/salvar imagem do QR Code
        try:
            qr_img = driver.find_element(By.CSS_SELECTOR, "img.pix-qr-code")
            qr_src = qr_img.get_attribute("src")
            
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            screenshot_dir = os.path.join(base_dir, "media", "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            
            filename = f"qr_pix_{uuid.uuid4().hex[:8]}.png"
            filepath = os.path.join(screenshot_dir, filename)
            
            # Se src é relativa, tornar absoluta
            if qr_src and not qr_src.startswith("http"):
                qr_src = "https://www.hcpneus.com.br" + qr_src
            
            if qr_src:
                # Tentar fazer screenshot do elemento diretamente
                try:
                    qr_img.screenshot(filepath)
                    qr_code_path = filepath
                except:
                    # Fallback: baixar a imagem via URL
                    urllib.request.urlretrieve(qr_src, filepath)
                    qr_code_path = filepath
                print(f"[Pagamento] QR Code salvo: {qr_code_path}")
        except Exception as e:
            print(f"[Pagamento] Erro ao salvar QR Code: {e}")

        # Extrair número do pedido
        try:
            pedido_el = driver.find_element(By.CSS_SELECTOR, "strong[data-bind*='OrderNumber']")
            numero_pedido = pedido_el.text.strip()
            print(f"[Pagamento] Número do pedido: {numero_pedido}")
        except Exception as e:
            print(f"[Pagamento] Erro ao extrair nº pedido: {e}")

        # Extrair total da compra
        try:
            total_el = driver.find_element(By.CSS_SELECTOR, ".total-info strong")
            total_compra = total_el.text.strip()
            print(f"[Pagamento] Total: {total_compra}")
        except Exception as e:
            print(f"[Pagamento] Erro ao extrair total: {e}")

        resultado = {
            "codigo_pix": codigo_pix,
            "qr_code_path": qr_code_path,
            "numero_pedido": numero_pedido,
            "total_compra": total_compra,
            "senha_gerada": senha_gerada,
        }
        print(f"[Pagamento] Checkout concluído com sucesso! Pedido: {numero_pedido}")

    except Exception as e:
        print(f"[Pagamento] Erro geral no checkout: {e}")
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

    return resultado
