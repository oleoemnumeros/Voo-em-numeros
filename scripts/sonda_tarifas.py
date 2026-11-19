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
if dados[:2] == b"PK":
    z = zipfile.ZipFile(io.BytesIO(dados))
    print(z.namelist())
    dados = z.read(z.namelist()[0])
txt = dados.decode("latin-1")
linhas = txt.splitlines()
print("linhas:", len(linhas))
for l in linhas[:8]:
    print(l[:300])
for l in linhas[1:]:
    if "SBSV" in l and "SBGR" in l:
        print("exemplo SSA-GRU:", l)
        break
n = sum(1 for l in linhas if "SBSV" in l.split(";")[:6] and "SBGR" in l.split(";")[:6])
print("linhas SBSV x SBGR:", n)
