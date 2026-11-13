"""Sonda temporária: onde estão os dados de reclamações de companhias aéreas?"""
import re, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; vooemnumeros-sonda)"}
PAGS = [
    "https://www.consumidor.gov.br/pages/dadosabertos/externo/",
    "https://www.gov.br/anac/pt-br/assuntos/passageiros/anac_passageiro",
    "https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/mercado-do-transporte-aereo",
    "https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas",
    "https://dados.gov.br/dados/conjuntos-dados?termo=reclama%C3%A7%C3%B5es%20anac",
    "https://dadosabertos.anac.gov.br/dataset?q=reclama",
    "https://dadosabertos.anac.gov.br/api/3/action/package_search?q=reclama",
    "https://dados.mj.gov.br/dataset/reclamacoes-do-consumidor-gov-br",
]
for u in PAGS:
    try:
        r = requests.get(u, headers=H, timeout=60)
        t = r.text
        print("\n##", r.status_code, u, len(t), r.headers.get("content-type"))
        links = sorted(set(re.findall(r'href="([^"]+)"', t)))
        keep = [l for l in links if re.search(r"(csv|zip|xlsx|json|painel|powerbi|looker|datastudio|reclama|dados|passageiro)", l, re.I)]
        for l in keep[:40]:
            print("  ", l[:200])
        for m in re.findall(r'(?:powerbi\.com|lookerstudio\.google\.com|app\.powerbi)[^"\' <]{0,200}', t)[:5]:
            print("  PAINEL:", m)
        if "api/3" in u:
            print(t[:1500])
    except Exception as e:
        print("\n##", "ERRO", u, str(e)[:150])
