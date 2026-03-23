import os
import json
from typing import Dict, TypedDict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from .scraper_search import buscar_pneus_no_site
from .scraper_screenshot import screenshot_produto
from .scraper_pagamento import finalizar_compra_pix
from .knowledge_base import buscar_conhecimento

# Define the state schema
class AgentState(TypedDict):
    messages: list
    is_buying_intent: bool # True se o usuário demonstrou interesse em pesquisar/cotar pneus
    car_marca: str
    car_modelo: str
    car_ano: str
    car_versao: str
    aro: str
    catalog_results: dict
    recommendation_given: bool
    dados_confirmados: bool
    pending_images: list  # Lista de imagens pendentes para envio [{"path": ..., "caption": ...}]
    produto_escolhido_idx: int  # Índice do produto escolhido pelo cliente (Fluxo 2)
    # === Checkout / Pagamento ===
    checkout_iniciado: bool       # Fluxo de pagamento começou
    possui_cadastro: str          # "sim", "nao", ou "" (não perguntou ainda)
    login_email: str
    login_senha: str
    cadastro_nome: str
    cadastro_cpf: str
    cadastro_nascimento: str
    cadastro_telefone: str
    cadastro_sexo: str
    cadastro_email: str
    dados_checkout_confirmados: bool
    # === Endereço ===
    endereco_cep: str
    endereco_numero: str
    endereco_complemento: str
    endereco_identificacao: str   # Casa, Apt, Escritório, etc.
    endereco_confirmado: bool
    pix_confirmado: bool          # Cliente aceitou pagar via PIX
    pix_codigo: str               # Código PIX copiável
    pix_qr_path: str              # Caminho da imagem QR code
    pix_numero_pedido: str        # Número do pedido HC
    pix_total: str                # Total da compra
    senha_gerada: str             # Senha gerada para novo cadastro


def _build_conversation_context(state: AgentState, max_messages: int = 10) -> str:
    """Monta o contexto da conversa recente (últimas N mensagens) para o LLM entender o fluxo."""
    msgs = state.get("messages", [])
    recent = msgs[-max_messages:] if len(msgs) > max_messages else msgs
    lines = []
    for m in recent:
        if isinstance(m, HumanMessage):
            lines.append(f"Cliente: {m.content}")
        elif isinstance(m, AIMessage):
            lines.append(f"Consultor: {m.content[:200]}")  # Truncar respostas longas
    return "\n".join(lines)


def _is_first_interaction(state: AgentState) -> bool:
    """Verifica se é a primeira interação (nenhuma resposta do agente ainda)."""
    ai_msgs = [m for m in state.get("messages", []) if isinstance(m, AIMessage)]
    return len(ai_msgs) == 0


def parse_intent_and_extract(state: AgentState):
    """Uses LLM to evaluate the latest user message and extract required info."""
    
    # Se o fluxo de checkout já começou, delegar ao parser de checkout
    if state.get("checkout_iniciado"):
        return parse_checkout_intent(state)
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    user_msg = state["messages"][-1].content if state["messages"] else ""

    # Verificar se o cliente está confirmando os dados do veículo
    
    # Se todos os campos estão preenchidos e o cliente confirmou
    all_filled = all([
        state.get("car_marca"),
        state.get("car_modelo"),
        state.get("car_ano"),
        state.get("car_versao"),
        state.get("aro")
    ])
    
    if all_filled and not state.get("dados_confirmados"):
        conversa = _build_conversation_context(state, max_messages=4)
        intencao = _llm_detect_intent(
            user_msg, conversa,
            opcoes='"confirmar" = o cliente confirma que os dados do veículo estão corretos\n"corrigir" = o cliente quer corrigir algum dado do veículo\n"outro" = não é possível determinar ou o cliente está falando sobre outra coisa',
            contexto="O consultor mostrou os dados do veículo (marca, modelo, ano, versão, aro) e pediu confirmação ao cliente antes de buscar pneus."
        )
        if intencao == "confirmar":
            state["dados_confirmados"] = True
            return state

    # Montar contexto da conversa para o LLM entender respostas curtas como "14" ou "2015"
    conversa_recente = _build_conversation_context(state, max_messages=6)

    prompt = f"""
    Você é um assistente de extração de dados de veículos.
    Analise a CONVERSA RECENTE e a ÚLTIMA MENSAGEM do cliente para extrair informações do veículo.
    
    CONVERSA RECENTE:
    {conversa_recente}
    
    ÚLTIMA MENSAGEM DO CLIENTE: "{user_msg}"
    
    Além dos dados do veículo, determine a INTENÇÃO de compra ('is_buying_intent'):
    - Se o cliente citou dados do carro, perguntou preço, pediu recomendações de pneu, ou usou o funil atual: true
    - Se ele disse apenas "olá", fez uma pergunta genérica não focada em orçamento/compra no momento: false
    - Se no passado ele já estava cotando (estado atual tem dados do carro), mantenha true.
    
    Estado atual:
    - Já estava comprando/cotando? {state.get('is_buying_intent', False)}
    - Marca: {state.get('car_marca') or 'Não informado'}
    - Modelo: {state.get('car_modelo') or 'Não informado'}
    - Ano: {state.get('car_ano') or 'Não informado'}
    - Versão: {state.get('car_versao') or 'Não informado'}
    - Aro: {state.get('aro') or 'Não informado'}
    
    REGRAS:
    1. Se um campo já foi informado antes, MANTENHA o valor anterior.
    2. Extraia TUDO que for possível da mensagem.
    3. Retorne null APENAS para campos que NÃO estão na mensagem E que NÃO foram informados antes.
    
    RESPONDA SOMENTE O JSON, sem texto adicional:
    {{
        "is_buying_intent": true ou false,
        "car_marca": "valor ou null",
        "car_modelo": "valor ou null",
        "car_ano": "valor ou null",
        "car_versao": "valor ou null",
        "aro": "valor ou null"
    }}
    """

    response = llm.invoke(
        [SystemMessage(content=prompt), HumanMessage(content=user_msg)]
    )

    try:
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content
            content = content.rsplit("```", 1)[0] if "```" in content else content
            content = content.strip()
        
        extracted = json.loads(content)

        # Atualiza a intenção de compra
        state["is_buying_intent"] = extracted.get("is_buying_intent", state.get("is_buying_intent", False))

        for key in ["car_marca", "car_modelo", "car_ano", "car_versao", "aro"]:
            value = extracted.get(key)
            if value and str(value).lower() not in ("null", "none", "não informado"):
                state[key] = str(value)
                state["is_buying_intent"] = True # Se passou dados de carro, a intenção vira True.

    except Exception as e:
        print(f"Erro no parse de intenção: {e}")
        print(f"Resposta do LLM: {response.content}")

    return state


def router_node(state: AgentState):
    """Decides what the agent should do next based on missing info."""
    
    # === CHECKOUT FLOW ===
    if state.get("checkout_iniciado"):
        # Se já confirmou PIX, executar scraper
        if state.get("pix_confirmado"):
            return "process_pix_payment"
        # Se já confirmou endereço, ir para pagamento PIX
        if state.get("endereco_confirmado"):
            return "process_pix_payment"
        # Se já confirmou dados pessoais, coletar endereço
        if state.get("dados_checkout_confirmados"):
            missing_addr = not all([
                state.get("endereco_cep"),
                state.get("endereco_numero"),
                state.get("endereco_identificacao"),
            ])
            if missing_addr:
                return "collect_address_data"
            else:
                return "confirm_address_data"
        # Se já confirmou dados de checkout (antigo), ir para pagamento
        if state.get("dados_checkout_confirmados") and not state.get("endereco_confirmado"):
            # placeholder — não deveria chegar aqui, o bloco acima já trata
            pass
        # Se ainda não perguntou se tem cadastro
        if not state.get("possui_cadastro"):
            # Acabou de ativar checkout — nesta mesma rodada, não precisa parsear
            # Na próxima rodada (nova mensagem do user), parse_intent vai cair aqui de novo
            return "ask_cadastro_ou_login"
        # Se tem cadastro mas falta coletar login
        if state.get("possui_cadastro") == "sim":
            if not state.get("login_email") or not state.get("login_senha"):
                return "collect_checkout_data"
            else:
                return "confirm_checkout_data"
        # Se não tem cadastro, coletar dados
        if state.get("possui_cadastro") == "nao":
            missing = not all([
                state.get("cadastro_nome"),
                state.get("cadastro_cpf"),
                state.get("cadastro_nascimento"),
                state.get("cadastro_telefone"),
                state.get("cadastro_sexo"),
                state.get("cadastro_email"),
            ])
            if missing:
                return "collect_checkout_data"
            else:
                return "confirm_checkout_data"
    
    # === FUNIL ORIGINAL ===
    if state.get("dados_confirmados") and not state.get("recommendation_given"):
        return "consult_catalog"
        
    if state.get("recommendation_given"):
        return "general_chat"
        
    if not state.get("is_buying_intent"):
        return "general_chat"
    
    # Se está no funil de vendas, validar os campos faltantes
    if not state.get("car_marca") or not state.get("car_modelo") or not state.get("car_ano") or not state.get("car_versao") or not state.get("aro"):
        return "ask_missing_info"
    
    if not state.get("dados_confirmados"):
        return "confirm_data"
        
    return END


def confirm_data(state: AgentState):
    """Apresenta os dados coletados e pede confirmação ao cliente."""
    marca = state.get("car_marca", "")
    modelo = state.get("car_modelo", "")
    ano = state.get("car_ano", "")
    versao = state.get("car_versao", "")
    aro = state.get("aro", "")

    msg = (
        f"Perfeito, peguei as especificações! Só para confirmar, vamos de **{marca} {modelo} {ano} {versao} (Aro {aro})**?\n\n"
        f"Se estiver correto, é só confirmar que eu já busco as opções pra você!"
    )
    state["messages"].append(AIMessage(content=msg))
    return state


def generate_consultative_question(state: AgentState, question_type: str):
    """Gera uma pergunta consultiva usando o LLM e a base de conhecimento."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    # Mapa de tipos para português
    tipo_map = {
        "brand": "Marca do veículo",
        "model": "Modelo do veículo",
        "year": "Ano do veículo",
        "version": "Versão do veículo",
        "rim": "Aro do pneu"
    }
    tipo_label = tipo_map.get(question_type, question_type)
    
    # Verificar se é a primeira interação
    is_first = _is_first_interaction(state)
    
    # Buscar conhecimento relevante na base de dados
    user_msg = state["messages"][-1].content if state["messages"] else "Olá"
    conhecimento = buscar_conhecimento(user_msg)

    # Montar contexto do que já sabemos
    dados_coletados = []
    if state.get("car_marca"):
        dados_coletados.append(f"Marca: {state['car_marca']}")
    if state.get("car_modelo"):
        dados_coletados.append(f"Modelo: {state['car_modelo']}")
    if state.get("car_ano"):
        dados_coletados.append(f"Ano: {state['car_ano']}")
    if state.get("car_versao"):
        dados_coletados.append(f"Versão: {state['car_versao']}")
    if state.get("aro"):
        dados_coletados.append(f"Aro: {state['aro']}")

    dados_str = ", ".join(dados_coletados) if dados_coletados else "Nenhum dado coletado ainda"

    # Decidir sobre saudação
    if is_first:
        saudacao_instrucao = "Esta é a PRIMEIRA mensagem. Comece com: 'Olá! Seja muito bem-vindo à HC Pneus! Sou seu consultor virtual e estou aqui para ajudá-lo.'"
    else:
        saudacao_instrucao = "NÃO repita a saudação 'Olá! Seja muito bem-vindo'. Vá direto ao ponto de forma cordial."

    # Contexto da conversa
    conversa = _build_conversation_context(state, max_messages=4)

    sys_prompt = f"""
    Você é o Consultor Técnico da HC Pneus.
    Sua missão é pedir ao cliente a informação: {tipo_label}.
    
    {saudacao_instrucao}
    
    CONHECIMENTO TÉCNICO DISPONÍVEL:
    {conhecimento if conhecimento else '(Sem informações técnicas relevantes)'}

    INSTRUÇÕES:
    - {saudacao_instrucao}
    - Seja conversacional, natural, direito ao ponto e aja como um vendedor humano experiente.
    - NUNCA repita o que o cliente acabou de escrever, apenas dê sequência na conversa lendo a "CONVERSA ATÉ AGORA".
    - Se o cliente já passou os dados de uma vez, avance as perguntas sem ficar repetindo os itens individualmente.
    - Se o cliente perguntar algo técnico, responda usando o CONHECIMENTO TÉCNICO de forma bem resumida.
    - Já sabemos do veículo: {dados_str}
    
    CONVERSA ATÉ AGORA:
    {conversa}
    
    Gere apenas a resposta para o chat, pedindo a informação que falta ({tipo_label}).
    """
    
    response = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    return response.content

def ask_missing_info(state: AgentState):
    """Descobre qual info está faltando e faz a pergunta correta usando a IA."""
    falta_tipo = None
    if not state.get("car_marca"):
        falta_tipo = "brand"
    elif not state.get("car_modelo"):
        falta_tipo = "model"
    elif not state.get("car_ano"):
        falta_tipo = "year"
    elif not state.get("car_versao"):
        falta_tipo = "version"
    elif not state.get("aro"):
        falta_tipo = "rim"
        
    if falta_tipo:
        res = generate_consultative_question(state, falta_tipo)
        state["messages"].append(AIMessage(content=res))
    return state

def _detect_product_choice(user_msg: str, products: list) -> int:
    """
    Detecta se o cliente escolheu um produto específico.
    Retorna o índice (0-based) do produto escolhido, ou -1 se não detectou.
    """
    msg_lower = user_msg.strip().lower()
    
    import re
    # 1. Padrões claros: "opcao 6", "modelo 2", "produto 1", "item 3"
    match = re.search(r'(?:op[cç][aã]o|modelo|produto|item|pneu)\s*(\d+)', msg_lower)
    if match:
        idx = int(match.group(1)) - 1
        if 0 <= idx < len(products):
            return idx
            
    # 2. Número solto (ex: "3", "3.", "eu quero o 3")
    # Usa \b para não pegar o 1 de "175/70"
    match_num = re.search(r'\b(\d+)\b', msg_lower)
    if match_num:
        idx = int(match_num.group(1)) - 1
        # Cuidado para não confundir o número do aro ("aro 14") com a opção "14"
        if 0 <= idx < len(products) and not re.search(r'(?:aro|r)\s*\d+', msg_lower):
            return idx
            
    # 3. Textos ordinais ("primeiro", "segundo")
    ordinais = {"primeir": 0, "segund": 1, "terceir": 2, "quart": 3, "quint": 4, 
                "sext": 5, "setim": 6, "sétim": 6, "oitav": 7, "non": 8, "decim": 9, "décim": 9}
    for word, idx in ordinais.items():
        if word in msg_lower and idx < len(products):
            return idx
    
    # 4. Confirmação genérica para quando há apenas 1 produto — usar LLM
    if len(products) == 1:
        conversa = ""
        intencao = _llm_detect_intent(
            user_msg, conversa,
            opcoes='"confirmar" = o cliente confirma interesse no produto apresentado\n"outro" = o cliente NÃO está confirmando',
            contexto="O consultor apresentou UM único modelo de pneu e perguntou se o cliente deseja esse modelo."
        )
        if intencao == "confirmar":
            return 0
            
    return -1


def general_chat(state: AgentState):
    """Bate papo livre e responde a dúvidas, terminando com um gancho sutil para pneus e fechamento de vendas se produtos foram recomendados."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    user_msg = state["messages"][-1].content if state["messages"] else "Olá"
    conhecimento = buscar_conhecimento(user_msg)
    conversa = _build_conversation_context(state, max_messages=4)
    is_first = _is_first_interaction(state)
    
    saudacao = "Se for a primeira mensagem, dê boas vindas calorosas à HC Pneus (só use se não tiver dado boas vindas antes)." if is_first else "Não fique repetindo saudações e seja fluído."

    contexto_recomendacao = ""
    objetivos_finais = ""
    produtos_apresentados = ""
    
    if state.get("recommendation_given"):
        results_dict = state.get("catalog_results", {})
        products = results_dict.get("products", []) if isinstance(results_dict, dict) else results_dict
        
        # === FLUXO 1 E 2: Lógica de Conversão (Detecção de escolha e confirmação) ===
        already_chosen_idx = state.get("produto_escolhido_idx", -1)
        detected_idx = _detect_product_choice(user_msg, products) if products else -1
        
        current_chosen_idx = already_chosen_idx
        is_final_confirmation = False
        just_chose_now = False
        
        if products:
            if len(products) == 1:
                # Fluxo 1: Se detectou interesse, já é a confirmação final direto (o robô já mandou a imagem antes)
                if detected_idx == 0:
                    is_final_confirmation = True
                    current_chosen_idx = 0
            else:
                # Fluxo 2: Requer 2 passos (escolher modelo -> confirmar foto)
                if already_chosen_idx >= 0:
                    user_lower = user_msg.strip().lower()
                    
                    if detected_idx >= 0 and detected_idx != already_chosen_idx:
                        # Mudou de ideia e escolheu outro modelo
                        just_chose_now = True
                        current_chosen_idx = detected_idx
                    else:
                        # Verificar se está confirmando a foto enviada — usar LLM
                        conversa_ctx = _build_conversation_context(state, max_messages=4)
                        intencao_foto = _llm_detect_intent(
                            user_msg, conversa_ctx,
                            opcoes='"confirmar" = o cliente confirma que quer o pneu da foto\n"outro" = o cliente NÃO está confirmando ou quer outra coisa',
                            contexto="O consultor enviou a foto de um pneu específico e perguntou se é esse que o cliente deseja."
                        )
                        if intencao_foto == "confirmar" or detected_idx == already_chosen_idx:
                            # Confirmou explicitamente a foto enviada no turno anterior
                            is_final_confirmation = True
                elif detected_idx >= 0:
                    # Acabou de escolher um modelo pela primeira vez
                    just_chose_now = True
                    current_chosen_idx = detected_idx

        # Atualiza o estado com a escolha atual
        if current_chosen_idx >= 0:
            state["produto_escolhido_idx"] = current_chosen_idx

        produtos_apresentados = ""
        objetivos_extras = ""
        
        if products:
            produtos_apresentados = "\nPRODUTOS APRESENTADOS RECENTEMENTE E SEUS LINKS NO SISTEMA (MEMÓRIA DA IA):\n"
            for i, p in enumerate(products, 1):
                produtos_apresentados += f"Modelo {i}: {p.get('nome_modelo')} | Preço: {p.get('preco_desconto', p.get('preco'))} | Link: {p.get('link_produto')}\n"
                
            if is_final_confirmation:
                # Ativar fluxo de checkout em vez de enviar link
                state["checkout_iniciado"] = True
                objetivos_extras = """
                ATENÇÃO PARA FLUXO DE COMPRA:
                O cliente ACABOU DE CONFIRMAR a compra do modelo selecionado.
                SUA MISSÃO AGORA É:
                - Diga exatamente: "Que ótimo! Para prosseguir para o pagamento preciso de algumas informações.\nVocê já possui cadastro em nosso site?"
                - NÃO faça mais perguntas técnicas sobre pneus.
                - NÃO envie link de compra.
                - Apenas pergunte se tem cadastro no site.
                """
            elif just_chose_now:
                objetivos_extras = """
                ATENÇÃO: O cliente acabou de escolher um modelo de pneu.
                O SUA RESPOSTA EM TEXTO SERÁ USADA COMO A LEGENDA ÚNICA DA FOTO do pneu escolhido (ou seja, apenas uma mensagem vai ser enviada).
                Você deve confirmar a escolha e pedir que ele valide a imagem antes de gerar o link.
                Exemplo: "Ótima escolha! Esse modelo aqui da foto, certo? Posso enviar o link de pagamento? 😊"
                NÃO ENVIE O LINK DE COMPRA AINDA.
                """
            else:
                objetivos_extras = "ATENÇÃO: O cliente ainda não tomou a decisão final de compra. Esclareça dúvidas, compare opções se necessário, e direcione a escolha."

        contexto_recomendacao = f"Atenção: Você JÁ apresentou opções de pneus para o cliente em mensagens passadas. {objetivos_extras}"
        objetivos_finais = "Esclareça as dúvidas de orçamento/produtos e mantenha o tom amigável."
        
        # Fazer screenshot do produto escolhido APENAS se houver mais de 1 produto (Fluxo 2) e acabou de escolher
        if just_chose_now and current_chosen_idx >= 0 and current_chosen_idx < len(products):
            chosen_product = products[current_chosen_idx]
            link = chosen_product.get("link_produto", "")
            if len(products) > 1 and link and "hcpneus.com.br" in link:
                # Usa a search_url para manter a sessão correta (veículo persistido por cookie/sessão) e clica via scraper
                search_url = link
                if isinstance(results_dict, dict) and results_dict.get("search_url"):
                    search_url = results_dict.get("search_url")
                
                print(f"Fluxo 2: Cliente escolheu modelo {current_chosen_idx + 1}. Abrindo search_url: {search_url} para foto de: {chosen_product.get('data_name')}")
                screenshot_path = screenshot_produto(search_url, chosen_product.get("data_name"))
                if screenshot_path:
                    if not state.get("pending_images"):
                        state["pending_images"] = []
                    state["pending_images"].append({
                        "path": screenshot_path,
                        "caption": ""  # Vazio para herdar do AI text
                    })
    else:
        contexto_recomendacao = "Cenário: O cliente está apenas conversando ou tirando dúvidas iniciais, sem focar ativamente na cotação de pneus."
        objetivos_finais = "Termine SEMPRE com um leve incentivo perguntando se ele gostaria de pesquisar pneus."

    sys_prompt = f"""
    Você é o Consultor Técnico da HC Pneus.
    {contexto_recomendacao}

    {saudacao}

    CONHECIMENTO DA BASE:
    {conhecimento if conhecimento else '(Sem informações diretas da base de dados, mas você tem muita bagagem do mercado)'}

    {produtos_apresentados}

    CONVERSA RECENTE:
    {conversa}

    OBJETIVOS:
    1. Responda diretamente ao cliente com simpatia.
    2. Se ele fez uma pergunta, responda usando seu conhecimento ou o histórico.
    3. {objetivos_finais}
    4. NUNCA diga 'Cliente: ....' na sua resposta nem repita textos passados do cliente. Use listagens ou negritos (<b> ou **) para formatações visuais se desejar enriquecer sua resposta.
    """
    
    response = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    state["messages"].append(AIMessage(content=response.content))
    return state


def consult_catalog(state: AgentState):
    print("Consultando site com:", state["car_marca"], state["car_modelo"], state["car_ano"], state["car_versao"], state["aro"])
    results = buscar_pneus_no_site(
        state["car_marca"], state["car_modelo"], state["car_ano"], state["car_versao"], state["aro"]
    )
    state["catalog_results"] = results
    return state

def recommend_tires(state: AgentState):
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    results_dict = state.get("catalog_results", {})
    if isinstance(results_dict, list):
        products = results_dict
        count = str(len(products))
    else:
        products = results_dict.get("products", [])
        count = results_dict.get("count")

    car_modelo = state.get("car_modelo", "")
    aro = state.get("aro", "")

    if not products:
        msg = f"Infelizmente não encontrei pneus aro {aro} para o {car_modelo} no momento em nosso site. Posso ajudar com mais alguma coisa?"
    else:
        products_text = ""
        count_str = f"Encontramos {count} produtos disponíveis.\n\n" if count else ""
        for i, p in enumerate(products):
            preco_vista = p.get('preco_desconto', p.get('preco', ''))
            preco_orig = p.get('preco_original', '')
            condicao = p.get('condicao', '')
            
            if preco_orig and preco_orig != "N/A":
                texto_preco = f"De: <s>{preco_orig}</s> | Por: **{preco_vista} à vista**" 
            else:
                texto_preco = f"Por: **{preco_vista} à vista**"
                
            if condicao:
                texto_preco += f" ou {condicao}"
                
            if len(products) == 1:
                products_text += f"{p['nome_modelo']} | {texto_preco}"
            else:
                products_text += f"\n- Modelo {i+1}: {p['nome_modelo']} | {texto_preco}"

        if len(products) == 1:
            sys_prompt = f"""
            Você é um vendedor especialista da HC Pneus.
            O cliente possui um {car_modelo}.
            Você encontrou APENAS ESTA OPÇÃO de pneu no estoque:
            {products_text}
            
            Sua tarefa:
            - Apresente a opção EXATAMENTE com este padrão de frase, sem floreios extras: "Encontrei este modelo disponível para o seu {car_modelo}: [DESCRIÇÃO DO PNEU E PREÇO]. É isso mesmo que você deseja?"
            - Não informe que você "guardou os detalhes".
            - Não liste como "Modelo 1".
            - NÃO ENVIE O LINK DE COMPRA NESSA RESPOSTA.
            """
            
            # === FLUXO 1: Produto único - Usar screenshot já capturado pelo scraper ===
            screenshot_path = products[0].get("screenshot_path")
            if not screenshot_path:
                # Fallback: tentar capturar se o scraper não conseguiu
                link = products[0].get("link_produto", "")
                if link and "hcpneus.com.br" in link:
                    print(f"Fluxo 1: Screenshot não veio do scraper. Tentando captura avulsa: {link}")
                    screenshot_path = screenshot_produto(link, products[0].get("data_name"))
            
            if screenshot_path:
                print(f"Fluxo 1: Screenshot disponível: {screenshot_path}")
                if not state.get("pending_images"):
                    state["pending_images"] = []
                state["pending_images"].append({
                    "path": screenshot_path,
                    "caption": ""
                })
        else:
            sys_prompt = f"""
            Você é um vendedor especialista e objetivo da HC Pneus.
            O cliente possui um {car_modelo} usando aro {aro}.
            Você consultou o sistema e tem as seguintes opções:
            {count_str}{products_text}
            
            Sua tarefa:
            - Apresente as opções de forma clara, natural e MUITO PROFISSIONAL.
            - SEM GÍRIAS, SEM EXCESSO DE EMOJIS e com TEXTOS CURTOS (vá direto ao ponto).
            - Apresente os preços detalhados.
            - Informe que você guardou todos os detalhes desses modelos.
            - FINALIZAÇÃO OBRIGATÓRIA: Pergunte de forma explícita QUAL MODELO ele deseja confirmar para que você possa enviar o link da compra.
            - NÃO ENVIE O LINK DE COMPRA AQUI. Apenas estimule o cliente a escolher um dos modelos primeiro.
            """
            
        response = llm.invoke([SystemMessage(content=sys_prompt)])
        msg = response.content
        state["recommendation_given"] = True

    state["messages"].append(AIMessage(content=msg))
    return state


def _llm_detect_intent(user_msg: str, conversa: str, opcoes: str, contexto: str) -> str:
    """Usa LLM para detectar a intenção do cliente, tolerante a erros de digitação."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    prompt = f"""
    Você é um analisador de intenção do cliente em um chat de WhatsApp.
    O cliente pode cometer ERROS DE DIGITAÇÃO, usar gírias, abreviações ou escrever de forma informal.
    
    CONTEXTO DA CONVERSA:
    {contexto}
    
    CONVERSA RECENTE:
    {conversa}
    
    MENSAGEM DO CLIENTE: "{user_msg}"
    
    Determine a intenção do cliente entre estas opções:
    {opcoes}
    
    IMPORTANTE:
    - O cliente pode ter digitado errado (ex: "corretp" = "correto", "simmm" = "sim", "nãoo" = "não")
    - Considere o CONTEXTO da conversa para entender a resposta
    - Se o cliente parece estar respondendo à última pergunta do consultor, interprete como resposta a ela
    
    Responda SOMENTE com JSON:
    {{"intencao": "valor"}}
    """
    response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=user_msg)])
    try:
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        return result.get("intencao", "")
    except Exception as e:
        print(f"Erro ao detectar intenção: {e}")
        return ""


def parse_checkout_intent(state: AgentState):
    """Detecta respostas do cliente durante o fluxo de checkout.
    Usa LLM para todas as detecções, tolerando erros de digitação e respostas informais."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    user_msg = state["messages"][-1].content if state["messages"] else ""
    conversa = _build_conversation_context(state, max_messages=6)

    # --- 1. Confirmação de dados de LOGIN ---
    if state.get("login_email") and state.get("login_senha") and not state.get("dados_checkout_confirmados"):
        intencao = _llm_detect_intent(
            user_msg, conversa,
            opcoes='"confirmar" = o cliente confirma que os dados estão corretos\n"corrigir" = o cliente quer corrigir/mudar os dados\n"outro" = não é possível determinar',
            contexto="O consultor mostrou os dados de login (email e senha) e pediu confirmação ao cliente."
        )
        if intencao == "confirmar":
            state["dados_checkout_confirmados"] = True
            return state
        elif intencao == "corrigir":
            state["login_email"] = ""
            state["login_senha"] = ""
            return state
        # Se "outro", continua — o router vai mandá-lo para collect_checkout_data novamente

    # --- 2. Confirmação de dados de CADASTRO ---
    if state.get("possui_cadastro") == "nao":
        all_cadastro_filled = all([
            state.get("cadastro_nome"), state.get("cadastro_cpf"),
            state.get("cadastro_nascimento"), state.get("cadastro_telefone"),
            state.get("cadastro_sexo"), state.get("cadastro_email"),
        ])
        if all_cadastro_filled and not state.get("dados_checkout_confirmados"):
            # Usar LLM para detectar se confirma, corrige inline, ou quer refazer tudo
            llm_correcao = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            dados_atuais = (
                "Nome: " + str(state.get('cadastro_nome', '')) + "\n"
                "CPF: " + str(state.get('cadastro_cpf', '')) + "\n"
                "Nascimento: " + str(state.get('cadastro_nascimento', '')) + "\n"
                "Telefone: " + str(state.get('cadastro_telefone', '')) + "\n"
                "Sexo: " + str(state.get('cadastro_sexo', '')) + "\n"
                "Email: " + str(state.get('cadastro_email', ''))
            )
            prompt_correcao = f"""
            O consultor mostrou os dados de cadastro do cliente e pediu confirmação.
            
            DADOS MOSTRADOS:
            {dados_atuais}
            
            CONVERSA RECENTE:
            {conversa}
            
            MENSAGEM DO CLIENTE: "{user_msg}"
            
            O cliente pode:
            1. CONFIRMAR que está tudo correto (ex: "sim", "correto", "tá certo", "perfeito", mesmo com erros de digitação)
            2. CORRIGIR um campo específico inline (ex: "não, o cpf é 12345678900", "o email tá errado, é outro@email.com")
            3. Pedir para REFAZER todos os dados
            
            IMPORTANTE: O cliente pode cometer ERROS DE DIGITAÇÃO.
            
            Se o cliente está CORRIGINDO inline, identifique QUAL campo e QUAL o novo valor.
            Campos possíveis: cadastro_nome, cadastro_cpf, cadastro_nascimento, cadastro_telefone, cadastro_sexo, cadastro_email
            
            Responda SOMENTE JSON:
            {{
                "acao": "confirmar" ou "corrigir_inline" ou "refazer",
                "campo_corrigido": "nome_do_campo ou null",
                "valor_corrigido": "novo_valor ou null"
            }}
            """
            response_correcao = llm_correcao.invoke([SystemMessage(content=prompt_correcao), HumanMessage(content=user_msg)])
            try:
                content = response_correcao.content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                result = json.loads(content)
                acao = result.get("acao", "")
                
                if acao == "confirmar":
                    state["dados_checkout_confirmados"] = True
                    return state
                elif acao == "corrigir_inline":
                    campo = result.get("campo_corrigido", "")
                    valor = result.get("valor_corrigido", "")
                    if campo and valor and campo in ["cadastro_nome", "cadastro_cpf", "cadastro_nascimento",
                                                      "cadastro_telefone", "cadastro_sexo", "cadastro_email"]:
                        state[campo] = str(valor)
                        # Não limpa os outros campos! Vai direto para confirm_checkout_data de novo
                    return state
                elif acao == "refazer":
                    for k in ["cadastro_nome", "cadastro_cpf", "cadastro_nascimento",
                               "cadastro_telefone", "cadastro_sexo", "cadastro_email"]:
                        state[k] = ""
                    return state
            except Exception as e:
                print(f"Erro ao processar correção: {e}")
            return state

    # --- 3. Confirmação do ENDEREÇO ---
    if state.get("dados_checkout_confirmados") and not state.get("endereco_confirmado"):
        all_addr_filled = all([
            state.get("endereco_cep"),
            state.get("endereco_numero"),
            state.get("endereco_identificacao"),
        ])
        if all_addr_filled:
            intencao = _llm_detect_intent(
                user_msg, conversa,
                opcoes='"confirmar" = o cliente confirma que o endereço está correto\n"corrigir" = o cliente quer corrigir algum dado do endereço\n"outro" = não é possível determinar',
                contexto="O consultor mostrou os dados de endereço (CEP, número, complemento, identificação) e pediu confirmação."
            )
            if intencao == "confirmar":
                state["endereco_confirmado"] = True
                return state
            elif intencao == "corrigir":
                state["endereco_cep"] = ""
                state["endereco_numero"] = ""
                state["endereco_complemento"] = ""
                state["endereco_identificacao"] = ""
                return state

    # --- 4. Confirmação do PIX ---
    if state.get("endereco_confirmado") and not state.get("pix_confirmado"):
        intencao = _llm_detect_intent(
            user_msg, conversa,
            opcoes='"confirmar" = o cliente aceita pagar via PIX\n"recusar" = o cliente não quer PIX ou quer outra forma\n"outro" = não é possível determinar',
            contexto="O consultor informou que o pagamento via WhatsApp é exclusivamente por PIX e perguntou se o cliente deseja prosseguir."
        )
        if intencao == "confirmar":
            state["pix_confirmado"] = True
            return state
        # Se recusar ou outro, o router vai redirecionar para process_pix (que pergunta de novo)

    # --- 4. Detectar SIM/NÃO cadastro ---
    if not state.get("possui_cadastro"):
        intencao = _llm_detect_intent(
            user_msg, conversa,
            opcoes='"sim" = o cliente JÁ possui cadastro no site\n"nao" = o cliente NÃO possui cadastro no site\n"outro" = não é possível determinar',
            contexto="O consultor perguntou se o cliente já possui cadastro no site da HC Pneus."
        )
        if intencao in ["sim", "nao"]:
            state["possui_cadastro"] = intencao
        return state

    # --- 5. Extrair dados de login ou cadastro ---
    if state.get("possui_cadastro") == "sim":
        prompt = f"""
        O cliente está informando seus dados de LOGIN (email e senha).
        Extraia os campos da mensagem.
        
        CONVERSA RECENTE:
        {conversa}
        
        MENSAGEM: "{user_msg}"
        
        Estado atual:
        - Email: {state.get('login_email') or 'Não informado'}
        - Senha: {state.get('login_senha') or 'Não informada'}
        
        REGRAS:
        1. Se o campo já foi informado antes, MANTENHA.
        2. Retorne null para campos não encontrados.
        
        Responda SOMENTE JSON:
        {{"login_email": "valor ou null", "login_senha": "valor ou null"}}
        """
        response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=user_msg)])
        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            extracted = json.loads(content)
            for key in ["login_email", "login_senha"]:
                val = extracted.get(key)
                if val and str(val).lower() not in ("null", "none", "não informado", "não informada"):
                    state[key] = str(val)
        except Exception as e:
            print(f"Erro ao extrair login: {e}")

    elif state.get("possui_cadastro") == "nao":
        prompt = f"""
        O cliente está informando seus dados de CADASTRO para criar conta.
        Extraia os campos da mensagem.
        
        CONVERSA RECENTE:
        {conversa}
        
        MENSAGEM: "{user_msg}"
        
        Estado atual:
        - Nome completo: {state.get('cadastro_nome') or 'Não informado'}
        - CPF: {state.get('cadastro_cpf') or 'Não informado'}
        - Data de nascimento: {state.get('cadastro_nascimento') or 'Não informada'}
        - Telefone: {state.get('cadastro_telefone') or 'Não informado'}
        - Sexo: {state.get('cadastro_sexo') or 'Não informado'}
        - Email: {state.get('cadastro_email') or 'Não informado'}
        
        REGRAS IMPORTANTES:
        1. Se o campo já foi informado antes, MANTENHA o valor anterior.
        2. Retorne null para campos não encontrados na mensagem.
        3. DIFERENCIE CPF de TELEFONE:
           - CPF tem EXATAMENTE 11 dígitos numéricos (ex: 52305373104, 123.456.789-00)
           - TELEFONE tem DDD + número (ex: 61985695745, (61) 98569-5745)
           - Se o cliente enviou DOIS números de 11 dígitos, o que contém padrão de DDD (11, 21, 31, 41, 51, 61, 71, 81, 91...) é mais provável ser TELEFONE
           - O CPF geralmente NÃO começa com DDD comum
        4. NOME: são palavras (letras), não números
        5. EMAIL: contém @ e .com/.br etc.
        6. SEXO: masculino/feminino/outro
        7. DATA DE NASCIMENTO: formato DD/MM/AAAA
        
        Responda SOMENTE JSON:
        {{{{
            "cadastro_nome": "valor ou null",
            "cadastro_cpf": "valor ou null",
            "cadastro_nascimento": "valor ou null",
            "cadastro_telefone": "valor ou null",
            "cadastro_sexo": "valor ou null",
            "cadastro_email": "valor ou null"
        }}}}
        """
        response = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=user_msg)])
        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            extracted = json.loads(content)
            for key in ["cadastro_nome", "cadastro_cpf", "cadastro_nascimento",
                         "cadastro_telefone", "cadastro_sexo", "cadastro_email"]:
                val = extracted.get(key)
                if val and str(val).lower() not in ("null", "none", "não informado", "não informada"):
                    state[key] = str(val)
        except Exception as e:
            print(f"Erro ao extrair cadastro: {e}")

    return state


def ask_cadastro_ou_login(state: AgentState):
    """Pergunta ao cliente se já possui cadastro no site."""
    msg = (
        "Para prosseguir com o pagamento, preciso saber: "
        "você já possui cadastro em nosso site?"
    )
    state["messages"].append(AIMessage(content=msg))
    return state


def collect_checkout_data(state: AgentState):
    """Solicita os dados que faltam para login ou cadastro."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    conversa = _build_conversation_context(state, max_messages=6)

    if state.get("possui_cadastro") == "sim":
        # Coletar email e senha
        faltam = []
        if not state.get("login_email"):
            faltam.append("email")
        if not state.get("login_senha"):
            faltam.append("senha")

        dados_ja = ""
        if state.get("login_email"):
            dados_ja += "- Email: " + state['login_email'] + "\n"
        if state.get("login_senha"):
            dados_ja += "- Senha: (informada)\n"

        dados_ja_section = ("Dados já informados:\n" + dados_ja) if dados_ja else ""

        sys_prompt = f"""
        Você é o Consultor da HC Pneus.
        O cliente JÁ POSSUI cadastro. Você precisa coletar: {', '.join(faltam)}.
        
        {dados_ja_section}
        
        CONVERSA RECENTE:
        {conversa}
        
        INSTRUÇÕES:
        - Peça os dados que faltam de forma clara e objetiva.
        - Diga ao cliente que seus dados estão 100% seguros e nada será vazado.
        - Seja cordial mas direto.
        - NÃO repita dados já informados.
        """
    else:
        # Coletar dados de cadastro
        campos = {
            "cadastro_nome": "Nome completo",
            "cadastro_cpf": "CPF",
            "cadastro_nascimento": "Data de nascimento",
            "cadastro_telefone": "Telefone",
            "cadastro_sexo": "Sexo",
            "cadastro_email": "Email",
        }
        faltam = [label for key, label in campos.items() if not state.get(key)]
        
        dados_ja = ""
        for key, label in campos.items():
            if state.get(key):
                dados_ja += "- " + label + ": " + str(state[key]) + "\n"

        dados_ja_section = ("Dados já informados:\n" + dados_ja) if dados_ja else ""

        sys_prompt = f"""
        Você é o Consultor da HC Pneus.
        O cliente NÃO possui cadastro. Você precisa coletar os seguintes dados para criar a conta: {', '.join(faltam)}.
        
        {dados_ja_section}
        
        CONVERSA RECENTE:
        {conversa}
        
        INSTRUÇÕES:
        - Peça TODOS os dados que faltam de uma só vez.
        - Seja cordial e objetivo.
        - Se o cliente já informou algum dado, NÃO repita. Apenas peça os que faltam.
        """

    user_msg = state["messages"][-1].content if state["messages"] else ""
    response = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    state["messages"].append(AIMessage(content=response.content))
    return state


def confirm_checkout_data(state: AgentState):
    """Mostra os dados coletados e pede confirmação."""
    if state.get("possui_cadastro") == "sim":
        email = state.get("login_email", "")
        # Mascarar a senha parcialmente
        senha_raw = state.get("login_senha", "")
        if len(senha_raw) > 2:
            senha_masked = senha_raw[0] + "*" * (len(senha_raw) - 2) + senha_raw[-1]
        else:
            senha_masked = "***"
        msg = (
            f"Perfeito! Seus dados de login:\n\n"
            f"📧 **Email:** {email}\n"
            f"🔒 **Senha:** {senha_masked}\n\n"
            f"Está tudo correto? Confirme para prosseguirmos com o pagamento!"
        )
    else:
        msg = (
            f"Ótimo! Confira seus dados de cadastro:\n\n"
            f"👤 **Nome:** {state.get('cadastro_nome', '')}\n"
            f"🪪 **CPF:** {state.get('cadastro_cpf', '')}\n"
            f"🎂 **Nascimento:** {state.get('cadastro_nascimento', '')}\n"
            f"📱 **Telefone:** {state.get('cadastro_telefone', '')}\n"
            f"⚧ **Sexo:** {state.get('cadastro_sexo', '')}\n"
            f"📧 **Email:** {state.get('cadastro_email', '')}\n\n"
            f"Está tudo correto? Se sim, vamos prosseguir para o pagamento!"
        )
    state["messages"].append(AIMessage(content=msg))
    return state


def collect_address_data(state: AgentState):
    """Solicita os dados de endereço do cliente."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    user_msg = state["messages"][-1].content if state["messages"] else ""
    conversa = _build_conversation_context(state, max_messages=6)

    faltam = []
    if not state.get("endereco_cep"):
        faltam.append("CEP")
    if not state.get("endereco_numero"):
        faltam.append("Número")
    if not state.get("endereco_complemento") and not state.get("endereco_cep"):
        faltam.append("Complemento (se houver)")
    if not state.get("endereco_identificacao"):
        faltam.append("Identificação do endereço (ex: Casa, Apartamento, Escritório)")

    dados_ja = ""
    if state.get("endereco_cep"):
        dados_ja += "- CEP: " + state["endereco_cep"] + "\n"
    if state.get("endereco_numero"):
        dados_ja += "- Número: " + state["endereco_numero"] + "\n"
    if state.get("endereco_complemento"):
        dados_ja += "- Complemento: " + state["endereco_complemento"] + "\n"
    if state.get("endereco_identificacao"):
        dados_ja += "- Identificação: " + state["endereco_identificacao"] + "\n"

    dados_ja_section = ("Dados já informados:\n" + dados_ja) if dados_ja else ""

    sys_prompt = f"""
    Você é o Consultor da HC Pneus.
    Os dados pessoais do cliente já foram confirmados. Agora precisa coletar o endereço de entrega.
    Dados que faltam: {', '.join(faltam)}.
    
    {dados_ja_section}
    
    CONVERSA RECENTE:
    {conversa}
    
    INSTRUÇÕES:
    - Peça: CEP, Número, Complemento (opcional) e uma Identificação (Casa, Apartamento, Escritório, etc.).
    - Explique que o endereço é necessário para finalizar a compra.
    - Seja cordial, breve e objetivo.
    - NÃO repita dados já informados.
    """

    response = llm.invoke(
        [SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)]
    )
    state["messages"].append(AIMessage(content=response.content))

    # Tentar extrair dados de endereço da mensagem do usuário
    extraction_prompt = f"""
    Extraia os dados de endereço da mensagem do usuário.
    Mensagem: "{user_msg}"
    Conversa recente:\n{conversa}
    
    Valores atuais (manter se não atualizados):
    - cep: "{state.get('endereco_cep', '')}"
    - numero: "{state.get('endereco_numero', '')}"
    - complemento: "{state.get('endereco_complemento', '')}"
    - identificacao: "{state.get('endereco_identificacao', '')}"
    
    REGRAS:
    - CEP: 8 dígitos numéricos (pode ter hífen)
    - Número: apenas números
    - Complemento: texto livre (Bloco A, Apt 101, etc.)
    - Identificação: Casa, Apartamento, Escritório, etc.
    - Se o usuário não informou um campo, retorne o valor atual.
    
    Responda APENAS com JSON:
    {{"cep": "...", "numero": "...", "complemento": "...", "identificacao": "..."}}
    """

    try:
        extraction_response = llm.invoke([SystemMessage(content=extraction_prompt)])
        content = extraction_response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        extracted = json.loads(content)
        
        for field, state_key in [("cep", "endereco_cep"), ("numero", "endereco_numero"),
                                   ("complemento", "endereco_complemento"), ("identificacao", "endereco_identificacao")]:
            val = extracted.get(field, "")
            if val and str(val).lower() not in ("null", "none", "", "não informado"):
                state[state_key] = str(val)
    except Exception as e:
        print(f"Erro ao extrair endereço: {e}")

    return state


def confirm_address_data(state: AgentState):
    """Mostra os dados de endereço coletados e pede confirmação."""
    complemento = state.get('endereco_complemento', '')
    complemento_str = complemento if complemento else "(nenhum)"
    msg = (
        f"Agora confira seu endereço:\n\n"
        f"📬 **CEP:** {state.get('endereco_cep', '')}\n"
        f"🔢 **Número:** {state.get('endereco_numero', '')}\n"
        f"🏢 **Complemento:** {complemento_str}\n"
        f"🏠 **Identificação:** {state.get('endereco_identificacao', '')}\n\n"
        f"Está tudo correto? Confirmando, vamos prosseguir para o pagamento!"
    )
    state["messages"].append(AIMessage(content=msg))
    return state


def process_pix_payment(state: AgentState):
    """Confirma PIX como forma de pagamento, executa o scraper e envia os dados."""
    if not state.get("pix_confirmado"):
        # Primeira vez: informar que só PIX está disponível via WhatsApp
        msg = (
            "A forma de pagamento disponível para compras pelo WhatsApp é exclusivamente via **PIX**. 💰\n\n"
            "Deseja prosseguir com o pagamento via PIX?"
        )
        state["messages"].append(AIMessage(content=msg))
        return state
    
    # Se já tem os dados do PIX, não executar de novo
    if state.get("pix_codigo"):
        state["messages"].append(AIMessage(content="Os dados do PIX já foram enviados acima! 😊"))
        return state
    
    # Cliente confirmou PIX — executar o scraper de pagamento!
    # Primeiro, enviar mensagem de aguardo
    state["messages"].append(AIMessage(content="Perfeito! Aguarde um momento enquanto processo seu pedido... 🔄"))
    
    # Montar dados para o scraper
    products = state.get("catalog_results", {}).get("products", [])
    chosen_idx = state.get("produto_escolhido_idx", 0)
    link_produto = ""
    if products and 0 <= chosen_idx < len(products):
        link_produto = products[chosen_idx].get("link_produto", "")
    
    possui_cadastro = state.get("possui_cadastro", "nao")
    
    if possui_cadastro == "sim":
        dados_checkout = {
            "email": state.get("login_email", ""),
            "senha": state.get("login_senha", ""),
        }
    else:
        dados_checkout = {
            "nome": state.get("cadastro_nome", ""),
            "cpf": state.get("cadastro_cpf", ""),
            "nascimento": state.get("cadastro_nascimento", ""),
            "telefone": state.get("cadastro_telefone", ""),
            "sexo": state.get("cadastro_sexo", ""),
            "email": state.get("cadastro_email", ""),
        }
    
    endereco_dados = {
        "cep": state.get("endereco_cep", ""),
        "numero": state.get("endereco_numero", ""),
        "complemento": state.get("endereco_complemento", ""),
        "identificacao": state.get("endereco_identificacao", ""),
    }
    
    print(f"[Agent] Executando scraper de pagamento para: {link_produto}")
    resultado = finalizar_compra_pix(link_produto, possui_cadastro, dados_checkout, endereco_dados)
    
    if resultado:
        state["pix_codigo"] = resultado.get("codigo_pix", "")
        state["pix_qr_path"] = resultado.get("qr_code_path", "")
        state["pix_numero_pedido"] = resultado.get("numero_pedido", "")
        state["pix_total"] = resultado.get("total_compra", "")
        if resultado.get("senha_gerada"):
            state["senha_gerada"] = resultado["senha_gerada"]
        
        # Montar mensagem com os dados do PIX
        msg_pix = (
            "✅ **Pedido realizado com sucesso!**\n\n"
            "📋 **Número do Pedido:** " + state["pix_numero_pedido"] + "\n"
            "💰 **Total:** " + state["pix_total"] + "\n\n"
            "--- **Pagamento via PIX** ---\n\n"
            "Copie o código abaixo para efetuar o pagamento:\n\n"
            "`" + state["pix_codigo"] + "`\n\n"
        )
        
        if state.get("senha_gerada"):
            msg_pix += (
                "🔐 **Seus dados de acesso ao site:**\n"
                "Email: " + state.get("cadastro_email", "") + "\n"
                "Senha: " + state["senha_gerada"] + "\n\n"
            )
        
        msg_pix += (
            "Após o pagamento, você receberá a confirmação por email! 📧\n\n"
            "Se precisar de algo mais, estou à disposição! 😊"
        )
        
        state["messages"].append(AIMessage(content=msg_pix))
        
        # Enviar QR Code como imagem
        if state.get("pix_qr_path"):
            if not state.get("pending_images"):
                state["pending_images"] = []
            state["pending_images"].append({
                "path": state["pix_qr_path"],
                "caption": state["pix_codigo"]
            })
    else:
        msg_erro = (
            "❌ Ops! Ocorreu um erro ao processar seu pedido. "
            "Por favor, tente novamente em alguns instantes ou entre em contato com nossa equipe pelo telefone (61) 3262-2100. 📞"
        )
        state["messages"].append(AIMessage(content=msg_erro))
    
    return state


# Build Graph
workflow = StateGraph(AgentState)

workflow.add_node("parse_intent", parse_intent_and_extract)
workflow.add_node("ask_missing_info", ask_missing_info)
workflow.add_node("general_chat", general_chat)
workflow.add_node("confirm_data", confirm_data)
workflow.add_node("consult_catalog", consult_catalog)
workflow.add_node("recommend_tires", recommend_tires)
# Checkout nodes
workflow.add_node("parse_checkout_intent", parse_checkout_intent)
workflow.add_node("ask_cadastro_ou_login", ask_cadastro_ou_login)
workflow.add_node("collect_checkout_data", collect_checkout_data)
workflow.add_node("confirm_checkout_data", confirm_checkout_data)
workflow.add_node("collect_address_data", collect_address_data)
workflow.add_node("confirm_address_data", confirm_address_data)
workflow.add_node("process_pix_payment", process_pix_payment)

workflow.set_entry_point("parse_intent")

workflow.add_conditional_edges(
    "parse_intent",
    router_node,
    {
        "general_chat": "general_chat",
        "ask_missing_info": "ask_missing_info",
        "confirm_data": "confirm_data",
        "consult_catalog": "consult_catalog",
        # Checkout routes
        "ask_cadastro_ou_login": "ask_cadastro_ou_login",
        "collect_checkout_data": "collect_checkout_data",
        "confirm_checkout_data": "confirm_checkout_data",
        "collect_address_data": "collect_address_data",
        "confirm_address_data": "confirm_address_data",
        "process_pix_payment": "process_pix_payment",
        END: END,
    },
)

# Checkout conditional edges (parse_checkout_intent -> router -> correto nó)
workflow.add_conditional_edges(
    "parse_checkout_intent",
    router_node,
    {
        "ask_cadastro_ou_login": "ask_cadastro_ou_login",
        "collect_checkout_data": "collect_checkout_data",
        "confirm_checkout_data": "confirm_checkout_data",
        "collect_address_data": "collect_address_data",
        "confirm_address_data": "confirm_address_data",
        "process_pix_payment": "process_pix_payment",
        "general_chat": "general_chat",
        END: END,
    },
)

workflow.add_edge("general_chat", END)
workflow.add_edge("ask_missing_info", END)
workflow.add_edge("confirm_data", END)
workflow.add_edge("consult_catalog", "recommend_tires")
workflow.add_edge("recommend_tires", END)
# Checkout edges
workflow.add_edge("ask_cadastro_ou_login", END)
workflow.add_edge("collect_checkout_data", END)
workflow.add_edge("confirm_checkout_data", END)
workflow.add_edge("collect_address_data", END)
workflow.add_edge("confirm_address_data", END)
workflow.add_edge("process_pix_payment", END)

agent_executor = workflow.compile()

def process_message(user_message: str, current_state: dict):
    if not current_state:
        current_state = {
            "messages": [],
            "is_buying_intent": False,
            "car_marca": None,
            "car_modelo": None,
            "car_ano": None,
            "car_versao": None,
            "aro": None,
            "catalog_results": {},
            "recommendation_given": False,
            "dados_confirmados": False,
            "pending_images": [],
            "produto_escolhido_idx": -1,
            # Checkout
            "checkout_iniciado": False,
            "possui_cadastro": "",
            "login_email": "",
            "login_senha": "",
            "cadastro_nome": "",
            "cadastro_cpf": "",
            "cadastro_nascimento": "",  
            "cadastro_telefone": "",
            "cadastro_sexo": "",
            "cadastro_email": "",
            "dados_checkout_confirmados": False,
            "endereco_cep": "",
            "endereco_numero": "",
            "endereco_complemento": "",
            "endereco_identificacao": "",
            "endereco_confirmado": False,
            "pix_confirmado": False,
            "pix_codigo": "",
            "pix_qr_path": "",
            "pix_numero_pedido": "",
            "pix_total": "",
            "senha_gerada": "",
        }

    # Limpar imagens pendentes de rodadas anteriores
    current_state["pending_images"] = []

    current_state["messages"].append(HumanMessage(content=user_message))
    new_state = agent_executor.invoke(current_state)
    ai_text = new_state["messages"][-1].content

    # Montar lista de mensagens de retorno
    response_messages = []

    # Adicionar imagens pendentes primeiro
    for img in new_state.get("pending_images", []):
        caption = img.get("caption", "")
        # Se a imagem tiver caption vazio, usamos o texto do agente como caption
        if not caption and ai_text:
            caption = ai_text
            ai_text = ""  # Limpa para não enviar mensagem de texto duplicada
            
        response_messages.append({
            "type": "image",
            "path": img["path"],
            "caption": caption
        })

    # Texto por último (se ainda sobrar texto)
    if ai_text:
        response_messages.append({"type": "text", "content": ai_text})

    return response_messages, new_state
