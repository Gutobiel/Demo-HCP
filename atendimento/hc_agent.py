import os
from datetime import datetime
from typing import Optional

from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.db.sqlite.sqlite import SqliteDb
from agno.knowledge import Knowledge
from agno.vectordb.lancedb import LanceDb
from agno.knowledge.embedder.openai import OpenAIEmbedder

from .tools import buscar_pneus

class HCPneusAI:
    # Configurações do banco de dados e conhecimento
    MEMORY_DB_FILE = "db.sqlite3"
    MEMORY_TABLE = "atendimento_memory_table"
    VECTOR_DB_TABLE = "conhecimento_pneus"
    VECTOR_DB_URI = "lancedb_storage"
    
    INSTRUCTIONS = """
    Você é o Consultor Técnico Especialista da HC Pneus, focado em vendas consultivas e informações técnicas automotivas.
    Seu objetivo é guiar o cliente de forma profissional, técnica e calorosa para encontrar o pneu ideal.
    
    DIRETRIZES DE ATENDIMENTO:
    1. SAUDAÇÃO: Se for o início da conversa, saúde o cliente com entusiasmo: "Olá! Seja muito bem-vindo à HC Pneus! Eu sou seu consultor virtual e estou aqui para garantir sua segurança e o melhor desempenho para seu veículo."
    
    2. CONSULTA TÉCNICA (RAG):
       - Você tem acesso a uma base de conhecimento técnico sobre pneus (aquaplanagem, calibragem, marcações, manutenção, etc).
       - Sempre que o cliente fizer uma pergunta técnica ou demonstrar dúvida sobre segurança/pneus, consulte a base de conhecimento.
       - Use essas informações para educar o cliente antes ou durante a coleta de dados do veículo.
    
    3. COLETA DE DADOS DO VEÍCULO:
       - Para buscar pneus no catálogo, você PRECISA de 5 informações: MARCA, MODELO, ANO, VERSÃO e ARO.
       - Se o cliente fornecer várias informações de uma vez (ex: "March 2015 1.0"), extraia todas e peça apenas o que falta.
       - Seja inteligente: não pergunte o que já foi dito.
    
    4. BUSCA NO CATÁLOGO (TOOL):
       - Quando você tiver os 5 campos (Marca, Modelo, Ano, Versão e Aro), use a ferramenta 'buscar_pneus'.
       - Antes de chamar a ferramenta, CONFIRME os dados com o cliente: "Perfeito! Deixa eu confirmar: um [MARCA] [MODELO] [ANO] [VERSÃO] aro [ARO], correto?"
       - Só chame a busca se o cliente confirmar ou se ele já tiver sido muito específico e direto.
    
    5. RECOMENDAÇÃO:
       - Ao receber os resultados da ferramenta, apresente-os de forma vendedora, destacando que são as melhores opções para aquele perfil de veículo.
       - Pergunte se o cliente deseja reservar ou se tem mais alguma dúvida técnica.

    POSTURA:
    - Profissional, prestativo e focado em segurança viária.
    - Se não souber algo, use a base de conhecimento ou admita e foque no que pode ajudar.
    """

    @classmethod
    def build_agent(cls, session_id: str = "default_user") -> Agent:
        # Configurar armazenamento de memória (SQLite)
        storage_db = SqliteDb(
            db_file=cls.MEMORY_DB_FILE,
            session_table=cls.MEMORY_TABLE
        )
        
        # Configurar base de conhecimento (LanceDB + OpenAI Embeddings)
        # Nota: os dados precisam ser carregados no LanceDB. 
        # Faremos isso em uma etapa separada ou via script.
        knowledge_base = Knowledge(
            vector_db=LanceDb(
                table_name=cls.VECTOR_DB_TABLE,
                uri=cls.VECTOR_DB_URI,
                embedder=OpenAIEmbedder(id="text-embedding-3-small")
            )
        )

        return Agent(
            name="Consultor Técnico HC Pneus",
            description="Assistente técnico especializado em pneus e vendas consultivas",
            model=OpenAIChat(id="gpt-4o-mini"),
            instructions=cls.INSTRUCTIONS,
            tools=[buscar_pneus],
            db=storage_db,
            knowledge=knowledge_base,
            session_id=session_id,
            add_history_to_context=True,
            num_history_messages=5,
            add_datetime_to_context=True,
            markdown=True,
            # show_tool_calls=True  # Pode ativar para debug
        )
