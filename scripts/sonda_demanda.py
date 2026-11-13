"""Sonda temporária: baixa a base Dados Estatísticos da ANAC e mostra colunas e amostra."""
import re, sys, requests

URLS = [
    "https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/Dados%20Estat%C3%ADsticos%20do%20Transporte%20A%C3%A9reo/Dados_Estatisticos.csv",
    "https://dadosabertos.anac.gov.br/dataset/dados-estatisticos-do-transporte-aereo",
]
PAGINAS = [
    "https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/mercado-do-transporte-aereo/demanda-e-oferta",
    "https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/dados-estatisticos",
]
for u in PAGINAS:
    try:
        r = requests.get(u, timeout=60)
        print("PAGINA", r.status_code, u, len(r.text))
        for l in sorted(set(re.findall(r'href="([^"]+\.(?:csv|zip|xlsx)[^"]*)"', r.text)))[:15]:
            print("  link:", l)
    except Exception as e:
        print("PAGINA ERRO", u, e)
for u in URLS:
    try:
        r = requests.get(u, timeout=180, stream=True)
        print("URL", r.status_code, r.headers.get("content-type"), r.headers.get("content-length"), u)
        if r.status_code == 200 and "csv" in (r.headers.get("content-type", "") + u).lower():
            tot, linhas, buf = 0, [], b""
            for ch in r.iter_content(65536):
                buf += ch
                tot += len(ch)
                if buf.count(b"\n") > 12:
                    break
            for enc in ("utf-8", "latin-1"):
                try:
                    txt = buf.decode(enc); print("codificação:", enc); break
                except UnicodeDecodeError:
                    continue
            for l in txt.splitlines()[:8]:
                print("  |", l[:600])
        elif r.status_code == 200:
            for l in sorted(set(re.findall(r'href="([^"]+\.(?:csv|zip|xlsx)[^"]*)"', r.text)))[:15]:
                print("  link:", l)
    except Exception as e:
        print("URL ERRO", u, e)
