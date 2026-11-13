import re, time, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; vooemnumeros-sonda)"}
def get(u):
    for i in range(5):
        try: return requests.get(u, headers=H, timeout=60)
        except Exception as e:
            print("retry", i, str(e)[:80]); time.sleep(5)
def txt(t): return re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", t, flags=re.S))
u = "https://www.gov.br/anac/pt-br/assuntos/passageiros/anac_passageiro/desempenho-das-empresas"
r = get(u)
if r is None: raise SystemExit("falhou")
t = r.text
print("##", r.status_code, u, len(t))
i = t.find('id="content"'); 
print("TEXTO:", txt(t[i:] if i > 0 else t)[:2200])
for m in re.findall(r"<iframe[^>]+>", t)[:5]: print("IFRAME", m[:400])
for l in sorted(set(re.findall(r'(?:href|src|data-[a-z-]+)="([^"]+)"', t))):
    if re.search(r"(powerbi|looker|datastudio|\.csv|\.xlsx|\.zip|\.json|painel|bi\.|qlik|tableau|api|dados)", l, re.I) and "share" not in l:
        print("LINK", l[:260])
