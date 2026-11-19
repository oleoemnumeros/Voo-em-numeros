"""SONDA TEMPORÁRIA 2: acha os microdados de tarifas da ANAC."""
import re, time, urllib.parse
import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (vooemnumeros sonda)"


def get(url, **kw):
    for i in range(5):
        try:
            return S.get(url, timeout=60, **kw)
        except requests.RequestException as e:
            print("  falha", i, type(e).__name__, str(e)[:100])
            time.sleep(4)


def mostra(url, n=3000):
    print("\n=====", url)
    r = get(url)
    if r is None:
        print("sem resposta"); return None
    print(r.status_code, r.headers.get("content-type"), len(r.text), "->", r.url)
    t = r.text
    hs = re.findall(r'(?:href|src|action)="([^"]+)"', t)
    for h in hs:
        if re.search(r"arifa|download|csv|zip|xlsx|\.php|\.jsp|\.asp|sas|sistemas", h, re.I):
            print("  link:", urllib.parse.urljoin(r.url, h))
    txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", txt)
    print(re.sub(r"\s+", " ", txt)[:n])
    return r


mostra("https://sas.anac.gov.br/sas/downloads/")
mostra("https://sas.anac.gov.br/sas/downloads/view/frmDownload.aspx")
mostra("https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/mercado-do-transporte-aereo/tarifas-aereas")
mostra("https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/mercado-do-transporte-aereo/tarifas-aereas/tarifas-aereas-domesticas")
mostra("https://www.gov.br/anac/pt-br/acesso-a-informacao/dados-abertos/areas-de-atuacao/voos-e-operacoes-aereas/tarifas-aereas-domesticas")
mostra("https://dados.gov.br/dados/conjuntos-dados/tarifas-aereas-domesticas")
