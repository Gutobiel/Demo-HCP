import os
import json
from typing import Dict, TypedDict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from .scraper_search import buscar_pneus_no_site
from .scraper_screenshot import screenshot_produto
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
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    user_msg = state["messages"][-1].content if state["messages"] else ""

    # Verificar se o cliente está confirmando os dados
    confirmacao_words = ["ok", "sim", "isso", "correto", "certo", "confirmo", 
                         "isso mesmo", "pode buscar", "perfeito", "exato", "tá certo",
                         "ta certo", "isso aí", "confirma", "bora", "pode ser", "yes",
                         "é sim", "e sim"]
    msg_lower = user_msg.strip().lower()
    
    # Se todos os campos estão preenchidos e o cliente confirmou
    all_filled = all([
        state.get("car_marca"),
        state.get("car_modelo"),
        state.get("car_ano"),
        state.get("car_versao"),
        state.get("aro")
    ])
    
    if all_filled and not state.get("dados_confirmados"):
        if any(word in msg_lower for word in confirmacao_words):
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
    
    # 4. Confirmação genérica para quando há apenas 1 produto
    if len(products) == 1:
        confirmacao = ["sim", "isso", "quero", "pode ser", "esse mesmo", "esse",
                       "quero esse", "ok", "certo", "perfeito", "bora", "confirmo", "ele mesmo"]
        if any(w in msg_lower for w in confirmacao):
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
                    confirmacao = ["sim", "isso", "quero", "pode ser", "esse", "ok", "certo", "perfeito", "confirmo", "manda", "bora"]
                    user_lower = user_msg.strip().lower()
                    
                    if detected_idx >= 0 and detected_idx != already_chosen_idx:
                        # Mudou de ideia e escolheu outro modelo
                        just_chose_now = True
                        current_chosen_idx = detected_idx
                    elif any(w in user_lower for w in confirmacao) or detected_idx == already_chosen_idx:
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
                link = products[current_chosen_idx].get('link_produto', '') if current_chosen_idx >= 0 and current_chosen_idx < len(products) else ""
                objetivos_extras = f"""
                ATENÇÃO PARA FLUXO DE COMPRA:
                O cliente ACABOU DE CONFIRMAR a compra do modelo selecionado.
                SUA MISSÃO FINAL É:
                - Diga algo como: "Que ótimo! Você pode concluir a compra de forma 100% segura e rápida através do link abaixo:\n\n[Comprar Pneu Agora]({link})\n\nSe precisar de mais alguma coisa, estou à disposição!"
                - O Link OBRIGATORIAMENTE DEVE estar no formato correto Markdown.
                - NÃO faça mais perguntas. Apenas entregue o link de checkout.
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


# Build Graph
workflow = StateGraph(AgentState)

workflow.add_node("parse_intent", parse_intent_and_extract)
workflow.add_node("ask_missing_info", ask_missing_info)
workflow.add_node("general_chat", general_chat)
workflow.add_node("confirm_data", confirm_data)
workflow.add_node("consult_catalog", consult_catalog)
workflow.add_node("recommend_tires", recommend_tires)

workflow.set_entry_point("parse_intent")

workflow.add_conditional_edges(
    "parse_intent",
    router_node,
    {
        "general_chat": "general_chat",
        "ask_missing_info": "ask_missing_info",
        "confirm_data": "confirm_data",
        "consult_catalog": "consult_catalog",
        END: END,
    },
)

workflow.add_edge("general_chat", END)
workflow.add_edge("ask_missing_info", END)
workflow.add_edge("confirm_data", END)
workflow.add_edge("consult_catalog", "recommend_tires")
workflow.add_edge("recommend_tires", END)

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
