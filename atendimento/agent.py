import os
from typing import Dict, TypedDict, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from .scraper import buscar_pneus_no_site

# Define the state schema
class AgentState(TypedDict):
    messages: list
    car_brand: str
    car_model: str
    car_year: str
    car_version: str
    rim_size: str
    catalog_results: list
    recommendation_given: bool

def parse_intent_and_extract(state: AgentState):
    """Uses LLM to evaluate the latest user message and extract required info."""
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    prompt = f"""
    Você é um agente de vendas da HC Pneus, atuando em português brasileiro.
    Objetivo: ajudar clientes a encontrar os produtos certos e gerar leads qualificados.
   
    1. Saudação:
    "Olá, como posso te ajudar hoje?"
    Analise a mensagem do usuário e extraia o máximo das seguintes informações do veículo e pneu:
    - Marca do Carro (ex: Toyota, Chevrolet, Honda)
    - Modelo do Carro (ex: Corolla, Onix, Civic)
    - Ano do Carro (ex: 2018, 2020)
    - Versão do Carro (ex: 1.0, 1.6, SL, Automatico, 12V, 16V)
    - Aro do Pneu (ex: 15, 16, R17)
    
    Estado atual de informações conhecidas:
    - Marca: {state.get('car_brand', 'Não informado')}
    - Modelo: {state.get('car_model', 'Não informado')}
    - Ano: {state.get('car_year', 'Não informado')}
    - Versão: {state.get('car_version', 'Não informado')}
    - Aro: {state.get('rim_size', 'Não informado')}
    
    RESPONDA EXATAMENTE NO FORMATO JSON ABAIXO, substituindo null pelo valor extraído ou mantendo null se não estiver na mensagem:
    {{
        "car_brand": "marca ou null",
        "car_model": "modelo ou null",
        "car_year": "ano ou null",
        "car_version": "versão ou null",
        "rim_size": "aro ou null"
    }}
    """

    user_msg = state["messages"][-1].content if state["messages"] else ""
    response = llm.invoke(
        [SystemMessage(content=prompt), HumanMessage(content=user_msg)]
    )

    try:
        import json
        extracted = json.loads(response.content)

        if extracted.get("car_brand") and not state.get("car_brand"):
            state["car_brand"] = extracted["car_brand"]
        if extracted.get("car_model") and not state.get("car_model"):
            state["car_model"] = extracted["car_model"]
        if extracted.get("car_year") and not state.get("car_year"):
            state["car_year"] = extracted["car_year"]
        if extracted.get("car_version") and not state.get("car_version"):
            state["car_version"] = extracted["car_version"]
        if extracted.get("rim_size") and not state.get("rim_size"):
            state["rim_size"] = extracted["rim_size"]
    except Exception as e:
        print(f"Erro no parse de intenção: {e}")

    return state


def router_node(state: AgentState):
    """Decides what the agent should do next based on missing info."""
    if not state.get("car_brand"):
        return "ask_brand"
    if not state.get("car_model"):
        return "ask_model"
    if not state.get("car_year"):
        return "ask_year"
    if not state.get("car_version"):
        return "ask_version"
    if not state.get("rim_size"):
        return "ask_rim"
    if not state.get("recommendation_given"):
        return "consult_catalog"
    return END

def ask_brand(state: AgentState):
    if len(state["messages"]) <= 1:
        # First interaction
        res = "Olá, como posso te ajudar a encontrar o produto ideal para sua necessidade hoje? Para começarmos, qual é a **Marca** do seu veículo?"
    else:
        res = "Por favor, me informe a **Marca** do veículo (ex: Toyota, Honda, etc)."
    state["messages"].append(AIMessage(content=res))
    return state

def ask_model(state: AgentState):
    response = f"Excelente marca. E qual é o **Modelo** do seu {state['car_brand']}?"
    state["messages"].append(AIMessage(content=response))
    return state

def ask_year(state: AgentState):
    response = f"Entendi, é um {state['car_brand']} {state['car_model']}. Qual o **Ano** dele?"
    state["messages"].append(AIMessage(content=response))
    return state

def ask_version(state: AgentState):
    response = f"Quase lá! Qual é a **Versão** do seu {state['car_model']} {state['car_year']} (ex: XEI, LTZ, Touring)?"
    state["messages"].append(AIMessage(content=response))
    return state

def ask_rim(state: AgentState):
    response = "Perfeito! E para filtrarmos melhor as opções, você sabe me dizer qual é o **Aro** do pneu que você precisa? (Ex: 15, 16, 17)"
    state["messages"].append(AIMessage(content=response))
    return state


def consult_catalog(state: AgentState):
    print("Consultando site com:", state["car_brand"], state["car_model"], state["car_year"], state["car_version"], state["rim_size"])
    results = buscar_pneus_no_site(
        state["car_brand"], state["car_model"], state["car_year"], state["car_version"], state["rim_size"]
    )
    state["catalog_results"] = results
    return state

def recommend_tires(state: AgentState):
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    results = state.get("catalog_results", [])
    car_model = state.get("car_model", "")
    rim = state.get("rim_size", "")

    if not results:
        msg = f"Infelizmente não encontrei pneus aro {rim} para o {car_model} no momento em nosso site. Posso ajudar com mais alguma coisa?"
    else:
        products_text = ""
        for i, p in enumerate(results):
            products_text += f"\n- {p['nome_modelo']} | {p['preco']}"

        sys_prompt = f"""
        Você é um vendedor entusiasta da HC Pneus.
        O cliente possui um {car_model} usando aro {rim}.
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
        "consult_catalog": "consult_catalog",
        END: END,
    },
)

workflow.add_edge("ask_brand", END)
workflow.add_edge("ask_model", END)
workflow.add_edge("ask_year", END)
workflow.add_edge("ask_version", END)
workflow.add_edge("ask_rim", END)
workflow.add_edge("consult_catalog", "recommend_tires")
workflow.add_edge("recommend_tires", END)

agent_executor = workflow.compile()

def process_message(user_message: str, current_state: dict):
    if not current_state:
        current_state = {
            "messages": [],
            "car_brand": None,
            "car_model": None,
            "car_year": None,
            "car_version": None,
            "rim_size": None,
            "catalog_results": [],
            "recommendation_given": False,
        }

    current_state["messages"].append(HumanMessage(content=user_message))
    new_state = agent_executor.invoke(current_state)
    ai_response = new_state["messages"][-1].content
    return ai_response, new_state
