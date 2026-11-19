"""SONDA TEMPORÁRIA 5: navega o DataSAS (WebForms) até o arquivo de tarifas domésticas."""
import re, time, html
import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (vooemnumeros sonda)"
U = "https://sas.anac.gov.br/sas/downloads/view/frmDownload.aspx"


def campos(t):
    d = {}
    for m in re.finditer(r'<input[^>]*>', t):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        if not n:
            continue
        ty = re.search(r'type="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        d[n.group(1)] = (ty.group(1) if ty else "text", html.unescape(v.group(1)) if v else "")
    for m in re.finditer(r'<select name="([^"]+)".*?</select>', t, flags=re.S):
        opts = re.findall(r'<option( selected="selected")? value="([^"]*)">([^<]*)</option>', m.group(0))
        sel = next((o[1] for o in opts if o[0]), opts[0][1] if opts else "")
        d[m.group(1)] = ("select", sel, [(o[1], html.unescape(o[2])) for o in opts])
    return d


def mostra(t, titulo):
    print("\n#####", titulo)
    for k, v in campos(t).items():
        if k.startswith("__") and k not in ("__EVENTTARGET",):
            continue
        print(" ", k, v[:2] if v[0] != "select" else (v[1], v[2]))
    for m in re.finditer(r'<(?:input|a|button)[^>]*(?:Button|btn|Download|lnk)[^>]*>', t, flags=re.I):
        print("  botão:", m.group(0)[:300])
    msgs = re.findall(r'id="MainContent_(?:ErrorMessage|SuccessText)"[^>]*>([^<]*)<', t)
    print("  msgs:", msgs)


def post(t, alvo, extra):
    d = {k: v[1] for k, v in campos(t).items() if v[0] != "submit" and v[0] != "button"}
    d.update(extra)
    d["__EVENTTARGET"] = alvo
    return S.post(U, data=d, timeout=120)


r = S.get(U, timeout=60)
mostra(r.text, "inicial")
r2 = post(r.text, "ctl00$MainContent$listTema", {"ctl00$MainContent$listTema": "14"})
mostra(r2.text, "depois de escolher tema 14")
i = r2.text.find("listAno")
print(re.sub(r"\s+", " ", r2.text[i - 200:i + 3500]))
