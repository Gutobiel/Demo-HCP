from atendimento.scraper import buscar_pneus_no_site
import json

if __name__ == "__main__":
    print("Testando scraper isoladamente...")
    res = buscar_pneus_no_site("Corolla", "2018", "16")
    print(json.dumps(res, indent=2))
