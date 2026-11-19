"""SONDA TEMPORÁRIA: acha os microdados de tarifas da ANAC e mostra colunas e tamanho."""
import re, sys, time, urllib.parse
import requests

BASE = "https://sistemas.anac.gov.br/dadosabertos/"
S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (vooemnumeros sonda)"


def get(url, **kw):
    for i in range(5):
        try:
            r = S.get(url, timeout=60, **kw)
            return r
        except requests.RequestException as e:
            print("  falha", i, type(e).__name__, str(e)[:100])
            time.sleep(4)
    return None


def links(url):
    r = get(url)
    if not r or r.status_code != 200:
        print("  sem acesso:", url, r.status_code if r else None)
        return []
    hs = re.findall(r'href="([^"]+)"', r.text)
    return [urllib.parse.urljoin(url, h) for h in hs if not h.startswith(("?", "#", "javascript")) and "Parent" not in h]


print("== raiz")
for l in links(BASE)[:60]:
    print(" ", urllib.parse.unquote(l))
voos = [l for l in links(BASE) if "Voos" in urllib.parse.unquote(l)]
achados = []
for v in voos[:1]:
    print("== ", urllib.parse.unquote(v))
    for l in links(v):
        print("  ", urllib.parse.unquote(l))
        if "arifa" in urllib.parse.unquote(l):
            achados.append(l)
for a in achados:
    print("== tarifas:", urllib.parse.unquote(a))
    sub = links(a)
    for l in sub[:80]:
        print("  ", urllib.parse.unquote(l))
        for l2 in links(l)[:40] if l.endswith("/") else []:
            print("     ", urllib.parse.unquote(l2))
print("== sas/downloads")
r = get("https://sistemas.anac.gov.br/sas/downloads/")
print(r.status_code if r else None, (r.text[:1500] if r else ""))
