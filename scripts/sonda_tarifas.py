"""SONDA TEMPORÁRIA 4: estrutura do formulário DataSAS."""
import re, time
import requests

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (vooemnumeros sonda)"
U = "https://sas.anac.gov.br/sas/downloads/view/frmDownload.aspx"
r = S.get(U, timeout=60)
t = r.text
body = t[t.find("<form"):]
body = re.sub(r'(__VIEWSTATE|__EVENTVALIDATION)" value="[^"]{40,}"', r'\1" value="..."', body)
body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
body = re.sub(r'<img[^>]*>', "", body)
print(body[:6000])
