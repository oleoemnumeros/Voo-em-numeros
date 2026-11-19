"""Baixa os microdados de tarifas aéreas domésticas da ANAC (DataSAS) e grava data/tarifas.json.

Cada arquivo mensal (cerca de 25 MB) tem uma linha por empresa que vendeu, origem, destino, valor da tarifa e
quantidade de assentos vendidos a esse valor, pelo MÊS DA VENDA. O robô guarda, dos últimos 13 meses:
  - assentos e soma das tarifas por mês, no país, por rota (origem-destino) e por rota e empresa;
  - a distribuição de preços (histograma em faixas fixas) do mês mais recente, por rota e por rota e empresa;
  - o IPCA mensal (Banco Central) para corrigir os valores pela inflação.
Quando nada mudou na ANAC (mesmos arquivos, mesma data de publicação), não baixa nada.
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
import html
import io
import json
import os
import re
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "tarifas.json"
U = "https://sas.anac.gov.br/sas/downloads/view/frmDownload.aspx"
TEMA_DOMESTICO = "14"
MESES = 13
MIN_ASSENTOS_ROTA = 150      # assentos no mês mais recente para a rota entrar
MIN_ASSENTOS_ROTA_CIA = 80   # idem para rota e empresa
CIAS = ("TAM", "GLO", "AZU")  # LATAM, GOL, Azul: as que vendem quase tudo; as demais ficam só no total da rota

# limites inferiores das faixas de preço (R$): 25 em 25 até 1.000; 50 em 50 até 2.000; 100 em 100 até 4.000; 500 em 500 até 8.000
EDGES = ([i * 25 for i in range(40)] + [1000 + i * 50 for i in range(20)] + [2000 + i * 100 for i in range(20)]
         + [4000 + i * 500 for i in range(9)])

S = requests.Session()
S.headers["User-Agent"] = "Mozilla/5.0 (vooemnumeros robo)"


# ---------------------------------------------------------------- DataSAS (ASP.NET WebForms)
def campos(t: str) -> dict:
    d = {}
    for m in re.finditer(r"<input[^>]*>", t):
        tag = m.group(0)
        n = re.search(r'name="([^"]+)"', tag)
        if not n:
            continue
        ty = re.search(r'type="([^"]+)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        d[n.group(1)] = (ty.group(1) if ty else "text", html.unescape(v.group(1)) if v else "")
    for m in re.finditer(r'<select name="([^"]+)".*?</select>', t, flags=re.S):
        opts = re.findall(r'<option( selected="selected")? value="([^"]*)">', m.group(0))
        d[m.group(1)] = ("select", next((o[1] for o in opts if o[0]), opts[0][1] if opts else ""))
    return d


def post(t: str, alvo: str, extra: dict, timeout: int = 240):
    d = {k: v[1] for k, v in campos(t).items() if v[0] not in ("submit", "button", "checkbox")}
    d.update(extra)
    d["__EVENTTARGET"] = alvo
    return S.post(U, data=d, timeout=timeout)


def com_tentativas(fn, vezes: int = 6, espera: int = 5):
    ultimo = None
    for i in range(vezes):
        try:
            return fn()
        except (requests.RequestException, ValueError, IndexError, zipfile.BadZipFile) as e:
            ultimo = e
            print(f"  tentativa {i + 1} falhou: {type(e).__name__} {str(e)[:100]}")
            time.sleep(espera * (i + 1))
    raise RuntimeError(f"falhou depois de {vezes} tentativas: {ultimo}")


def lista_ano(ano: int):
    """Devolve (página com a lista, [(campo da caixa, nome, data/hora, ano, mês)])."""
    def go():
        r = S.get(U, timeout=90)
        r2 = post(r.text, "ctl00$MainContent$listTema", {"ctl00$MainContent$listTema": TEMA_DOMESTICO})
        r3 = post(r2.text, "", {"ctl00$MainContent$listTema": TEMA_DOMESTICO, "ctl00$MainContent$listAno": str(ano),
                                "ctl00$MainContent$btnListaArquivos": "Buscar Arquivos"})
        pad = (r'name="(ctl00\$MainContent\$gridArquivos\$ctl\d+\$chkDownload)".*?<td[^>]*>([^<]*)</td><td[^>]*>([^<]*)</td>'
               r'<td[^>]*>(\d+)</td><td[^>]*>(\d+)</td>')
        linhas = re.findall(pad, r3.text, flags=re.S)
        if not linhas:
            raise ValueError("lista de arquivos vazia")
        return r3, [(c, n.strip(), h.strip(), int(a), int(m)) for c, n, h, a, m in linhas]
    return com_tentativas(go)


def baixar_mes(ano: int, mes: int) -> bytes:
    def go():
        pag, linhas = lista_ano(ano)
        cand = [l for l in linhas if l[4] == mes]
        if not cand:
            raise ValueError(f"mês {ano}-{mes:02d} não está na lista")
        caixa = cand[-1][0]
        r = post(pag.text, "", {"ctl00$MainContent$listTema": TEMA_DOMESTICO, "ctl00$MainContent$listAno": str(ano),
                                caixa: "on", "ctl00$MainContent$btnBaixar": "Baixar Marcados"}, timeout=300)
        if r.status_code != 200 or r.content[:2] != b"PK":
            raise ValueError(f"resposta inesperada ({r.status_code}, {len(r.content)} bytes)")
        z = zipfile.ZipFile(io.BytesIO(r.content))
        pref = f"{ano}{mes:02d}"
        nomes = [n for n in z.namelist() if n.startswith(pref)]
        if not nomes:
            raise ValueError(f"arquivo {pref} não veio no zip: {z.namelist()[:5]}")
        return z.read(nomes[-1])
    return com_tentativas(go)


def meses_disponiveis() -> dict:
    """{(ano, mês): data/hora de publicação} dos arquivos domésticos, dos dois últimos anos."""
    hoje = dt.date.today()
    out = {}
    for ano in (hoje.year - 1, hoje.year):
        try:
            _, linhas = lista_ano(ano)
        except RuntimeError as e:
            print(f"Lista de {ano} indisponível: {e}")
            continue
        for _, nome, hora, a, m in linhas:
            out[(a, m)] = hora
    return out


# ---------------------------------------------------------------- leitura
def faixa(valor: float) -> int:
    return bisect.bisect_right(EDGES, valor) - 1


def le_mes(raw: bytes, com_distribuicao: bool) -> dict:
    """Soma assentos e tarifas por rota e por rota e empresa; opcionalmente o histograma."""
    texto = raw.decode("utf-8-sig", errors="replace") if raw[:3] == b"\xef\xbb\xbf" else raw.decode("latin-1")
    rd = csv.reader(io.StringIO(texto, newline=""), delimiter=";")
    cab = [c.strip().lower() for c in next(rd)]
    mapa = {"empresa": ("empresa", "sg_empresa_icao"), "origem": ("origem", "sg_icao_origem"),
            "destino": ("destino", "sg_icao_destino"), "tarifa": ("tarifa", "nr_tarifa"), "assentos": ("assentos", "nr_assentos")}
    ix = {}
    for k, nomes in mapa.items():
        achou = [cab.index(n) for n in nomes if n in cab]
        if not achou:
            raise ValueError(f"coluna {k} ausente: {cab}")
        ix[k] = achou[0]
    nac = [0, 0.0]
    rotas = defaultdict(lambda: [0, 0.0])
    rc = defaultdict(lambda: [0, 0.0])
    h_nac = [0] * len(EDGES)
    h_rotas = defaultdict(lambda: [0] * len(EDGES))
    h_rc = defaultdict(lambda: [0] * len(EDGES))
    linhas = 0
    for r in rd:
        try:
            t = float(r[ix["tarifa"]].replace(",", "."))
            q = int(r[ix["assentos"]])
        except (ValueError, IndexError):
            continue
        if q <= 0 or t <= 0:
            continue
        o, d, e = r[ix["origem"]], r[ix["destino"]], r[ix["empresa"]]
        if not o or not d:
            continue
        linhas += 1
        k = f"{o}-{d}"
        v = t * q
        nac[0] += q; nac[1] += v
        rotas[k][0] += q; rotas[k][1] += v
        if e in CIAS:
            kc = f"{k}|{e}"
            rc[kc][0] += q; rc[kc][1] += v
        if com_distribuicao:
            b = faixa(t)
            h_nac[b] += q
            h_rotas[k][b] += q
            if e in CIAS:
                h_rc[f"{k}|{e}"][b] += q
    return {"linhas": linhas, "nac": nac, "rotas": rotas, "rc": rc, "h_nac": h_nac, "h_rotas": h_rotas, "h_rc": h_rc}


def ipca(meses: list[str], antigo: dict) -> dict:
    ini = dt.date.fromisoformat(meses[0] + "-01").strftime("%d/%m/%Y")
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial={ini}"
    try:
        r = com_tentativas(lambda: requests.get(url, timeout=60), vezes=3, espera=3)
        out = {}
        for it in r.json():
            d, m, a = it["data"].split("/")
            out[f"{a}-{m}"] = float(it["valor"])
        if out:
            return out
    except Exception as e:  # noqa: BLE001
        print("IPCA indisponível:", e)
    return antigo


def mes_str(a: int, m: int) -> str:
    return f"{a}-{m:02d}"


def main() -> int:
    forcar = os.environ.get("FORCAR") == "1"
    atual = json.loads(SAIDA.read_text(encoding="utf-8")) if SAIDA.exists() else {}
    disp = meses_disponiveis()
    if not disp:
        print("DataSAS indisponível agora; mantém o arquivo anterior.")
        return 1 if not atual else 0
    ref = max(disp)
    alvo = []
    a, m = ref
    for _ in range(MESES):
        alvo.append((a, m))
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    alvo.sort()
    alvo = [x for x in alvo if x in disp]
    arquivos = {mes_str(*x): disp[x] for x in alvo}
    if atual and not forcar and atual.get("arquivos") == arquivos and atual.get("ref") == mes_str(*ref):
        print(f"Tarifas em dia (até {mes_str(*ref)}).")
        return 0
    print(f"Baixando {len(alvo)} meses de tarifas, de {mes_str(*alvo[0])} a {mes_str(*ref)}.")
    por_mes, hist = {}, None
    for x in alvo:
        ms = mes_str(*x)
        try:
            raw = baixar_mes(*x)
            res = le_mes(raw, com_distribuicao=(x == ref))
        except Exception as e:  # noqa: BLE001
            print(f"  {ms}: falhou ({e})")
            continue
        print(f"  {ms}: {res['linhas']:,} linhas, {res['nac'][0]:,} assentos, tarifa média R$ {res['nac'][1] / max(res['nac'][0], 1):.2f}")
        por_mes[ms] = res
        if x == ref:
            hist = res
    ms_ref = mes_str(*ref)
    if ms_ref not in por_mes or len(por_mes) < 10:
        print("Mês mais recente ou muitos meses faltando; mantém o arquivo anterior.")
        return 1
    r0 = por_mes[ms_ref]
    if not 1_500_000 <= r0["nac"][0] <= 6_000_000 or r0["linhas"] < 300_000 or len(r0["rotas"]) < 1000:
        print("Números do mês mais recente fora do esperado; não grava.")
        return 1
    manter = {k for k, v in r0["rotas"].items() if v[0] >= MIN_ASSENTOS_ROTA}
    manter_rc = {k for k, v in r0["rc"].items() if v[0] >= MIN_ASSENTOS_ROTA_CIA and k.split("|")[0] in manter}
    rotas, cias = {}, {}
    for ms, res in por_mes.items():
        for k in manter:
            v = res["rotas"].get(k)
            if v:
                rotas.setdefault(k, {})[ms] = [v[0], round(v[1])]
        for kc in manter_rc:
            v = res["rc"].get(kc)
            if v:
                k, e = kc.split("|")
                cias.setdefault(k, {}).setdefault(e, {})[ms] = [v[0], round(v[1])]
    h = {k: {"": hist["h_rotas"][k]} for k in manter}
    for kc in manter_rc:
        k, e = kc.split("|")
        h[k][e] = hist["h_rc"][kc]
    saida = {
        "atualizado_em": dt.date.today().isoformat(),
        "ref": ms_ref,
        "arquivos": arquivos,
        "edges": EDGES,
        "ipca": ipca(sorted(por_mes), atual.get("ipca", {})),
        "nac": {ms: [res["nac"][0], round(res["nac"][1])] for ms, res in sorted(por_mes.items())},
        "nac_h": hist["h_nac"],
        "rotas": rotas,
        "cias": cias,
        "h": h,
    }
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Tarifas gravadas até {ms_ref}: {len(rotas)} rotas, {sum(len(v) for v in cias.values())} rotas com empresa, "
          f"{SAIDA.stat().st_size / 1e6:.1f} MB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
