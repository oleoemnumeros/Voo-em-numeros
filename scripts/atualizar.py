"""Robô do Voo em Números.

Baixa a base Voo Regular Ativo (VRA) da ANAC, um arquivo por mês, e guarda
um resumo por voo (companhia + número + origem + destino) em data/meses/AAAA-MM.json.
Só baixa os meses que ainda não estão salvos. O site é gerado a partir desses resumos
por scripts/gerar_site.py.

Fonte: https://siros.anac.gov.br/siros/registros/diversos/vra/AAAA/VRA_AAAA_MM.csv
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
MESES = RAIZ / "data" / "meses"
DEBUG = RAIZ / "data" / "debug.json"
URL = "https://siros.anac.gov.br/siros/registros/diversos/vra/{a}/VRA_{a}_{m:02d}.csv"
UA = {"User-Agent": "Mozilla/5.0 (compatible; VooEmNumeros/1.0; +https://vooemnumeros.com.br)"}
INICIO = (2024, 12)  # primeiro mês guardado (dá base de comparação para dezembro/2025)

# Empresas de carga que aparecem com linha doméstica "N"; ficam fora do site
CARGUEIRAS = {"SID", "BPC", "MWM", "TTL", "LTG", "TPA", "LAE", "GEC", "CLX", "GTI", "LCO", "CMA", "QTR", "DHL", "FDX", "UPS"}
BUCKETS = {"Atraso 30-60": 0, "Atraso 60-120": 1, "Atraso 120-240": 2, "Atraso > 240": 3}


def log(*a):
    print(*a, flush=True)


def baixar(ano: int, mes: int) -> bytes | None:
    url = URL.format(a=ano, m=mes)
    for tentativa in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=180)
        except requests.RequestException as e:
            log(f"  erro de rede ({e}); nova tentativa")
            time.sleep(10 * (tentativa + 1))
            continue
        if r.status_code == 404:
            return None
        if r.status_code == 200 and len(r.content) > 1_000_000:
            return r.content
        log(f"  {url} -> {r.status_code} ({len(r.content)} bytes); nova tentativa")
        time.sleep(10 * (tentativa + 1))
    raise RuntimeError(f"Não consegui baixar {url}")


def data_hora(s: str) -> dt.datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return dt.datetime.strptime(s[:16], "%d/%m/%Y %H:%M")
    except ValueError:
        return None


def brasil(desc: str) -> bool:
    return (desc or "").strip().upper().endswith("BRASIL")


def resumir(bruto: bytes, chave_mes: str) -> tuple[dict, dict]:
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("latin-1")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")
    obrig = {"Sigla ICAO Empresa Aérea", "Número Voo", "Código Tipo Linha", "Sigla ICAO Aeroporto Origem",
             "Sigla ICAO Aeroporto Destino", "Partida Prevista", "Chegada Prevista", "Chegada Real",
             "Situação Voo", "Situação Chegada"}
    faltando = obrig - set(leitor.fieldnames or [])
    if faltando:
        raise RuntimeError(f"Colunas mudaram no arquivo da ANAC; faltam: {sorted(faltando)}")

    cias, aeros = {}, {}
    # voo -> contadores
    V = defaultdict(lambda: {"prev": 0, "canc": 0, "med": 0, "pont": 0, "b": [0, 0, 0, 0], "s30": 0,
                             "spos": 0, "dprev": 0, "dreal": 0, "hora": Counter(), "modelo": Counter(),
                             "assentos": 0, "nass": 0})
    dias = defaultdict(lambda: [0, 0, 0, 0])            # dia -> prev, canc, med, pont
    dias_cia = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))
    aero_dia = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))  # partidas por aeroporto
    rota_sem = defaultdict(lambda: [[0, 0] for _ in range(7)])         # rota -> dia da semana -> med, pont
    dbg = Counter()

    for x in leitor:
        dbg["linhas"] += 1
        if (x.get("Código Tipo Linha") or "").strip() != "N":
            continue
        cia = (x.get("Sigla ICAO Empresa Aérea") or "").strip()
        o = (x.get("Sigla ICAO Aeroporto Origem") or "").strip()
        d = (x.get("Sigla ICAO Aeroporto Destino") or "").strip()
        if not cia or cia in CARGUEIRAS or "CARG" in (x.get("Empresa Aérea") or "").upper():
            dbg["carga"] += 1
            continue
        if not (brasil(x.get("Descrição Aeroporto Origem")) and brasil(x.get("Descrição Aeroporto Destino"))):
            dbg["fora_do_brasil"] += 1
            continue
        pp = data_hora(x.get("Partida Prevista"))
        cp = data_hora(x.get("Chegada Prevista"))
        if not pp or not cp:
            dbg["sem_previsto"] += 1
            continue
        if pp.strftime("%Y-%m") != chave_mes:
            dbg["outro_mes"] += 1
        dbg["domesticos"] += 1
        cias[cia] = (x.get("Empresa Aérea") or cia).strip()
        aeros.setdefault(o, (x.get("Descrição Aeroporto Origem") or "").strip())
        aeros.setdefault(d, (x.get("Descrição Aeroporto Destino") or "").strip())
        num = (x.get("Número Voo") or "").strip().lstrip("0") or "0"
        v = V[(cia, num, o, d)]
        v["prev"] += 1
        v["hora"][pp.strftime("%H:%M")] += 1
        mod = (x.get("Modelo Equipamento") or "").strip()
        if mod:
            v["modelo"][mod] += 1
        try:
            a = int(x.get("Número de Assentos") or 0)
            if a > 0:
                v["assentos"] += a
                v["nass"] += 1
        except ValueError:
            pass
        dia = pp.strftime("%Y-%m-%d")
        sit = (x.get("Situação Voo") or "").strip().upper()
        if sit == "CANCELADO":
            v["canc"] += 1
            for arr in (dias[dia], dias_cia[cia][dia], aero_dia[o][dia]):
                arr[0] += 1
                arr[1] += 1
            continue
        for arr in (dias[dia], dias_cia[cia][dia], aero_dia[o][dia]):
            arr[0] += 1
        cr = data_hora(x.get("Chegada Real"))
        pr = data_hora(x.get("Partida Real"))
        sc = (x.get("Situação Chegada") or "").strip()
        if not cr:
            dbg["realizado_sem_chegada"] += 1
            continue
        atraso = (cr - cp).total_seconds() / 60
        if abs(atraso) > 24 * 60:  # registro inconsistente
            dbg["atraso_absurdo"] += 1
            continue
        v["med"] += 1
        pontual = atraso <= 30
        # confere com a classificação da própria ANAC
        if sc:
            anac_pontual = sc in ("Antecipado", "Pontual")
            dbg["confere" if anac_pontual == pontual else "diverge"] += 1
        if pontual:
            v["pont"] += 1
        else:
            k = 0 if atraso <= 60 else 1 if atraso <= 120 else 2 if atraso <= 240 else 3
            v["b"][k] += 1
            v["s30"] += round(atraso)
        if atraso > 0:
            v["spos"] += round(atraso)
        if pr:
            v["dprev"] += round((cp - pp).total_seconds() / 60)
            v["dreal"] += round((cr - pr).total_seconds() / 60)
        for arr in (dias[dia], dias_cia[cia][dia], aero_dia[o][dia]):
            arr[2] += 1
            arr[3] += 1 if pontual else 0
        rs = rota_sem[f"{o}-{d}"][pp.weekday()]
        rs[0] += 1
        rs[1] += 1 if pontual else 0

    voos = []
    for (cia, num, o, d), v in sorted(V.items()):
        voos.append([cia, num, o, d, v["hora"].most_common(1)[0][0], v["prev"], v["canc"], v["med"], v["pont"],
                     *v["b"], v["s30"], v["spos"], v["dprev"], v["dreal"],
                     v["modelo"].most_common(1)[0][0] if v["modelo"] else "",
                     round(v["assentos"] / v["nass"]) if v["nass"] else 0])
    resumo = {
        "mes": chave_mes,
        "baixado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "colunas_voos": ["cia", "numero", "origem", "destino", "hora", "previstos", "cancelados", "medidos",
                         "pontuais", "a30_60", "a60_120", "a120_240", "a240", "soma_atraso_atrasados",
                         "soma_atraso_positivo", "soma_dur_prevista", "soma_dur_real", "modelo", "assentos"],
        "cias": dict(sorted(cias.items())),
        "aeroportos": dict(sorted(aeros.items())),
        "voos": voos,
        "dias": dict(sorted(dias.items())),
        "dias_cia": {c: dict(sorted(dd.items())) for c, dd in sorted(dias_cia.items())},
        "aero_dia": {a: dict(sorted(dd.items())) for a, dd in sorted(aero_dia.items())},
        "rota_semana": dict(sorted(rota_sem.items())),
    }
    return resumo, dict(dbg)


def meses_ate_hoje():
    hoje = dt.date.today()
    a, m = INICIO
    while (a, m) <= (hoje.year, hoje.month):
        yield a, m
        m += 1
        if m == 13:
            a, m = a + 1, 1


def main() -> int:
    MESES.mkdir(parents=True, exist_ok=True)
    forcar = os.environ.get("FORCAR") == "1"
    debug = {"execucao": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "meses": {}}
    novos = 0
    for a, m in meses_ate_hoje():
        chave = f"{a}-{m:02d}"
        destino = MESES / f"{chave}.json"
        if destino.exists() and not forcar:
            continue
        log(f"{chave}: baixando…")
        bruto = baixar(a, m)
        if bruto is None:
            log(f"{chave}: ainda não publicado pela ANAC")
            continue
        resumo, dbg = resumir(bruto, chave)
        if dbg.get("domesticos", 0) < 20000:
            raise RuntimeError(f"{chave}: poucos voos domésticos ({dbg.get('domesticos')}); arquivo suspeito")
        if dbg.get("diverge", 0) > 0.02 * max(1, dbg.get("confere", 0)):
            raise RuntimeError(f"{chave}: classificação de pontualidade diverge da ANAC ({dbg})")
        destino.write_text(json.dumps(resumo, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        debug["meses"][chave] = dbg
        log(f"{chave}: {dbg.get('domesticos')} voos domésticos, {len(resumo['voos'])} voos distintos")
        novos += 1
    debug["novos"] = novos
    DEBUG.write_text(json.dumps(debug, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Meses novos: {novos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
