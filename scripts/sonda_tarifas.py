"""SONDA TEMPORÁRIA 3."""
import re, time, urllib.parse
import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (vooemnumeros sonda)"


def get(url, **kw):
    for i in range(6):
        try:
            r = S.get(url, timeout=90, **kw)
            if r.status_code == 200 and len(r.text) > 2000 or kw.get("stream"):
                return r
        except requests.RequestException as e:
            print("  falha", i, type(e).__name__)
        time.sleep(4)


u = "https://www.gov.br/anac/pt-br/assuntos/dados-e-estatisticas/microdados-de-tarifas-aereas-comercializadas"
r = get(u)
print(r.status_code if r else None)
t = r.text
i = t.find("documentContent")
body = t
for h in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, flags=re.S):
    href, txt = h
    txt = re.sub(r"<[^>]+>", "", txt).strip()
    if re.search(r"csv|zip|xls|download|sas\.|sistemas|tarifa|microdado|\d{4}", href + txt, re.I) and "share" not in href and "whatsapp" not in href:
        print(" ", txt[:80], "|", urllib.parse.urljoin(u, href))
txt = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
txt = re.sub(r"<[^>]+>", " ", txt)
txt = re.sub(r"\s+", " ", txt)
k = txt.find("Microdados")
print(txt[k:k + 2500])
