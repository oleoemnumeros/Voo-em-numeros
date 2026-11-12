"""Sonda as fontes de dados de voos da ANAC e imprime o que encontrar.

Uso único, para descobrir onde e em que formato a base VRA está publicada.
"""
import re
import sys
import urllib.parse

import requests

UA = {"User-Agent": "Mozilla/5.0 (voo-em-numeros sonda)"}
CANDIDATOS = [
    "https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/",
    "https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/Voo%20Regular%20Ativo%20%28VRA%29/",
    "https://siros.anac.gov.br/siros/registros/diversos/vra/",
    "https://www.gov.br/anac/pt-br/acesso-a-informacao/dados-abertos/areas-de-atuacao/voos-e-operacoes-aereas/voo-regular-ativo-vra",
    "https://www.gov.br/anac/pt-br/acesso-a-informacao/dados-abertos/areas-de-atuacao/voos-e-operacoes-aereas",
]


def links(html, base):
    out = []
    for href in re.findall(r'href="([^"]+)"', html, flags=re.I):
        if href.startswith(("?", "#", "mailto:", "javascript:")):
            continue
        out.append(urllib.parse.urljoin(base, href))
    return out


def get(url, stream=False):
    try:
        r = requests.get(url, headers=UA, timeout=60, stream=stream)
        return r
    except Exception as e:  # noqa: BLE001
        print(f"  ERRO {url}: {e}")
        return None


def mostrar_arquivo(url):
    r = get(url, stream=True)
    if r is None:
        return
    print(f"\n### ARQUIVO {url} -> {r.status_code} {r.headers.get('content-type')} {r.headers.get('content-length')}")
    if r.status_code != 200:
        return
    bruto = b""
    for pedaco in r.iter_content(4096):
        bruto += pedaco
        if len(bruto) > 6000:
            break
    for cod in ("utf-8-sig", "latin-1"):
        try:
            texto = bruto.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    print("\n".join(texto.splitlines()[:12]))


def main():
    vistos = set()
    fila = [(u, 0) for u in CANDIDATOS]
    arquivos = []
    while fila:
        url, nivel = fila.pop(0)
        if url in vistos or len(vistos) > 60:
            continue
        vistos.add(url)
        r = get(url)
        if r is None:
            continue
        print(f"\n== {url} -> {r.status_code} {r.headers.get('content-type')}")
        if r.status_code != 200 or "html" not in (r.headers.get("content-type") or ""):
            continue
        ls = links(r.text, url)
        relevantes = [l for l in ls if re.search(r"vra|voo|dadosabertos|\.csv|\.zip|\.json|\.xlsx", l, re.I)]
        for l in relevantes[:80]:
            print("   ", l)
        for l in relevantes:
            if re.search(r"\.(csv|zip|json|txt)$", l, re.I):
                arquivos.append(l)
            elif nivel < 2 and l.endswith("/") and l.startswith(url) and l != url:
                fila.append((l, nivel + 1))
    print("\n\n######## ARQUIVOS ENCONTRADOS:", len(arquivos))
    for a in arquivos[-40:]:
        print(a)
    # mostra o cabeçalho dos 2 arquivos mais recentes (pela ordem da listagem)
    for a in [x for x in arquivos if x.lower().endswith(".csv")][-2:]:
        mostrar_arquivo(a)


if __name__ == "__main__":
    sys.exit(main())
