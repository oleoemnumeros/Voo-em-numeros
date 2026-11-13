"""Sonda temporária 2: cabeçalho completo, valores de NATUREZA/GRUPO e últimos meses."""
import csv, io, requests
from collections import Counter, defaultdict
U = "https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/Dados%20Estat%C3%ADsticos%20do%20Transporte%20A%C3%A9reo/Dados_Estatisticos.csv"
import os, time
ARQ = "/tmp/de.csv"
total = int(requests.head(U, timeout=60, allow_redirects=True).headers.get("content-length", 0))
print("tamanho esperado", total)
tent = 0
while (os.path.getsize(ARQ) if os.path.exists(ARQ) else 0) < total and tent < 40:
    tent += 1
    ja = os.path.getsize(ARQ) if os.path.exists(ARQ) else 0
    try:
        rr = requests.get(U, headers={"Range": f"bytes={ja}-"}, timeout=120, stream=True)
        if rr.status_code not in (200, 206):
            print("status", rr.status_code); time.sleep(5); continue
        modo = "ab" if rr.status_code == 206 else "wb"
        with open(ARQ, modo) as f:
            for ch in rr.iter_content(1 << 20):
                f.write(ch)
    except Exception as e:
        print("tentativa", tent, "falhou:", str(e)[:120]); time.sleep(3)
print("baixado", os.path.getsize(ARQ), "em", tent, "tentativas")
fh = open(ARQ, encoding="utf-8-sig", errors="replace")
fh.readline()  # "Atualizado em"
rd = csv.DictReader(fh, delimiter=";")
print("COLUNAS:", rd.fieldnames)
nat, grp, meses, tot = Counter(), Counter(), defaultdict(lambda: Counter()), 0
amostra = []
for row in rd:
    tot += 1
    nat[row["NATUREZA"]] += 1; grp[row["GRUPO_DE_VOO"]] += 1
    a, m = int(row["ANO"]), int(row["MES"])
    if (a, m) >= (2025, 6) and row["NATUREZA"] == "DOMÉSTICA":
        k = f"{a}-{m:02d}"
        meses[k]["linhas"] += 1
        for c in ("PASSAGEIROS_PAGOS", "ASK", "RPK", "DECOLAGENS", "ASSENTOS"):
            v = (row.get(c) or "").replace(",", ".")
            try: meses[k][c] += float(v)
            except ValueError: pass
        if k == "2026-08" and len(amostra) < 4 and row["GRUPO_DE_VOO"] == "REGULAR":
            amostra.append(dict(row))
print("LINHAS", tot)
print("NATUREZA", dict(nat)); print("GRUPO", dict(grp))
for k in sorted(meses): print(k, {c: round(v) for c, v in meses[k].items()})
for a in amostra: print("AMOSTRA", a)
