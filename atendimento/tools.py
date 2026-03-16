from .scraper import buscar_pneus_no_site

def buscar_pneus(marca: str, modelo: str, ano: str, versao: str, aro: str) -> str:
    """
    Busca pneus no catálogo da HC Pneus com base nas informações do veículo.
    
    Args:
        marca: Marca do veículo (ex: Nissan).
        modelo: Modelo do veículo (ex: March).
        ano: Ano do veículo (ex: 2015).
        versao: Versão do veículo (ex: 1.0 S).
        aro: Aro do pneu (ex: 14).
        
    Returns:
        Uma lista formatada de pneus encontrados ou uma mensagem de erro.
    """
    print(f"DEBUG: Tool buscar_pneus chamada com: {marca}, {modelo}, {ano}, {versao}, {aro}")
    try:
        results = buscar_pneus_no_site(marca, modelo, ano, versao, aro)
        if not results:
            return f"Não encontrei pneus para {marca} {modelo} {ano} {versao} aro {aro} no momento."
        
        output = f"Encontrei as seguintes opções para o {marca} {modelo} {ano} {versao} (aro {aro}):\n"
        for p in results:
            output += f"- {p['nome_modelo']} | Preço: {p['preco']}\n"
        
        output += "\nComo o senhor gostaria de prosseguir? Deseja reservar algum?"
        return output
    except Exception as e:
        return f"Erro ao consultar o catálogo: {str(e)}"
