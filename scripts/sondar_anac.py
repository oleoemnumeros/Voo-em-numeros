"""Sonda 2: estatísticas de um mês do VRA para decidir filtros e fuso."""
import collections
import csv
import io

import requests

UA = {"User-Agent": "Mozilla/5.0 (voo-em-numeros sonda)"}
for ano, mes in ((2026, 9), (2025, 12), (2024, 1)):
    url = f"https://siros.anac.gov.br/siros/registros/diversos/vra/{ano}/VRA_{ano}_{mes:02d}.csv"
    r = requests.get(url, headers=UA, timeout=120)
    print("\n=====", url, r.status_code, len(r.content))
    if r.status_code != 200:
        continue
    txt = r.content.decode("utf-8-sig", errors="replace")
    linhas = txt.splitlines()
    print("linha1:", linhas[0][:200])
    print("linha2:", linhas[1][:300])
    ini = 1 if linhas[0].lower().startswith("atualizado") else 0
    rd = csv.DictReader(io.StringIO("\n".join(linhas[ini:])), delimiter=";")
    rows = list(rd)
    print("colunas:", rd.fieldnames)
    print("linhas:", len(rows))
    c = {k: collections.Counter() for k in ("Código Tipo Linha", "Situação Voo", "Justificativa", "Situação Partida", "Situação Chegada", "Codeshare", "Referência")}
    emp = collections.Counter()
    horas = collections.Counter()
    aer = collections.Counter()
    for x in rows:
        for k in c:
            c[k][x.get(k)] += 1
        o, d = x["Sigla ICAO Aeroporto Origem"], x["Sigla ICAO Aeroporto Destino"]
        if o[:2] in ("SB", "SD", "SN", "SS", "SW", "SI", "SJ") and d[:2] in ("SB", "SD", "SN", "SS", "SW", "SI", "SJ"):
            emp[(x["Sigla ICAO Empresa Aérea"], x["Empresa Aérea"][:25], x["Código Tipo Linha"])] += 1
            if o in ("SBGR", "SBSP", "SBSV", "SBBR") and x["Código Tipo Linha"] == "N":
                horas[x["Partida Prevista"][11:13]] += 1
                aer[(o, x["Descrição Aeroporto Origem"])] += 1
    for k, v in c.items():
        print(k, v.most_common(25))
    print("empresas domésticas:", emp.most_common(40))
    print("partidas previstas por hora (GRU/CGH/SSA/BSB, tipo N):", sorted(horas.items()))
    print("descr aeroportos:", list(aer)[:4])
    # exemplos de voos domésticos para conferir horário com a vida real
    ex = [x for x in rows if x["Sigla ICAO Aeroporto Origem"] == "SBSP" and x["Sigla ICAO Aeroporto Destino"] == "SBRJ"][:6]
    for x in ex:
        print("CGH-SDU:", {k: v for k, v in x.items() if "Descrição" not in k})
    if ano != 2026:
        break
