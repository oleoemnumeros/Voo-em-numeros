"""Clima mês a mês das cidades com aeroporto, para as páginas "Melhor época para ir".

Clima histórico quase não muda, então o robô só baixa quando data/clima.json ainda não
existe (ou com FORCAR=1). Duas fontes, guardadas lado a lado para cada aeroporto:

1. Inmet, Normais Climatológicas do Brasil 1991-2020 (médias de 30 anos medidas nas
   estações). A estação é casada com o aeroporto pelo nome do município e pela UF.
2. NASA POWER, médias mensais por coordenada (satélite e modelo), para os aeroportos
   cuja cidade não tem estação do Inmet ou se o site do Inmet não responder.

O gerador usa o Inmet quando existe e a NASA no resto. data/clima_debug.json registra o
que deu certo, para conferir sem precisar dos logs do Actions.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "clima.json"
DEBUG = RAIZ / "data" / "clima_debug.json"
MESES = RAIZ / "data" / "meses"
COORD = RAIZ / "data" / "aeroportos_iata.json"
DESTINOS = RAIZ / "data" / "destinos.json"   # destinos turísticos sem aeroporto (clima pelas coordenadas do próprio destino)
UA = {"User-Agent": "Mozilla/5.0 (compatible; VooEmNumeros/1.0; +https://vooemnumeros.com.br)"}

INMET_PAGINA = "https://portal.inmet.gov.br/normais"
INMET_ARQ = "https://portal.inmet.gov.br/uploads/normais/Normal-Climatologica-{}.xlsx"
# nomes possíveis de cada planilha (o Inmet não documenta; o primeiro que abrir vale)
INMET_CODIGOS = {
    "chuva": ["PREC"],
    "tmax": ["TMAX", "TEMPMAX", "TMAXMED", "TMAXIMA"],
    "tmin": ["TMIN", "TEMPMIN", "TMINMED", "TMINIMA"],
}
# Série DIÁRIA 2001-2020: a "climatologia" pronta do NASA POWER traz os extremos do mês (o dia mais quente
# e o mais frio), não a média das máximas e mínimas. Com os dias, a conta fica igual à das normais do Inmet.
NASA = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M_MAX,T2M_MIN,PRECTOTCORR"
        "&community=AG&longitude={lon}&latitude={lat}&start=20010101&end=20201231&format=JSON")
NASA_METODO = "diario-2001-2020"


def log(*a):
    print(*a, flush=True)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"[^A-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def aeroportos() -> dict:
    """ICAO -> (cidade, UF, lat, lon) dos aeroportos domésticos dos meses salvos."""
    desc = {}
    for f in sorted(MESES.glob("*.json")):
        desc.update(json.loads(f.read_text(encoding="utf-8")).get("aeroportos", {}))
    coords = json.loads(COORD.read_text(encoding="utf-8"))
    out = {}
    for icao, d in desc.items():
        p = [x.strip() for x in d.split(" - ")]
        if len(p) >= 4 and len(p[-2]) == 2 and icao in coords:
            out[icao] = (p[-3], p[-2], coords[icao]["lat"], coords[icao]["lon"])
    return out


def baixar(url: str, relay: bool = False) -> requests.Response | None:
    alvo, headers = url, dict(UA)
    if relay:
        base, token = os.environ.get("RELAY_URL", "").rstrip("/"), os.environ.get("RELAY_TOKEN", "")
        if not base:
            return None
        alvo = f"{base}/?url={requests.utils.quote(url, safe='')}"
        headers["X-Token"] = token
    for tentativa in range(3):
        try:
            r = requests.get(alvo, headers=headers, timeout=90)
            return r
        except requests.RequestException as e:
            log(f"  {url}: {e.__class__.__name__}; tentativa {tentativa + 1}")
            time.sleep(5 * (tentativa + 1))
    return None


def planilha_inmet(conteudo: bytes) -> dict:
    """Linhas da planilha de normais: nome normalizado da estação + UF -> 12 valores mensais."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    linhas = list(ws.iter_rows(values_only=True))
    cab = next(i for i, l in enumerate(linhas) if l and any(str(c or "").strip().lower().startswith("jan") for c in l))
    h = [str(c or "").strip().lower() for c in linhas[cab]]
    i_jan = next(i for i, c in enumerate(h) if c.startswith("jan"))
    i_nome = next((i for i, c in enumerate(h) if "nome" in c or "esta" in c or "munic" in c), 1)
    i_uf = next((i for i, c in enumerate(h) if c == "uf"), 2)
    out = {}
    for l in linhas[cab + 1:]:
        if not l or not l[i_nome]:
            continue
        vals = []
        for c in l[i_jan:i_jan + 12]:
            try:
                vals.append(round(float(str(c).replace(",", ".")), 1))
            except (TypeError, ValueError):
                vals.append(None)
        if sum(v is not None for v in vals) >= 10:
            out.setdefault((norm(str(l[i_nome])), str(l[i_uf] or "").strip().upper()), (str(l[i_nome]).strip(), vals))
    return out


def inmet(dbg: dict) -> dict:
    """var -> planilha. Tenta direto e, se configurada, pela ponte (o gov.br bloqueia os IPs do GitHub)."""
    tabelas = {}
    for via_relay in (False, True):
        if via_relay and not os.environ.get("RELAY_URL"):
            break
        r = baixar(INMET_PAGINA, via_relay)
        if r is not None:
            links = sorted(set(re.findall(r'uploads/normais/[^"\'\s>]+', r.text)))
            dbg["inmet_pagina"] = {"status": r.status_code, "relay": via_relay, "links": links[:80]}
            for var in INMET_CODIGOS:
                if var in tabelas:
                    continue
                cods = list(INMET_CODIGOS[var])
                # códigos que aparecem nos links da página entram primeiro
                for lk in links:
                    m = re.search(r"Normal-Climatologica-([A-Z0-9]+)\.xlsx", lk)
                    if m and m.group(1) not in cods and m.group(1).startswith({"chuva": "PREC", "tmax": "TMAX", "tmin": "TMIN"}[var]):
                        cods.insert(0, m.group(1))
                for cod in cods:
                    rr = baixar(INMET_ARQ.format(cod), via_relay)
                    st = rr.status_code if rr is not None else "erro"
                    dbg.setdefault("inmet_arquivos", {})[cod] = st
                    if rr is not None and rr.status_code == 200 and rr.content[:2] == b"PK":
                        try:
                            tabelas[var] = planilha_inmet(rr.content)
                            dbg["inmet_arquivos"][cod] = f"ok, {len(tabelas[var])} estações"
                            break
                        except Exception as e:  # planilha em formato inesperado
                            dbg["inmet_arquivos"][cod] = f"planilha ilegível: {e}"
        else:
            dbg.setdefault("inmet_pagina_erros", []).append({"relay": via_relay})
        if len(tabelas) == len(INMET_CODIGOS):
            break
    return tabelas


def casa_estacao(tabelas: dict, cidade: str, uf: str):
    """Mesma cidade e UF nas três planilhas. Devolve (nome da estação, tmax, tmin, chuva) ou None."""
    alvo = norm(cidade)
    res = {}
    for var, tab in tabelas.items():
        cand = [(k, v) for k, v in tab.items() if k[1] == uf and (k[0] == alvo or k[0].startswith(alvo + " "))]
        if not cand:
            return None
        res[var] = sorted(cand, key=lambda t: (t[0][0] != alvo, t[0][0]))[0][1]
    return res["tmax"][0], res["tmax"][1], res["tmin"][1], res["chuva"][1]


def resume_diario(p: dict) -> dict:
    """Média das máximas e das mínimas diárias por mês; chuva e dias de chuva (>= 1 mm) somados por mês e na média dos anos."""
    from collections import defaultdict
    mx, mn = defaultdict(list), defaultdict(list)
    ch, dias = defaultdict(float), defaultdict(int)
    anos = defaultdict(set)
    for dia, v in p["T2M_MAX"].items():
        m = int(dia[4:6]) - 1
        if v is not None and v > -900:
            mx[m].append(v)
        w = p["T2M_MIN"].get(dia)
        if w is not None and w > -900:
            mn[m].append(w)
        c = p["PRECTOTCORR"].get(dia)
        if c is not None and c > -900:
            ch[m] += c
            dias[m] += c >= 1
            anos[m].add(dia[:4])
    def med(l):
        return round(sum(l) / len(l), 1) if l else None
    return {"tmax": [med(mx[m]) for m in range(12)], "tmin": [med(mn[m]) for m in range(12)],
            "chuva": [round(ch[m] / len(anos[m])) if anos[m] else None for m in range(12)],
            "dias_chuva": [round(dias[m] / len(anos[m])) if anos[m] else None for m in range(12)]}


def nasa(lat: float, lon: float):
    r = baixar(NASA.format(lat=round(lat, 3), lon=round(lon, 3)))
    if r is None or r.status_code != 200:
        return None, (r.status_code if r is not None else "erro")
    return resume_diario(r.json()["properties"]["parameter"]), 200


def main() -> int:
    forcar = os.environ.get("FORCAR") == "1"
    atual = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else {"aeros": {}}
    if atual.get("nasa_metodo") != NASA_METODO:  # dados da NASA calculados de outro jeito: refaz
        for reg in atual["aeros"].values():
            reg.pop("nasa", None)
        atual["aeros"] = {a: r for a, r in atual["aeros"].items() if "inmet" in r}
    aeros = aeroportos()
    falta = [a for a in aeros if forcar or a not in atual["aeros"]]
    destinos = json.loads(DESTINOS.read_text(encoding="utf-8"))["destinos"] if DESTINOS.exists() else []
    atual.setdefault("destinos", {})
    falta_dest = [d for d in destinos if forcar or d["slug"] not in atual["destinos"]]
    # quando a ponte para o gov.br for configurada, tenta o Inmet uma vez para todos que só têm NASA
    if os.environ.get("RELAY_URL") and not atual.get("inmet_pela_ponte"):
        falta = sorted(set(falta) | {a for a in aeros if "inmet" not in atual["aeros"].get(a, {})})
        atual["inmet_pela_ponte"] = dt.date.today().isoformat()
    if not falta and not falta_dest:
        log("Clima: nada a baixar")
        return 0
    dbg = {"execucao": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "aeroportos": len(aeros), "faltando": len(falta)}
    tabelas = inmet(dbg)
    dbg["inmet_tabelas"] = sorted(tabelas)
    ok_inmet = ok_nasa = 0
    for a in falta:
        cidade, uf, lat, lon = aeros[a]
        reg = atual["aeros"].get(a, {}) if not forcar else {}
        reg.update({"cidade": cidade, "uf": uf})
        if len(tabelas) == 3:
            e = casa_estacao(tabelas, cidade, uf)
            if e:
                reg["inmet"] = {"estacao": e[0], "tmax": e[1], "tmin": e[2], "chuva": e[3]}
                ok_inmet += 1
        if "nasa" not in reg:
            n, st = nasa(lat, lon)
            if n:
                reg["nasa"] = n
                ok_nasa += 1
            else:
                dbg.setdefault("nasa_erros", {})[a] = st
            time.sleep(1)
        if "inmet" in reg or "nasa" in reg:
            atual["aeros"][a] = reg
    ok_dest = 0
    for d in falta_dest:  # destinos sem aeroporto: Inmet pelo município do destino, senão NASA pelas coordenadas
        reg = {"cidade": d["municipio"], "uf": d["uf"]}
        if len(tabelas) == 3:
            e = casa_estacao(tabelas, d["municipio"], d["uf"])
            if e:
                reg["inmet"] = {"estacao": e[0], "tmax": e[1], "tmin": e[2], "chuva": e[3]}
        n, st = nasa(d["lat"], d["lon"])
        if n:
            reg["nasa"] = n
        else:
            dbg.setdefault("nasa_erros", {})[d["slug"]] = st
        time.sleep(1)
        if "inmet" in reg or "nasa" in reg:
            atual["destinos"][d["slug"]] = reg
            ok_dest += 1
    dbg["destinos"] = ok_dest
    atual["inmet_periodo"] = "1991-2020"
    atual["nasa_periodo"] = "2001-2020"
    atual["nasa_metodo"] = NASA_METODO
    atual["baixado_em"] = dt.date.today().isoformat()
    dbg.update({"com_inmet": ok_inmet, "com_nasa": ok_nasa, "salvos": len(atual["aeros"])})
    SAIDA.write_text(json.dumps(atual, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    DEBUG.write_text(json.dumps(dbg, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Clima: {ok_inmet} com estação do Inmet, {ok_nasa} com NASA POWER, {len(atual['aeros'])} aeroportos salvos, {ok_dest} destinos sem aeroporto")
    return 0


if __name__ == "__main__":
    sys.exit(main())
