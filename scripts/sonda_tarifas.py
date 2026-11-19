"""SONDA TEMPORÁRIA 7: baixa um arquivo de tarifas domésticas do DataSAS e mostra colunas."""
import csv, html, io, re, zipfile
import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (vooemnumeros sonda)"
U = "https://sas.anac.gov.br/sas/downloads/view/frmDownload.aspx"


def campos(t):
    d = {}
    for m in re.finditer(r"<input[^>]*>", t):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        if not n:
            continue
        ty = re.search(r'type="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        d[n.group(1)] = (ty.group(1) if ty else "text", html.unescape(v.group(1)) if v else "")
    for m in re.finditer(r'<select name="([^"]+)".*?</select>', t, flags=re.S):
        opts = re.findall(r'<option( selected="selected")? value="([^"]*)">', m.group(0))
        d[m.group(1)] = ("select", next((o[1] for o in opts if o[0]), opts[0][1] if opts else ""))
    return d


def post(t, alvo, extra):
    d = {k: v[1] for k, v in campos(t).items() if v[0] not in ("submit", "button", "checkbox")}
    d.update(extra)
    d["__EVENTTARGET"] = alvo
    return S.post(U, data=d, timeout=180)


def lista(ano):
    r = S.get(U, timeout=60)
    r2 = post(r.text, "ctl00$MainContent$listTema", {"ctl00$MainContent$listTema": "14"})
    r3 = post(r2.text, "", {"ctl00$MainContent$listTema": "14", "ctl00$MainContent$listAno": str(ano),
                            "ctl00$MainContent$btnListaArquivos": "Buscar Arquivos"})
    pad = (r'name="(ctl00\$MainContent\$gridArquivos\$ctl\d+\$chkDownload)".*?<td[^>]*>([^<]*)</td><td[^>]*>([^<]*)</td>'
           r'<td[^>]*>(\d+)</td><td[^>]*>(\d+)</td><td[^>]*>([^<]*)</td>')
    return r3, re.findall(pad, r3.text, flags=re.S)


r3, ls = lista(2026)
print("2026:", [(a[1], a[2], a[4], a[5]) for a in ls])
_, ls5 = lista(2025)
print("2025:", [(a[1], a[4], a[5]) for a in ls5])
alvo = ls[-1]
print("baixando", alvo[1])
rr = post(r3.text, "", {"ctl00$MainContent$listTema": "14", "ctl00$MainContent$listAno": "2026", alvo[0]: "on",
                        "ctl00$MainContent$btnBaixar": "Baixar Marcados"})
print(rr.status_code, rr.headers.get("content-type"), rr.headers.get("content-disposition"), len(rr.content))
dados = rr.content
z = zipfile.ZipFile(io.BytesIO(dados))
nome = [n for n in z.namelist() if n.startswith("202610")][0]
raw = z.read(nome)
print("membro", nome, len(raw), "bytes")
txt = raw.decode("latin-1")
linhas = txt.splitlines()
print("linhas:", len(linhas))
for l in linhas[:6]:
    print(l)
from collections import Counter, defaultdict
emp = Counter(); rotas = defaultdict(lambda: [0, 0.0]); tmin, tmax = 1e9, 0
for l in linhas[1:]:
    a = l.split(";")
    if len(a) < 7:
        continue
    try:
        t = float(a[5].replace(",", ".")); q = int(a[6])
    except ValueError:
        continue
    emp[a[2]] += q
    rotas[(a[3], a[4])][0] += q
    rotas[(a[3], a[4])][1] += t * q
    tmin = min(tmin, t); tmax = max(tmax, t)
print("empresas:", emp.most_common(12))
print("rotas:", len(rotas), "assentos totais:", sum(v[0] for v in rotas.values()))
tot = sum(v[1] for v in rotas.values()) / sum(v[0] for v in rotas.values())
print("tarifa média nominal (ponderada):", round(tot, 2), "min", tmin, "max", tmax)
for k in [("SBSV", "SBGR"), ("SBSV", "SBSP"), ("SBGR", "SBSV"), ("SBSP", "SBRJ"), ("SBSV", "SBRF")]:
    v = rotas.get(k)
    print(k, v and (v[0], round(v[1] / v[0], 2)))
# distribuição SSA-GRU
dist = Counter()
for l in linhas[1:]:
    a = l.split(";")
    if len(a) >= 7 and a[3] == "SBSV" and a[4] == "SBGR":
        dist[round(float(a[5].replace(",", ".")) / 100) * 100] += int(a[6])
print("SSA→GRU por faixa de R$100:", sorted(dist.items()))
r = requests.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial=01/09/2025", timeout=60)
print("IPCA BCB:", r.status_code, r.text[:600])
