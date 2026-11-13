"""Baixa a base "Dados Estatísticos do Transporte Aéreo" da ANAC e grava data/demanda.json.

A base tem uma linha por empresa, rota e mês desde 2000 (cerca de 360 MB). Guardamos só voos
domésticos regulares: o total nacional por mês desde 2015 e as linhas por empresa e rota desde dez/2024.
O download retoma de onde parou, porque o servidor da ANAC derruba a conexão com frequência.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "demanda.json"
TMP = Path("/tmp/dados_estatisticos.csv")
URL = ("https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/"
       "Dados%20Estat%C3%ADsticos%20do%20Transporte%20A%C3%A9reo/Dados_Estatisticos.csv")
INICIO_LINHAS = (2024, 12)
INICIO_MENSAL = 2015
DIAS_ENTRE_DOWNLOADS = 6
CAMPOS = ("PASSAGEIROS_PAGOS", "ASK", "RPK", "DECOLAGENS", "ASSENTOS")


def atualizado_remoto() -> str | None:
    try:
        r = requests.get(URL, headers={"Range": "bytes=0-200"}, timeout=60)
        m = re.search(r"Atualizado em:\s*(\d{4}-\d{2}-\d{2})", r.content.decode("utf-8-sig", "replace"))
        return m.group(1) if m else None
    except requests.RequestException:
        return None


def baixar() -> None:
    total = int(requests.head(URL, timeout=60, allow_redirects=True).headers.get("content-length", 0))
    if total < 100_000_000:
        sys.exit(f"Tamanho inesperado do arquivo da ANAC: {total}")
    if TMP.exists():
        TMP.unlink()
    tentativas = 0
    while (TMP.stat().st_size if TMP.exists() else 0) < total:
        tentativas += 1
        if tentativas > 40:
            sys.exit("Download da base de demanda não terminou depois de 40 tentativas.")
        ja = TMP.stat().st_size if TMP.exists() else 0
        try:
            r = requests.get(URL, headers={"Range": f"bytes={ja}-"}, timeout=120, stream=True)
            if r.status_code not in (200, 206):
                time.sleep(5)
                continue
            with open(TMP, "ab" if r.status_code == 206 else "wb") as f:
                for ch in r.iter_content(1 << 20):
                    f.write(ch)
        except requests.RequestException as e:
            print(f"tentativa {tentativas} falhou: {str(e)[:100]}")
            time.sleep(3)
    print(f"Baixado: {TMP.stat().st_size / 1e6:.0f} MB em {tentativas} tentativa(s)")


def num(v: str) -> int:
    try:
        return int(round(float(v.replace(",", "."))))
    except ValueError:
        return 0


def resumir(atualizado: str | None) -> dict:
    mensal = defaultdict(lambda: [0] * len(CAMPOS))
    linhas = defaultdict(lambda: defaultdict(lambda: [0] * len(CAMPOS)))
    with open(TMP, encoding="utf-8-sig", errors="replace", newline="") as f:
        f.readline()  # "Atualizado em: ..."
        rd = csv.reader(f, delimiter=";")
        cab = next(rd)
        ix = {c: i for i, c in enumerate(cab)}
        falta = [c for c in ("EMPRESA_SIGLA", "ANO", "MES", "AEROPORTO_DE_ORIGEM_SIGLA", "AEROPORTO_DE_DESTINO_SIGLA",
                             "NATUREZA", "GRUPO_DE_VOO") + CAMPOS if c not in ix]
        if falta:
            sys.exit(f"Colunas ausentes na base da ANAC: {falta}")
        i_nat, i_grp, i_ano, i_mes = ix["NATUREZA"], ix["GRUPO_DE_VOO"], ix["ANO"], ix["MES"]
        i_emp, i_o, i_d = ix["EMPRESA_SIGLA"], ix["AEROPORTO_DE_ORIGEM_SIGLA"], ix["AEROPORTO_DE_DESTINO_SIGLA"]
        i_c = [ix[c] for c in CAMPOS]
        for r in rd:
            if len(r) <= max(i_c) or r[i_nat] != "DOMÉSTICA" or r[i_grp] != "REGULAR":
                continue
            ano, mes = int(r[i_ano]), int(r[i_mes])
            if ano < INICIO_MENSAL:
                continue
            vals = [num(r[i]) for i in i_c]
            chave = f"{ano}-{mes:02d}"
            acc = mensal[chave]
            for k, v in enumerate(vals):
                acc[k] += v
            if (ano, mes) >= INICIO_LINHAS and r[i_o] and r[i_d]:
                acc2 = linhas[chave][(r[i_emp], r[i_o], r[i_d])]
                for k, v in enumerate(vals):
                    acc2[k] += v
    return {
        "atualizado_em": atualizado,
        "baixado_em": dt.date.today().isoformat(),
        "campos": ["passageiros", "ask", "rpk", "decolagens", "assentos"],
        "mensal": {m: v for m, v in sorted(mensal.items())},
        "linhas": {m: [[e, o, d, *v] for (e, o, d), v in sorted(t.items())] for m, t in sorted(linhas.items())},
    }


def valida(d: dict) -> None:
    ult = max(d["mensal"])
    pax = d["mensal"][ult][0]
    if not 4_000_000 <= pax <= 15_000_000:
        sys.exit(f"Passageiros de {ult} fora do esperado: {pax}")
    if len(d["linhas"][max(d["linhas"])]) < 500:
        sys.exit("Poucas rotas no último mês da base de demanda.")


def main() -> int:
    forcar = os.environ.get("FORCAR") == "1"
    atual = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else {}
    remoto = atualizado_remoto()
    if atual and not forcar:
        dias = (dt.date.today() - dt.date.fromisoformat(atual.get("baixado_em", "2000-01-01"))).days
        if remoto and remoto == atual.get("atualizado_em") or dias < DIAS_ENTRE_DOWNLOADS:
            print(f"Demanda em dia (base de {atual.get('atualizado_em')}, baixada há {dias} dias).")
            return 0
    baixar()
    d = resumir(remoto)
    valida(d)
    SAIDA.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ult = max(d["mensal"])
    print(f"Demanda gravada até {ult}: {d['mensal'][ult][0]:,} passageiros; {sum(len(v) for v in d['linhas'].values())} linhas.")
    TMP.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
