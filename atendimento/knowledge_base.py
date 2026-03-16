"""
Base de Conhecimento Técnico sobre Pneus - HC Pneus
Fontes: Continental Pneus (https://www.conti.com.br/tire-knowledge/)

Este módulo armazena o conteúdo técnico extraído dos 15 sites de referência
e disponibiliza uma função de busca por palavra-chave para o agente.
"""

# Cada entrada tem: título, palavras-chave para busca, conteúdo resumido, e a URL de referência
KNOWLEDGE_BASE = [
    {
        "titulo": "Aquaplanagem - O que é e como evitar",
        "palavras_chave": ["aquaplanagem", "aquaplaning", "chuva", "piso molhado", "água", "escorregadio", "derrapar", "hidroplanagem"],
        "url": "https://www.conti.com.br/tire-knowledge/aquaplaning/",
        "conteudo": (
            "A aquaplanagem ocorre quando uma camada de água se forma entre o pneu e o asfalto, "
            "fazendo com que o veículo perca a tração. Pneus novos dispersam até 30 litros de água por segundo a 80 km/h. "
            "Quando a profundidade da banda de rodagem cai para 1,6 mm (mínimo legal), a expulsão de água é drasticamente reduzida. "
            "A Continental recomenda trocar os pneus quando atingirem 3 mm de profundidade. "
            "Em caso de aquaplanagem: tire o pé do acelerador, pressione a embreagem, evite movimentos bruscos no volante. "
            "Indicadores de desgaste (TWI) estão nos sulcos principais do pneu. "
            "A Continental possui indicadores de umidade com 3 mm de altura entre os blocos da banda de rodagem."
        )
    },
    {
        "titulo": "Calibragem dos Pneus - Pressão correta",
        "palavras_chave": ["calibragem", "pressão", "calibrar", "psi", "enchimento", "murcho", "vazio", "cheio", "bomba"],
        "url": "https://www.conti.com.br/tire-knowledge/tire-pressure/",
        "conteudo": (
            "A calibragem correta dos pneus é essencial para segurança, economia e durabilidade. "
            "Pneus com pouca pressão aumentam o consumo de combustível, desperdiçando até 167 litros por ano. "
            "A calibragem correta pode prolongar a vida útil do pneu em até 7.500 km. "
            "Pneus subinflados aumentam a chance de acidente em até 3 vezes (NHTSA). "
            "27% dos carros e 32% das vans rodam com ao menos um pneu subinflado. "
            "Pneus com muita pressão tornam a dirigibilidade perigosa em curvas, enquanto pneus com pouca pressão "
            "deixam a direção lenta. Ambos afetam a distância de frenagem e a aderência."
        )
    },
    {
        "titulo": "Marcações do Pneu - Como ler as medidas",
        "palavras_chave": ["medida", "marcação", "tamanho", "largura", "perfil", "aro", "diâmetro", "leitura", "lateral", "número", "letra", "205", "55", "r16"],
        "url": "https://www.conti.com.br/tire-knowledge/tire-markings/",
        "conteudo": (
            "As marcações na lateral do pneu contêm informações essenciais. Exemplo: 225/45 R 18 95 H. "
            "225 = Largura do pneu em mm. "
            "45 = Altura (percentual da largura, ou 'perfil'). "
            "R = Construção Radial (mais comum hoje). "
            "18 = Diâmetro do aro em polegadas. "
            "95 = Índice de Carga (peso máximo que o pneu suporta). "
            "H = Índice de Velocidade (H = 209 km/h). "
            "Outras marcações: Run Flat (pneu autônomo), DOT (semana e ano de fabricação), M+S (lama e neve)."
        )
    },
    {
        "titulo": "Índice de Velocidade dos Pneus",
        "palavras_chave": ["velocidade", "índice", "máxima", "letra", "h", "v", "w", "t", "speed"],
        "url": "https://www.conti.com.br/tire-knowledge/indice-de-velocidade-pneu/",
        "conteudo": (
            "O índice de velocidade indica a velocidade máxima que o pneu pode suportar com segurança. "
            "Exemplos: T = até 190 km/h, H = até 210 km/h, V = até 240 km/h, W = até 270 km/h. "
            "NUNCA use um pneu com índice de velocidade menor que o original do veículo. "
            "Pode-se usar um índice superior ao original, mas devem ser instalados em pares no mesmo eixo. "
            "O índice de carga (número antes da letra) refere-se ao peso máximo que o pneu suporta. "
            "Pneus UHP (Ultra High Performance) como o SportContact 7 têm índices altos de carga e velocidade."
        )
    },
    {
        "titulo": "Pneus Premium vs Pneus de Baixo Custo",
        "palavras_chave": ["premium", "barato", "importado", "custo", "qualidade", "diferença", "comparação", "melhor", "pior", "segurança", "continental"],
        "url": "https://www.conti.com.br/tire-knowledge/pneu-premium-vs-pneu-importado-baixo-custo/",
        "conteudo": (
            "Pneus premium (como Continental) oferecem frenagem superior em piso molhado, "
            "maior aderência em piso seco e molhado, menor ruído e maior resistência à aquaplanagem. "
            "Os padrões de banda de rodagem avançados dispersam água de forma eficiente. "
            "Pneus de baixo custo podem ter materiais de qualidade inferior e construção mais básica, "
            "resultando em distâncias de frenagem mais longas e menor estabilidade. "
            "A segurança em condições adversas pode ser comprometida com pneus importados de baixo custo. "
            "Testes no Contidrom (Alemanha) demonstram diferenças significativas de desempenho."
        )
    },
    {
        "titulo": "Componentes dos Pneus - Estrutura interna",
        "palavras_chave": ["componente", "estrutura", "carcaça", "banda", "rodagem", "talão", "borracha", "aço", "camada", "interno", "construção"],
        "url": "https://www.conti.com.br/tire-knowledge/tire-components/",
        "conteudo": (
            "Os pneus são compostos por 9 componentes principais: "
            "1. Banda de rodagem (borracha sintética e natural, garante aderência e expulsão de água). "
            "2. Lonas sem junta (fio de nylon coberto em borracha para alta velocidade). "
            "3. Cintas de aço (cordões de aço para rigidez e estabilidade direcional). "
            "4. Camada de tecido (rayon ou poliéster para controlar pressão e manter forma). "
            "5. Revestimento interno/liner (borracha butílica hermética, atua como câmara de ar). "
            "6. Parede lateral (borracha natural para proteção). "
            "7. Reforço do talão (nylon ou aramida para estabilidade). "
            "8. Apex (enchimento de borracha para conforto). "
            "9. Centro do talão (arame de aço para fixação no aro). "
            "Em 1904, a Continental introduziu os primeiros desenhos na banda de rodagem."
        )
    },
    {
        "titulo": "Balanceamento e Rodízio de Pneus",
        "palavras_chave": ["balanceamento", "balancear", "rodízio", "desgaste", "vibração", "irregular", "troca", "eixo"],
        "url": "https://www.conti.com.br/tire-knowledge/balancing-tires/",
        "conteudo": (
            "O balanceamento deve ser feito toda vez que os pneus forem desmontados e montados. "
            "Pneus desbalanceados causam vibração, desgaste irregular e comprometem a segurança. "
            "O rodízio é uma das manutenções mais importantes: prolongar a vida útil do pneu, "
            "manter desgaste uniforme e melhorar a estabilidade em curvas e frenagens."
        )
    },
    {
        "titulo": "Montagem Correta de Pneus",
        "palavras_chave": ["montagem", "montar", "instalar", "instalação", "trocar", "troca", "profissional"],
        "url": "https://www.conti.com.br/tire-knowledge/fitting-tires/",
        "conteudo": (
            "A montagem correta é fundamental para que o índice de velocidade e outros parâmetros funcionem. "
            "Sempre procure profissionais qualificados para a montagem. "
            "Pneus mal instalados podem apresentar problemas de desempenho e segurança. "
            "Quando trocar apenas dois pneus, os novos devem ir no eixo traseiro para garantir estabilidade."
        )
    },
    {
        "titulo": "Diferença entre Pneus de 3 e 4 Sulcos",
        "palavras_chave": ["sulco", "sulcos", "3 sulcos", "4 sulcos", "três", "quatro", "diferença", "falsificação"],
        "url": "https://www.conti.com.br/tire-knowledge/diferenca-pneus-3-sulcos-e-4-sulcos/",
        "conteudo": (
            "O número de sulcos no pneu segue regras de design proporcionais à dimensão do pneu. "
            "Os sulcos são canais tangenciais responsáveis por escoar água e evitar aquaplanagem. "
            "O mesmo modelo pode ter 3 ou 4 sulcos dependendo da largura: "
            "Ex: PowerContact 2 - dimensões 165/175/185 = 3 sulcos; 195 = 3 ou 4; 205 = 4 sulcos. "
            "Isso NÃO é falsificação. É uma regra de engenharia baseada na dimensão do pneu. "
            "Podem existir pneus com 1 até 5 sulcos no mercado."
        )
    },
    {
        "titulo": "Pneus Reforçados (XL / Extra Load)",
        "palavras_chave": ["reforçado", "xl", "extra load", "carga", "pesado", "suv", "elétrico", "ev", "run flat", "hl"],
        "url": "https://www.conti.com.br/tire-knowledge/pneu-reforcados/",
        "conteudo": (
            "Pneus reforçados (XL) suportam cargas e pressões maiores que os padrão. "
            "Devem ser calibrados com ~5,8 psi a mais que pneus convencionais. "
            "Marcações: HL, XL, Reforçado, Extra Load ou RF na lateral. "
            "Vantagens: maior capacidade de carga, maior durabilidade com uso correto. "
            "Desvantagens: condução mais dura (especialmente veículos leves) e custo mais alto. "
            "Nem todos os pneus reforçados são Run Flat. Verifique as especificações do fabricante. "
            "Ideais para SUVs, vans, veículos elétricos e carros com carga frequente."
        )
    },
    {
        "titulo": "Cuidado e Manutenção Geral de Pneus",
        "palavras_chave": ["manutenção", "cuidado", "alinhamento", "suspensão", "desgaste", "trocar", "vida útil", "duração", "dica"],
        "url": "https://www.conti.com.br/tire-knowledge/Conhecimentos-gerais-sobre-cuidado-e-manutencao/",
        "conteudo": (
            "Problemas de alinhamento e balanceamento causam desgaste irregular e comprometem a segurança. "
            "O balanceamento deve ser feito toda vez que pneus forem desmontados/montados. "
            "O alinhamento perde referência com impactos e buracos - deve ser verificado regularmente. "
            "Componentes da suspensão (amortecedores, molas, bandejas, buchas, pivôs, bieletas) "
            "devem ser verificados pois afetam o desgaste dos pneus. "
            "Ao trocar apenas 2 pneus: novos devem ir no eixo traseiro para estabilidade. "
            "Sempre use pneus da mesma medida, marca, modelo e condição no mesmo eixo. "
            "O rodízio regular contribui para desgaste uniforme e vida útil maior."
        )
    },
    {
        "titulo": "Dirigindo na Neblina",
        "palavras_chave": ["neblina", "névoa", "visibilidade", "fog", "noite"],
        "url": "https://www.conti.com.br/tire-knowledge/driving-in-fog/",
        "conteudo": (
            "Dirigir na neblina exige cautela. Reduza a velocidade, aumente a distância entre veículos, "
            "use faróis baixos (nunca altos na neblina pois refletem) e farol de neblina se disponível. "
            "Pneus em boas condições com banda de rodagem adequada são essenciais para manter a aderência."
        )
    },
    {
        "titulo": "Dirigindo em Curvas",
        "palavras_chave": ["curva", "curvas", "aderência", "estabilidade", "lateral", "direção"],
        "url": "https://www.conti.com.br/tire-knowledge/curvy-rides/",
        "conteudo": (
            "Em curvas, os pneus sofrem forças laterais intensas. "
            "Pneus premium oferecem melhor aderência lateral e estabilidade direcional. "
            "A qualidade da banda de rodagem e a calibragem correta são fundamentais para curvas seguras."
        )
    },
    {
        "titulo": "Viajando com Crianças e Pets",
        "palavras_chave": ["viagem", "criança", "pet", "animal", "família", "segurança", "longa distância"],
        "url": "https://www.conti.com.br/tire-knowledge/ultimate-guide-travelling-with-kids-and-pets/",
        "conteudo": (
            "Antes de viajar com crianças e animais, verifique a calibragem e condição dos pneus. "
            "Peso extra (malas, passageiros) exige atenção especial à pressão dos pneus. "
            "Faça paradas regulares e verifique os pneus durante viagens longas."
        )
    },
]


from typing import List, Dict, Tuple


def buscar_conhecimento(pergunta: str, max_resultados: int = 3) -> str:
    """
    Busca na base de conhecimento por trechos relevantes à pergunta do usuário.
    Retorna os trechos mais relevantes formatados como contexto para o agente.
    """
    pergunta_lower: str = pergunta.lower()
    resultados: List[Tuple[int, Dict[str, object]]] = []

    for artigo in KNOWLEDGE_BASE:
        score: int = 0
        palavras_chave = artigo["palavras_chave"]
        titulo = artigo["titulo"]

        if isinstance(palavras_chave, list):
            for palavra in palavras_chave:
                if isinstance(palavra, str) and palavra.lower() in pergunta_lower:
                    score += 2
                if isinstance(palavra, str):
                    for word in pergunta_lower.split():
                        if len(word) > 3 and word in palavra.lower():
                            score += 1

        if isinstance(titulo, str):
            for word in pergunta_lower.split():
                if len(word) > 3 and word in titulo.lower():
                    score += 1

        if score > 0:
            resultados.append((score, artigo))

    resultados.sort(key=lambda x: x[0], reverse=True)

    if not resultados:
        return ""

    output: str = "INFORMAÇÕES DA BASE DE CONHECIMENTO:\n\n"
    top_results = resultados[:max_resultados]
    for item in top_results:
        art = item[1]
        output += f"📚 {art.get('titulo', '')}\n"
        output += f"{art.get('conteudo', '')}\n"
        output += f"Fonte: {art.get('url', '')}\n\n"

    return output


def popula_lancedb():
    """
    Popula o banco de dados vetorial LanceDB com os artigos da KNOWLEDGE_BASE.
    Isso deve ser executado uma vez para inicializar o RAG do Agno.
    """
    from agno.knowledge import Knowledge
    from agno.vectordb.lancedb import LanceDb
    from agno.knowledge.embedder.openai import OpenAIEmbedder
    from agno.knowledge.document import Document

    print("Iniciando população do LanceDB...")
    
    # Criar listas para insert_many
    text_contents = []
    for art in KNOWLEDGE_BASE:
        content = f"Título: {art['titulo']}\nConteúdo: {art['conteudo']}\nURL: {art['url']}"
        text_contents.append(content)
    
    # Configurar base de conhecimento
    kb = Knowledge(
        vector_db=LanceDb(
            table_name="conhecimento_pneus",
            uri="lancedb_storage",
            embedder=OpenAIEmbedder(id="text-embedding-3-small")
        )
    )
    
    # Carregar documentos usando insert_many
    kb.insert_many(text_contents=text_contents, upsert=True)
    print("LanceDB populado com sucesso!")

if __name__ == "__main__":
    # Script para rodar manualmente e popular o banco
    import os
    # Certifique-se de que a API KEY está no ambiente
    if "OPENAI_API_KEY" not in os.environ:
        print("ERRO: OPENAI_API_KEY não encontrada no ambiente.")
    else:
        popula_lancedb()
