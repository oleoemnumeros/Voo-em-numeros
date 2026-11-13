import re, requests
H = {"User-Agent": "Mozilla/5.0 (compatible; vooemnumeros-sonda)"}
def txt(t): return re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", t, flags=re.S))
for u in ["https://www.gov.br/anac/pt-br/assuntos/passageiros/desempenho-das-empresas",
          "https://www.gov.br/anac/pt-br/noticias/2026/nova-plataforma-da-anac-supera-4-mil-reclamacoes-finalizadas-nos-primeiros-60-dias"]:
    r = requests.get(u, headers=H, timeout=60); t = r.text
    print("\n##", r.status_code, u, len(t))
    i = t.find("<main"); body = t[i:] if i > 0 else t
    print("TEXTO:", txt(body)[:2500])
    for l in sorted(set(re.findall(r'(?:href|src)="([^"]+)"', t))):
        if re.search(r"(powerbi|looker|datastudio|\.csv|\.xlsx|\.zip|\.json|painel|iframe|api|dados-abertos|boletim|desempenho)", l, re.I) and "share" not in l:
            print("  LINK", l[:220])
    for m in re.findall(r"<iframe[^>]+>", t)[:5]: print("  IFRAME", m[:300])
r = requests.get("https://www.consumidor.gov.br/pages/dadosabertos/externo/", headers=H, timeout=60); t = r.text
print("\n## consumidor dados abertos")
for m in re.finditer(r"publicacoesDT|ajax|\.csv|\.zip|Download|download", t):
    print("  ", t[max(0, m.start()-120):m.end()+200].replace("\n", " ")[:330]); 
    if m.start() > 15000: break
