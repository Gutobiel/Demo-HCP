import os
import json
from typing import Dict, TypedDict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from .scraper import buscar_pneus_no_site
from .knowledge_base import buscar_conhecimento

# Define the state schema
class AgentState(TypedDict):
    messages: list
    car_marca: str
    car_modelo: str
    car_ano: str
    car_versao: str
    aro: str
    catalog_results: list
    recommendation_given: bool
    dados_confirmados: bool  # True quando o cliente confirma os dados


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
    
    O cliente pode informar vários dados de uma vez. Exemplo:
    "Nissan March 2015 1.0" → marca=Nissan, modelo=March, ano=2015, versão=1.0
    "Corolla 2020 XEI aro 17" → modelo=Corolla, ano=2020, versão=XEI, aro=17
    "14" (quando o consultor perguntou pelo aro) → aro=14
    
    CONTEXTO IMPORTANTE: Se o consultor perguntou algo específico e o cliente respondeu com um número ou palavra curta,
    interprete como resposta à pergunta feita. Exemplos:
    - Consultor perguntou "qual o aro?" e cliente disse "14" → aro=14
    - Consultor perguntou "qual o ano?" e cliente disse "2015" → ano=2015
    - Consultor perguntou "qual a marca?" e cliente disse "Toyota" → marca=Toyota
    
    Estado atual (informações JÁ coletadas):
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
        # Limpar a resposta (remover markdown code blocks se houver)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content
            content = content.rsplit("```", 1)[0] if "```" in content else content
            content = content.strip()
        
        extracted = json.loads(content)

        # Atualizar TODOS os campos que vieram preenchidos (não "null")
        for key in ["car_marca", "car_modelo", "car_ano", "car_versao", "aro"]:
            value = extracted.get(key)
            if value and str(value).lower() not in ("null", "none", "não informado"):
                state[key] = str(value)

    except Exception as e:
        print(f"Erro no parse de intenção: {e}")
        print(f"Resposta do LLM: {response.content}")

    return state


def router_node(state: AgentState):
    """Decides what the agent should do next based on missing info."""
    # Se os dados foram confirmados, ir direto para o catálogo
    if state.get("dados_confirmados") and not state.get("recommendation_given"):
        return "consult_catalog"
    
    if not state.get("car_marca"):
        return "ask_brand"
    if not state.get("car_modelo"):
        return "ask_model"
    if not state.get("car_ano"):
        return "ask_year"
    if not state.get("car_versao"):
        return "ask_version"
    if not state.get("aro"):
        return "ask_rim"
    
    # Todos os campos preenchidos mas não confirmados → confirmar
    if not state.get("dados_confirmados"):
        return "confirm_data"
    
    if not state.get("recommendation_given"):
        return "consult_catalog"
    return END


def confirm_data(state: AgentState):
    """Apresenta os dados coletados e pede confirmação ao cliente."""
    marca = state.get("car_marca", "")
    modelo = state.get("car_modelo", "")
    ano = state.get("car_ano", "")
    versao = state.get("car_versao", "")
    aro = state.get("aro", "")

    msg = (
        f"Perfeito! Deixa eu confirmar os dados do seu veículo:\n\n"
        f"🚗 **Marca:** {marca}\n"
        f"📋 **Modelo:** {modelo}\n"
        f"📅 **Ano:** {ano}\n"
        f"⚙️ **Versão:** {versao}\n"
        f"🔧 **Aro:** {aro}\n\n"
        f"Está tudo correto? Se sim, vou buscar as melhores opções de pneus para você!"
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
    - Seja cordial e profissional, mas BREVE.
    - NÃO repita informações que o cliente já forneceu.
    - Se o cliente perguntar algo técnico, responda usando o CONHECIMENTO TÉCNICO antes de pedir a próxima informação.
    - Já sabemos do veículo: {dados_str}
    
    CONVERSA ATÉ AGORA:
    {conversa}
    
    Gere apenas a resposta para o chat, pedindo a informação que falta ({tipo_label}).
    """
    
    response = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_msg)])
    return response.content

def ask_brand(state: AgentState):
    res = generate_consultative_question(state, "brand")
    state["messages"].append(AIMessage(content=res))
    return state

def ask_model(state: AgentState):
    res = generate_consultative_question(state, "model")
    state["messages"].append(AIMessage(content=res))
    return state

def ask_year(state: AgentState):
    res = generate_consultative_question(state, "year")
    state["messages"].append(AIMessage(content=res))
    return state

def ask_version(state: AgentState):
    res = generate_consultative_question(state, "version")
    state["messages"].append(AIMessage(content=res))
    return state

def ask_rim(state: AgentState):
    res = generate_consultative_question(state, "rim")
    state["messages"].append(AIMessage(content=res))
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

    results = state.get("catalog_results", [])
    car_modelo = state.get("car_modelo", "")
    aro = state.get("aro", "")

    if not results:
        msg = f"Infelizmente não encontrei pneus aro {aro} para o {car_modelo} no momento em nosso site. Posso ajudar com mais alguma coisa?"
    else:
        products_text = ""
        for i, p in enumerate(results):
            products_text += f"\n- {p['nome_modelo']} | {p['preco']}"

        sys_prompt = f"""
        Você é um vendedor entusiasta da HC Pneus.
        O cliente possui um {car_modelo} usando aro {aro}.
        Você consultou o sistema e tem estes produtos disponíveis:
        {products_text}
        
        Gere uma resposta amigável recomendando esses pneus exatamente como vieram.
        Se o sistema não trouxe marcas famosas ou apenas serviços/genéricos, mostre exatamente a lista de disponibilidade informando os preços para manter a agilidade.
        Pergunte se o cliente deseja reservar. Pode usar <br> e <b> (HTML) para formatar bonito.
        """
        response = llm.invoke([SystemMessage(content=sys_prompt)])
        msg = response.content
        state["recommendation_given"] = True

    state["messages"].append(AIMessage(content=msg))
    return state


# Build Graph
workflow = StateGraph(AgentState)

workflow.add_node("parse_intent", parse_intent_and_extract)
workflow.add_node("ask_brand", ask_brand)
workflow.add_node("ask_model", ask_model)
workflow.add_node("ask_year", ask_year)
workflow.add_node("ask_version", ask_version)
workflow.add_node("ask_rim", ask_rim)
workflow.add_node("confirm_data", confirm_data)
workflow.add_node("consult_catalog", consult_catalog)
workflow.add_node("recommend_tires", recommend_tires)

workflow.set_entry_point("parse_intent")

workflow.add_conditional_edges(
    "parse_intent",
    router_node,
    {
        "ask_brand": "ask_brand",
        "ask_model": "ask_model",
        "ask_year": "ask_year",
        "ask_version": "ask_version",
        "ask_rim": "ask_rim",
        "confirm_data": "confirm_data",
        "consult_catalog": "consult_catalog",
        END: END,
    },
)

workflow.add_edge("ask_brand", END)
workflow.add_edge("ask_model", END)
workflow.add_edge("ask_year", END)
workflow.add_edge("ask_version", END)
workflow.add_edge("ask_rim", END)
workflow.add_edge("confirm_data", END)
workflow.add_edge("consult_catalog", "recommend_tires")
workflow.add_edge("recommend_tires", END)

agent_executor = workflow.compile()

def process_message(user_message: str, current_state: dict):
    if not current_state:
        current_state = {
            "messages": [],
            "car_marca": None,
            "car_modelo": None,
            "car_ano": None,
            "car_versao": None,
            "aro": None,
            "catalog_results": [],
            "recommendation_given": False,
            "dados_confirmados": False,
        }

    current_state["messages"].append(HumanMessage(content=user_message))
    new_state = agent_executor.invoke(current_state)
    ai_response = new_state["messages"][-1].content
    return ai_response, new_state
