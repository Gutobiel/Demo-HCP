# 🚗 HC Pneus - Agente de IA para Vendas (WhatsApp & Web)

Bem-vindo ao repositório do **Agente de IA da HC Pneus**! 🤖🛞
Este projeto é um Consultor Técnico Virtual autônomo, desenhado para conversar com os clientes de forma humanizada, entender suas necessidades, extrair parâmetros de veículos e consultar preços de estoque de pneus em tempo real.

O bot atua principalmente no **WhatsApp** (integrado via ZDG / Evolution API) e no **Web Chat**, simulando um vendedor experiente na triagem e no fechamento de vendas.

---

## 🛠️ Tecnologias Utilizadas

A arquitetura do projeto une inteligência artificial generativa com automação clássica (RPA) fornecendo escalabilidade e velocidade:

*   **Django (Python):** Servidor Backend principal que gerencia as rotas, páginas Web e os endpoints dos Webhooks.
*   **LangChain & LangGraph:** Cérebro do bot. O LangGraph controla a *Máquina de Estados* (fluxo lógico) e o LangChain atua como ponte com os modelos de IA.
*   **GPT-4o-mini (OpenAI):** O modelo de linguagem (LLM) usado para entender o contexto, extrair entidades e formular conversas humanizadas.
*   **Selenium (RPA Web):** Robô de extração que navega instantaneamente no site do cliente preenchendo filtros e obtendo preços e estoques validados `scraper.py`.
*   **Evolution API (Node/ZDG):** Integração essencial para disparar e receber as mensagens via WhatsApp no modelo *Baileys*.

---

## 🔁 Arquitetura e Fluxo de Mensagens

Como a jornada da mensagem do cliente acontece:

1. **Recepção:** O cliente envia "Oi" no WhatsApp. A *Evolution API* envia o pacote via Webhook.
2. **Memória de Estado:** O Django (em `views.py`) recupera a sessão do usuário baseada em seu número. Isso faz o bot "lembrar" do contexto da conversa inteira.
3. **Grafos Mágicos (`agent.py`):** O texto e a memória são inseridos no `agent_executor`, passando por fluxos de validação.
4. **Resposta:** A IA decide se vai falar livremente, tirar dúvidas técnicas ou avançar a venda. A resposta consolidada viaja de volta ao WhatsApp na mesma hora.

---

## 🧠 Como Funciona: Máquina de Estados (LangGraph)

O agente não é apenas um "bot de perguntas prontas". Ele usa grafos para determinar os próximos passos de um cliente de forma lógica:

*   **`parse_intent`:** Assimila a intenção principal. Tenta extrair 5 dados essenciais do usuário: *Marca, Modelo, Ano, Versão e Aro*.
*   **Routers Iniciais:**
    *   Faltam dados do carro? -> Pula para nó `ask_missing_info`.
    *   Todos os dados existem, mas não confirmados? -> Pula para `confirm_data`.
    *   Tudo confirmado e pronto pra cotação? -> Vai pro scraper em `consult_catalog`.
*   **`ask_missing_info`:** Em vez de ser robótico ("*1. Digite a marca*"), a IA olha pro contexto antes de perguntar o que falta de forma sutil (*"Que legal que tem um Corolla. E qual o aro para eu ver aqui de pressa?"*).
*   **`consult_catalog` (RPA):** Inicia o Selenium invisible, abrindo a loja virtual da HC Pneus para buscar opções reais. Falhas no site real acionam um banco "Mock" local de contingência programado.
*   **`recommend_tires`:** Junta os preços do Selenium com o Prompt de fechamento de vendas, listando opções para o cliente escolher e gerando links de conversão direta.

---

## ✨ Funcionalidades

- **Reconhecimento de Entidades (NER):** Consegue pinçar detalhes mesmo que o cliente jogue em textos corridos (*Ex: "Eu tenho um Onix 14 e tá fazendo barulho"* -> Extrai Aro 14, Modelo Onix).
- **RAG Local:** Base de conhecimento (`knowledge_base.py`) embutida para tirar dúvidas de mecânica básica sobre os pneus.
- **RPA Integrado:** Foge da alucinação dos modelos (LLM) consumindo os preços direto da verdadeira base pública de e-commerce do cliente usando raspagem robusta.
- **Fechamento Comercial:** Tenta ativamente avançar a compra para não ser apenas um mero consultor de conversas gratuitas.

---

## 🚀 Como Executar Localmente

### Pré-requisitos
- Python 3.10+
- Chave de API da OpenAI (`OPENAI_API_KEY`)
- Chrome instalado na máquina (para o Selenium Webdriver)
- Instância ou acesso a uma Evolution API rodando (ou simulador ZDG).

### Passo a Passo

1. **Clone o repositório:**
```sh
git clone https://github.com/seuid/Demo_HCPneus.git
cd Demo_HCPneus
```

2. **Crie e ative o ambiente virtual:**
```sh
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

3. **Instale as dependências:**
```sh
pip install -r requirements.txt
```

4. **Configurações de Ambiente (`.env`):**
Crie um arquivo `.env` na raiz:
```env
OPENAI_API_KEY=sk-xxxx...
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=yyyy...
EVOLUTION_INSTANCE_NAME=hcpneus-bot
```

5. **Inicie o servidor Django:**
```sh
python manage.py runserver
```

6. **Para acessar o site de teste:**
Abra `http://localhost:8000/api/whatsapp/chat/` caso deseje testar as conversas no WebChat simulando a jornada final (sem plugar a api do WhatsApp).

---
*Projeto em desenvolvimento ativo. Feito para demonstrações de automação multi-agente.*
