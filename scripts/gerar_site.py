"""Gera o site estático do Voo em Números em docs/ a partir de data/meses/*.json.

Páginas: início, companhias, aeroportos, rotas, voos, fim de ano, como funciona,
mais sitemap.xml, robots.txt, 404.html, busca.json e a imagem de compartilhamento.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from familia_card import TEXTO_COMPARTILHE, bloco_imagem, gera_card, sem_imagem, seta  # noqa: E402  imagem do resumo, igual nos portais

RAIZ = Path(__file__).resolve().parent.parent
# AdSense: coloque o código do editor (ex.: pub-1234567890123456) em adsense.txt na raiz do repositório; vazio ou ausente = sem anúncios
_AD = RAIZ / "adsense.txt"
ADSENSE_ID = re.sub(r"^(ca-)?", "", _AD.read_text(encoding="utf-8").strip()) if _AD.exists() else ""
if ADSENSE_ID and not re.fullmatch(r"pub-\d{10,20}", ADSENSE_ID):
    print(f"Aviso: adsense.txt inválido ({ADSENSE_ID!r}); anúncios desligados")
    ADSENSE_ID = ""
SITE = RAIZ / "site"
MESES_DIR = RAIZ / "data" / "meses"
IATA_ARQ = RAIZ / "data" / "aeroportos_iata.json"
SAIDA = RAIZ / "docs"
DOMINIO = "vooemnumeros.com.br"
BASE = f"https://{DOMINIO}"
GOAT = '<script data-goatcounter="https://vooemnumeros.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'

# Família em Números: para incluir um novo portal, acrescente uma linha nesta lista
FAMILIA = [
    ("Óleo em Números", "Petróleo e gás", "https://oleoemnumeros.com.br/", "#17758C"),
    ("Comex em Números", "Exportações e importações", "https://comexemnumeros.com.br/", "#1F85D0"),
    ("Voo em Números", "Pontualidade aérea", "https://vooemnumeros.com.br/", "#4FB8EE"),
    ("Economia em Números", "Macroeconomia", "https://economiaemnumeros.com.br/", "#D9A514"),
]
ATUAL = "Voo em Números"

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]
MES_CURTO = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
DIAS_SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
DIAS_CURTO = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]

# Nome usado no site, código IATA usado nos bilhetes e endereço da página
CIAS = {
    "TAM": ("LATAM", "LA", "latam"),
    "GLO": ("GOL", "G3", "gol"),
    "AZU": ("Azul", "AD", "azul"),
    "ACN": ("Azul Conecta", "", "azul-conecta"),
    "PTB": ("Voepass", "2Z", "voepass"),
    "ABJ": ("Abaeté", "", "abaete"),
    "CQB": ("Apuí Táxi Aéreo", "", "apui"),
    "PLS": ("Placar", "", "placar"),
    "AEB": ("Avion Express Brasil", "", "avion-express"),
}
NOMES_AERO = {
    "SBGR": "São Paulo (Guarulhos)", "SBSP": "São Paulo (Congonhas)", "SBKP": "Campinas (Viracopos)",
    "SBGL": "Rio de Janeiro (Galeão)", "SBRJ": "Rio de Janeiro (Santos Dumont)",
    "SBCF": "Belo Horizonte (Confins)", "SBBH": "Belo Horizonte (Pampulha)", "SBBR": "Brasília",
    "SBMT": "São Paulo (Campo de Marte)", "SBJR": "Rio de Janeiro (Jacarepaguá)",
    # aeroportos que ficam em cidade vizinha à que dá nome a eles
    "SBCT": "Curitiba", "SBMO": "Maceió", "SBCY": "Cuiabá", "SBSG": "Natal", "SBJP": "João Pessoa",
    "SBIP": "Ipatinga (Vale do Aço)", "SBJE": "Jericoacoara", "SBZM": "Juiz de Fora", "SBAE": "Bauru",
    "SBUY": "Coari (Urucu)", "SBJA": "Jaguaruna", "SBTB": "Oriximiná (Trombetas)", "SBCJ": "Parauapebas (Carajás)",
}
PEQUENAS = {"de", "do", "da", "dos", "das", "e", "em", "d'", "del"}

# Limites para uma página ou ranking existir (evita conclusões com poucos voos)
MIN_AERO_RANK = 900      # partidas previstas no mês para entrar no ranking de aeroportos
MIN_ROTA_RANK = 150      # voos previstos no mês para entrar no ranking de rotas
MIN_VOO_RANK = 20        # voos medidos no mês para entrar no ranking de voos
MIN_CIA_RANK = 5000      # voos previstos no mês para entrar no ranking de companhias (as grandes)
MIN_PAG_AERO = 60        # partidas previstas em 3 meses para o aeroporto ter página
MIN_PAG_ROTA = 30        # voos previstos em 3 meses para a rota ter página
MIN_PAG_VOO = 12         # voos medidos em 3 meses para o voo ter página


# ---------------------------------------------------------------- utilidades
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def slug(t: str) -> str:
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def nf(v: float, d: int = 0) -> str:
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pc(v, d: int = 1) -> str:
    return "–" if v is None else nf(100 * v, d) + "%"


def titulo_pt(t: str) -> str:
    out = []
    for i, w in enumerate(t.lower().split()):
        if i and w in PEQUENAS:
            out.append(w)
        elif "'" in w and len(w) > 2:
            a, b = w.split("'", 1)
            out.append(a.capitalize() + "'" + b.capitalize())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def mes_nome(m: str) -> str:
    a, mm = m.split("-")
    return f"{MESES[int(mm) - 1]} de {a}"


def mes_curto(m: str) -> str:
    a, mm = m.split("-")
    return f"{MES_CURTO[int(mm) - 1]}/{a[2:]}"


def mes_ant_ano(m: str) -> str:
    a, mm = m.split("-")
    return f"{int(a) - 1}-{mm}"


def cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def delta_pp(a, b, maior_bom=True) -> str:
    """Variação em pontos percentuais com seta e cor."""
    if a is None or b is None:
        return ""
    d = 100 * (a - b)
    if abs(d) < 0.05:
        return "igual a um ano antes"
    bom = (d > 0) == maior_bom
    seta = "▲" if d > 0 else "▼"
    return f'<span class="{"up" if bom else "down"}">{seta} {nf(abs(d), 1)} p.p.</span> contra um ano antes'


# ---------------------------------------------------------------- dados
class Acc:
    """Soma de contadores de um conjunto de voos."""
    __slots__ = ("prev", "canc", "med", "pont", "b", "s30", "spos", "dprev", "dreal")

    def __init__(self):
        self.prev = self.canc = self.med = self.pont = self.s30 = self.spos = self.dprev = self.dreal = 0
        self.b = [0, 0, 0, 0]

    def add(self, r):
        self.prev += r[5]; self.canc += r[6]; self.med += r[7]; self.pont += r[8]
        self.b[0] += r[9]; self.b[1] += r[10]; self.b[2] += r[11]; self.b[3] += r[12]
        self.s30 += r[13]; self.spos += r[14]; self.dprev += r[15]; self.dreal += r[16]
        return self

    def soma(self, o: "Acc"):
        self.prev += o.prev; self.canc += o.canc; self.med += o.med; self.pont += o.pont
        self.b = [x + y for x, y in zip(self.b, o.b)]
        self.s30 += o.s30; self.spos += o.spos; self.dprev += o.dprev; self.dreal += o.dreal
        return self

    @property
    def atr(self):
        return sum(self.b)

    @property
    def p_pont(self):
        return self.pont / self.med if self.med else None

    @property
    def p_canc(self):
        return self.canc / self.prev if self.prev else None

    @property
    def p_a60(self):
        return (self.b[1] + self.b[2] + self.b[3]) / self.med if self.med else None

    @property
    def media_atr(self):
        return self.s30 / self.atr if self.atr else None


def carrega():
    meses = {}
    for f in sorted(MESES_DIR.glob("*.json")):
        meses[f.stem] = json.loads(f.read_text(encoding="utf-8"))
    if not meses:
        sys.exit("Sem dados em data/meses. Rode scripts/atualizar.py antes.")
    return meses


class Base:
    def __init__(self, meses: dict):
        self.meses = meses
        self.lista = sorted(meses)
        self.ref = self.lista[-1]
        self.ant = mes_ant_ano(self.ref)
        self.u3 = self.lista[-3:]
        self.u12 = self.lista[-12:]
        self.u13 = self.lista[-13:]
        self.iata = json.loads(IATA_ARQ.read_text(encoding="utf-8"))
        self.desc_aero, self.nome_cia_bruto = {}, {}
        for m in self.lista:
            self.desc_aero.update(meses[m]["aeroportos"])
            self.nome_cia_bruto.update(meses[m]["cias"])
        self.gerado = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3)))
        # agregados por mês
        self.tot, self.cia, self.aero, self.rota, self.voo = {}, {}, {}, {}, {}
        self.cia_aero, self.cia_rota = {}, {}
        self.chg = {}                                           # chegadas por aeroporto de destino
        self.voo_legs = defaultdict(lambda: defaultdict(Acc))   # (cia,num) -> (o,d) -> Acc (3 meses)
        self.voo_info = {}                                      # (cia,num) -> dados do mês mais recente
        self.voo_hora = defaultdict(Counter)                    # (cia,num,o,d) -> horário (3 meses)
        for m in self.lista:
            T, C, A, R, V = Acc(), defaultdict(Acc), defaultdict(Acc), defaultdict(Acc), defaultdict(Acc)
            CA, CR, CH = defaultdict(Acc), defaultdict(Acc), defaultdict(Acc)
            for r in meses[m]["voos"]:
                cia, num, o, d = r[0], r[1], r[2], r[3]
                T.add(r); C[cia].add(r); A[o].add(r); R[(o, d)].add(r); V[(cia, num)].add(r)
                CA[(cia, o)].add(r); CR[(cia, o, d)].add(r); CH[d].add(r)
                if m in self.u3:
                    self.voo_legs[(cia, num)][(o, d)].add(r)
                    self.voo_hora[(cia, num, o, d)][r[4]] += r[5]
                    self.voo_info[(cia, num, o, d)] = (r[4], r[17], r[18])
            self.tot[m], self.cia[m], self.aero[m], self.rota[m], self.voo[m] = T, C, A, R, V
            self.cia_aero[m], self.cia_rota[m] = CA, CR
            self.chg[m] = CH

    # somas em vários meses
    def soma(self, tabela: dict, chave, meses) -> Acc:
        a = Acc()
        for m in meses:
            if m in tabela and chave in tabela[m]:
                a.soma(tabela[m][chave])
        return a

    def soma_tot(self, meses) -> Acc:
        a = Acc()
        for m in meses:
            if m in self.tot:
                a.soma(self.tot[m])
        return a

    # nomes
    def cia_nome(self, c: str) -> str:
        if c in CIAS:
            return CIAS[c][0]
        bruto = self.nome_cia_bruto.get(c, c)
        bruto = re.sub(r"\s*\(.*?\)\s*", " ", bruto)
        bruto = re.sub(r"\b(S/?A|S\.A\.|LTDA\.?|LINHAS AÉREAS|TÁXI AÉREO|TRANSPORTES AÉREOS)\b", "", bruto, flags=re.I)
        return titulo_pt(bruto.strip(" -.,")) or c

    def cia_slug(self, c: str) -> str:
        return CIAS[c][2] if c in CIAS else slug(self.cia_nome(c))

    def cod_voo(self, c: str, num: str) -> str:
        pref = CIAS[c][1] if c in CIAS and CIAS[c][1] else c
        return f"{pref} {num}"

    def voo_slug(self, c: str, num: str) -> str:
        pref = CIAS[c][1] if c in CIAS and CIAS[c][1] else c
        return f"{pref.lower()}-{num}"

    def aero_partes(self, icao: str):
        desc = self.desc_aero.get(icao, icao)
        p = [x.strip() for x in desc.split(" - ")]
        if len(p) >= 4 and len(p[-2]) == 2:
            return " - ".join(p[:-3]), p[-3], p[-2]
        return desc, desc, ""

    def cidade(self, icao: str) -> str:
        if icao in NOMES_AERO:
            return NOMES_AERO[icao].split(" (")[0]
        return titulo_pt(self.aero_partes(icao)[1])

    def uf(self, icao: str) -> str:
        return self.aero_partes(icao)[2]

    def aero_nome(self, icao: str) -> str:
        if icao in NOMES_AERO:
            return NOMES_AERO[icao]
        return self._nomes_aero.get(icao) or self.cidade(icao)

    def preparar_nomes(self, aeros):
        """Cidades com mais de um aeroporto ganham o nome do aeroporto entre parênteses."""
        por_cidade = defaultdict(list)
        for a in aeros:
            if a not in NOMES_AERO:
                por_cidade[(self.cidade(a), self.uf(a))].append(a)
        self._nomes_aero = {}
        for (cid, _), lst in por_cidade.items():
            for a in lst:
                if len(lst) > 1:
                    nome = titulo_pt(self.aero_partes(a)[0].split(" - ")[0])
                    self._nomes_aero[a] = f"{cid} ({nome})"
                else:
                    self._nomes_aero[a] = cid

    # links só para páginas que existem
    pag_cias, pag_rotas, pag_aero = set(), set(), set()

    def link_cia(self, c: str) -> str:
        n = esc(self.cia_nome(c))
        return f'<a href="/companhias/{self.cia_slug(c)}/">{n}</a>' if c in self.pag_cias else n

    def link_rota(self, o: str, d: str, texto: str) -> str:
        return f'<a href="/rotas/{self.rota_slug(o, d)}/">{texto}</a>' if (o, d) in self.pag_rotas else f"<b>{texto}</b>"

    def link_aero(self, a: str, texto: str) -> str:
        return f'<a href="/aeroportos/{self.aero_slug(a)}/">{texto}</a>' if a in self.pag_aero else f"<b>{texto}</b>"

    def nome_cod(self, icao: str) -> str:
        n, c = self.aero_nome(icao), self.cod(icao)
        return n[:-1] + f", {c})" if n.endswith(")") else f"{n} ({c})"

    def cod(self, icao: str) -> str:
        return self.iata.get(icao, {}).get("iata", icao)

    def aero_slug(self, icao: str) -> str:
        return self.cod(icao).lower()

    def rota_slug(self, o: str, d: str) -> str:
        return f"{self.aero_slug(o)}-{self.aero_slug(d)}"


# ---------------------------------------------------------------- pedaços de HTML
def familia_html() -> str:
    itens = []
    for nome, tema, url, cor in FAMILIA:
        miolo = f'<span class="ponto" style="background:{cor}"></span><span><b>{nome}</b> {tema}</span>'
        if nome == ATUAL:
            itens.append(f'<li>{miolo} <em>você está aqui</em></li>')
        else:
            itens.append(f'<li><a href="{url}">{miolo}</a></li>')
    return ('<div class="familia"><p><b>Família em Números</b> · portais independentes que organizam dados públicos do Brasil · <a href="https://x.com/familianumeros" rel="noopener" target="_blank">Siga no X</a> · <a href="https://www.instagram.com/familiaemnumeros/" rel="noopener" target="_blank">Siga no Instagram</a> · <a href="https://www.linkedin.com/company/familiaemnumeros/" rel="noopener" target="_blank">Siga no LinkedIn</a></p>'
            f'<ul>{"".join(itens)}</ul></div>')


# ---------------------------------------------------------------- Continue explorando (entre os portais)
# Para incluir um novo portal, acrescente uma linha aqui e em FAMILIA.
PORTAIS = {
    "oleo": ("Óleo em Números", "https://oleoemnumeros.com.br", "#17758C"),
    "comex": ("Comex em Números", "https://comexemnumeros.com.br", "#1F85D0"),
    "voo": ("Voo em Números", BASE, "#4FB8EE"),
    "economia": ("Economia em Números", "https://economiaemnumeros.com.br", "#D9A514"),
}
ESTE = "voo"


def continue_html(itens) -> str:
    """Cartões no fim da página: (portal, caminho, título, descrição); no máximo 4.
    Cada clique é contado no GoatCounter como evento continue/<origem>-<destino>."""
    cartoes = []
    vistos = set()
    for portal, caminho, titulo, desc in itens:
        nome, base, cor = PORTAIS[portal]
        href = caminho if portal == ESTE else base + caminho
        if href in vistos:
            continue
        vistos.add(href)
        cartoes.append(
            f'<li><a href="{esc(href)}" data-goatcounter-click="continue/{ESTE}-{portal}" data-goatcounter-title="Continue explorando: {esc(titulo)}">'
            f'<span class="cont-tag"><i style="background:{cor}"></i>{nome}</span><b>{esc(titulo)}</b><span class="cont-d">{esc(desc)}</span></a></li>')
        if len(cartoes) == 4:
            break
    if not cartoes:
        return ""
    return ('<section class="continue" aria-labelledby="continue-t"><h2 id="continue-t">Continue explorando</h2>'
            f'<ul class="cont-grid">{"".join(cartoes)}</ul></section>')


# índices de cidades dos outros portais: {chave_cidade: [(portal, caminho, rótulo)]}; guarda cópia em data/familia/
# para o caso de o outro site estar fora do ar na hora da geração
FAMILIA_INDICES = {
    "economia": ("https://economiaemnumeros.com.br/municipios/busca.json", "economia", "Quantos habitantes, quanto a cidade produz e de onde vem o dinheiro da prefeitura"),
    "comex": ("https://comexemnumeros.com.br/municipios/indice.json", "comex", "O que a cidade exporta e importa"),
    "oleo": ("https://oleoemnumeros.com.br/royalties/indice.json", "oleo", "Royalties de petróleo que a cidade recebe"),
}


def chave_cidade(nome: str, uf: str) -> str:
    t = unicodedata.normalize("NFKD", str(nome)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t) + "-" + str(uf).strip().upper()


def carrega_familia(rede: bool = True) -> dict:
    import urllib.request
    pasta = RAIZ / "data" / "familia"
    out: dict = {}
    for nome, (url, portal, desc) in FAMILIA_INDICES.items():
        cache = pasta / f"{nome}.json"
        itens = None
        try:
            if not rede:
                raise OSError("sem rede")
            req = urllib.request.Request(url, headers={"User-Agent": "vooemnumeros"})
            with urllib.request.urlopen(req, timeout=15) as r:
                itens = json.loads(r.read().decode("utf-8"))
            pasta.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(itens, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        except Exception:  # noqa: BLE001
            if cache.exists():
                try:
                    itens = json.loads(cache.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    itens = None
        for it in itens or []:
            try:
                cid, uf, caminho = it[0], it[1], it[2]
            except (IndexError, TypeError, KeyError):
                continue
            if str(caminho).startswith("http"):
                continue
            out.setdefault(chave_cidade(cid, uf), {})[nome] = (portal, str(caminho), desc)
    return out


def itens_cidade(B: Base, icao: str) -> list:
    """Cartões das páginas da cidade do aeroporto nos outros portais."""
    achados = B.familia.get(chave_cidade(B.cidade(icao), B.uf(icao)), {})
    cid = B.cidade(icao)
    titulos = {"economia": f"{cid}: população, PIB e prefeitura", "comex": f"O que {cid} exporta e importa",
               "oleo": f"Royalties de petróleo em {cid}"}
    return [(p, c, titulos[n], d) for n in ("economia", "comex", "oleo") if n in achados for (p, c, d) in [achados[n]]]


def linha_destino(B: Base, d: str, quando: bool = True) -> str:
    """Linha curta com a cidade de destino: melhor época para ir (aqui) e a cidade nos outros portais."""
    achados = B.familia.get(chave_cidade(B.cidade(d), B.uf(d)), {})
    sq = cid_slug(B, d)
    tem_q = quando and sq in getattr(B, "quando", set())
    if not achados and not tem_q:
        return ""
    cid = B.cidade(d)
    rot = {"economia": "População e economia", "comex": "O que a cidade exporta", "oleo": "Royalties de petróleo"}
    links = []
    if tem_q:
        links.append(f'<a href="/quando-ir/{sq}/" data-goatcounter-click="destino/quando-ir"><i style="background:var(--acc)"></i>Melhor época para ir</a>')
    for n in ("economia", "comex", "oleo"):
        if n in achados:
            portal, caminho, _ = achados[n]
            nome, base, cor = PORTAIS[portal]
            links.append(f'<a href="{esc(base + caminho)}" data-goatcounter-click="destino/{ESTE}-{portal}" '
                         f'data-goatcounter-title="Destino: {esc(cid)} ({nome})"><i style="background:{cor}"></i>{rot[n]}</a>')
    return (f'<aside class="destino" aria-label="{esc(cid)} em números"><b>Vai para {esc(cid)}? Veja {esc(cid)} em números</b>'
            f'<span>{"".join(links)}</span></aside>')


def continue_padrao(caminho: str) -> list:
    """Cartões por tipo de página, para as que não passam os seus."""
    direitos = ("voo", "/direitos/", "Seus direitos se o voo atrasar", "O que a companhia deve pagar ou oferecer, por tempo de atraso")
    fim = ("voo", "/fim-de-ano/", "Voar no fim de ano", "Quais aeroportos e dias têm mais atraso no Natal e no Ano-Novo")
    mapa = ("voo", "/mapa/", "Mapa da pontualidade", "Cada aeroporto do Brasil por cor, do mais ao menos pontual")
    aero = ("voo", "/aeroportos/", "Ranking dos aeroportos", "Do mais ao menos pontual do Brasil")
    dem = ("voo", "/demanda/", "Passageiros e ocupação", "Aeroporto lotado atrasa mais?")
    aviao = ("comex", "/produto/8802/", "O Brasil também exporta aviões", "Quanto o país vende e compra de aviões e helicópteros")
    qav = ("oleo", "/refino/", "Do petróleo ao querosene de aviação", "Quanto as refinarias produzem de cada derivado")
    eco = ("economia", "/", "Selic, inflação e dólar", "Os números da economia brasileira, atualizados todo dia")
    if caminho == "/":
        return [direitos, aviao, qav, mapa]
    if caminho.startswith(("/companhias/", "/voos/")):
        return [aero, direitos, dem, eco]
    if caminho.startswith("/rotas/"):
        return [direitos, aero, mapa, eco]
    if caminho.startswith("/precos/"):
        return [direitos, aero, ("voo", "/rotas/", "Rotas mais e menos pontuais", "Qual trecho atrasa mais"), eco]
    if caminho.startswith("/aeroportos/"):
        return [("voo", "/rotas/", "Rotas mais e menos pontuais", "Qual trecho atrasa mais"), direitos, mapa, eco]
    if caminho.startswith(("/cidades/", "/estados/", "/trajetos/")):
        return [direitos, mapa, aviao, eco]
    if caminho.startswith("/rankings/"):
        return [direitos, mapa, dem, eco]
    if caminho.startswith("/fim-de-ano/"):
        return [direitos, mapa, aero, eco]
    if caminho.startswith("/direitos/"):
        return [aero, mapa, fim, aviao]
    if caminho.startswith(("/mapa/", "/demanda/")):
        return [aero, direitos, aviao, eco]
    return []


# Ordem padrão da Família em Números: Início, Resumos, temas do portal, lugares, guias, Como funciona
ADS_HEAD = (f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-{ADSENSE_ID}" crossorigin="anonymous"></script>'
            if ADSENSE_ID else "")
# menu enxuto (no celular só cabem 4 ou 5 itens): o resto fica no rodapé
NAV = [("/", "Início"), ("/resumo/", "Resumos"), ("/rotas/", "Rotas"), ("/precos/", "Preços"), ("/aeroportos/", "Aeroportos"), ("/companhias/", "Companhias"),
       ("/cidades/", "Cidades"), ("/rankings/", "Rankings"), ("/direitos/", "Seus direitos")]
LOGO = ('<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><rect x="1" y="1" width="28" height="28" rx="7" fill="#2A9DE0"/>'
        '<path d="M7 17.5 23 9.5l-3.2 9.3-4.3-2.6-2.9 3.8-.4-4.7z" fill="#fff"/><rect x="7" y="22" width="16" height="1.8" rx=".9" fill="#fff" opacity=".7"/></svg>')


ATALHOS = [("Quanto custa", "Preço"), ("Voo a voo", "Dia a dia"), ("Seu voo atrasou?", "Seus direitos"), ("Quanto ele atrasa", "Atrasos"),
           ("Outros voos", "Outros voos"), ("Passageiros", "Passageiros"), ("companhia", "Companhias"), ("Os voos desta", "Voos"),
           ("Voos que mais atrasam", "Voos"), ("Melhor horário", "Horários"), ("Destinos", "Destinos"), ("Mês a mês", "Mês a mês"),
           ("Outras rotas saindo", "Outras rotas"), ("Rotas", "Rotas"), ("Aeroportos", "Aeroportos"), ("Perguntas", "Perguntas")]


def com_atalhos(corpo: str, caminho: str) -> str:
    """Páginas longas ganham, logo depois do topo, uma fila de atalhos para as seções ("Nesta página")."""
    if not caminho.startswith(("/rotas/", "/voos/", "/aeroportos/", "/trajetos/", "/cidades/", "/companhias/", "/estados/")) or caminho.count("/") < 3:
        return corpo
    itens, usados, n = [], set(), [0]

    def troca(m):
        txt = re.sub(r"<[^>]+>", "", m.group(2))
        for chave, rot in ATALHOS:
            if chave.lower() in txt.lower() and rot not in usados:
                usados.add(rot)
                n[0] += 1
                ide = f"s{n[0]}"
                itens.append(f'<a href="#{ide}">{rot}</a>')
                return f'<h2{m.group(1)} id="{ide}">{m.group(2)}</h2>'
        return m.group(0)
    novo = re.sub(r'<h2((?:(?!id=)[^>])*)>(.*?)</h2>', troca, corpo)
    if len(itens) < 4:
        return corpo
    fila = f'<nav class="atalhos" aria-label="Nesta página"><span>Nesta página</span>{"".join(itens)}</nav>'
    i = novo.find("</section>")
    return novo[:i + 10] + "\n" + fila + novo[i + 10:] if i >= 0 else novo


def pagina(B: Base, caminho: str, titulo: str, descricao: str, corpo: str, ativo: str = "",
           migalhas=None, jsonld=None, continuar=None, imagem=None) -> str:
    url = BASE + caminho
    # "Continue explorando": cartões da própria página (continuar) completados pelos do tipo de página;
    # links para páginas do próprio site só entram se a página existe (B.fixas)
    cont = [c for c in list(continuar or []) + continue_padrao(caminho) if c[0] != ESTE or c[1] in B.fixas or c[1].startswith(("/aeroportos/", "/rotas/", "/voos/", "/companhias/"))]
    cont = [c for c in cont if c[1] != caminho]
    cont_html = continue_html(cont)
    corpo = com_atalhos(corpo, caminho)
    # o Google corta títulos acima de ~60 caracteres: tira a marca da <title> quando passa disso
    titulo_tag = titulo[:-len(" | Voo em Números")] if len(titulo) > 62 and titulo.endswith(" | Voo em Números") else titulo
    if len(titulo_tag) > 62:
        titulo_tag = titulo_tag.replace("atrasos e cancelamentos", "atrasos")
    nav = "".join(f'<a href="{h}"' + (' aria-current="page"' if h == ativo else "") + f">{t}</a>" for h, t in NAV)
    bc = ""
    lds = list(jsonld or [])
    if migalhas:
        partes = ['<a href="/">Início</a>'] + [f'<a href="{h}">{esc(t)}</a>' if h else esc(t) for h, t in migalhas]
        bc = '<nav class="bc" aria-label="Você está em">' + " › ".join(partes) + "</nav>"
        itens = [{"@type": "ListItem", "position": 1, "name": "Início", "item": BASE + "/"}]
        for i, (h, t) in enumerate(migalhas, 2):
            itens.append({"@type": "ListItem", "position": i, "name": t, "item": BASE + (h or caminho)})
        lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": itens})
    ld = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in lds)
    v = B.gerado.strftime("%Y%m%d")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(titulo_tag)}</title>
<meta name="description" content="{esc(descricao)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Voo em Números">
<meta property="og:title" content="{esc(titulo)}">
<meta property="og:description" content="{esc(descricao)}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="pt_BR">
<meta property="og:image" content="{imagem or BASE + "/assets/og.png"}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#2A9DE0">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/estilo.css?v={v}">
{ADS_HEAD}
{ld}
</head>
<body>
<header class="top"><div class="top-in">
<a class="brand" href="/" aria-label="Voo em Números, início">{LOGO}<span style="color:var(--ink)">Voo <span>em Números</span></span></a>
<nav class="main" aria-label="Seções">{nav}</nav>
</div></header>
<div class="info-bar"><div><strong>Dados até {mes_nome(B.ref)}.</strong> Fonte: ANAC, base Voo Regular Ativo (VRA). Atualizado automaticamente em {B.gerado.strftime("%d/%m/%Y")}.</div></div>
<main>
{bc}
{corpo}
{cont_html}
</main>
<footer><div>
<span><strong>Voo em Números</strong> · versão beta</span>
<span>Voos domésticos regulares de passageiros. No horário = chegada até 30 minutos depois do previsto, mesmo critério da ANAC. Cancelados contam sobre os voos previstos.</span>
<span><a href="/companhias/">Companhias</a> · <a href="/aeroportos/">Aeroportos</a> · <a href="/cidades/">Cidades</a> · <a href="/rankings/">Rankings</a> · <a href="/rotas/">Rotas</a> · <a href="/precos/">Preços</a> · <a href="/quando-ir/">Quando ir</a> · <a href="/mapa/">Mapa</a> · <a href="/resumo/">Resumos</a> · <a href="/demanda/">Passageiros</a> · <a href="/fim-de-ano/">Fim de ano</a> · <a href="/direitos/">Seus direitos</a> · <a href="/sobre/">Como funciona</a> · <a href="/sugestoes/">Sugestões e críticas</a> · <a href="/contato/">Contato</a> · <a href="/privacidade/">Privacidade</a></span>
</div>{familia_html()}</footer>
<script src="/assets/app.js?v={v}" defer></script>
<script src="/assets/familia.js?v={v}" defer></script>
<script src="/assets/familia-graficos.js?v={v}" defer></script>
<script src="/assets/precos.js?v={v}" defer></script>
<script src="/assets/rota.js?v={v}" defer></script>
<script src="/assets/familia-compartilhar.js?v={v}" defer></script>
<script src="/assets/familia-busca.js?v={v}" data-indice="/busca-geral.json?v={v}" data-dica="Voo (LA 3300), rota (GRU SSA), cidade ou aeroporto" defer></script>
{GOAT}
</body>
</html>
"""


def tile(lbl, val, nota="") -> str:
    return f'<div class="tile"><span class="lbl">{lbl}</span><span class="val num">{val}</span><span class="chg">{nota}</span></div>'


def meter(p, ruim=False) -> str:
    if p is None:
        return "–"
    w = max(0.0, min(1.0, p)) * 100
    return (f'<div class="meter"><div class="bar"><i class="{"w" if ruim else ""}" style="width:{w:.1f}%"></i></div>'
            f'<b>{pc(p)}</b></div>')


def tiles_acc(a: Acc, a0: Acc | None, rot_prev="Voos previstos") -> str:
    a0 = a0 if a0 and a0.med else None
    return '<div class="tiles">' + "".join([
        tile("Chegaram no horário", pc(a.p_pont), delta_pp(a.p_pont, a0.p_pont if a0 else None, True)),
        tile("Cancelados", pc(a.p_canc), delta_pp(a.p_canc, a0.p_canc if a0 else None, False)),
        tile("Atrasos acima de 1 hora", pc(a.p_a60), delta_pp(a.p_a60, a0.p_a60 if a0 else None, False)),
        tile(rot_prev, nf(a.prev), f"{nf(a.canc)} cancelados"),
    ]) + "</div>"


def fam_gr(cfg: dict, svg: str, aria: str) -> str:
    """Gráfico interativo (familia-graficos.js): os dados vão no atributo e o SVG de reserva fica dentro, valendo sem JavaScript."""
    dados = html.escape(json.dumps({**cfg, "a": aria}, ensure_ascii=False, separators=(",", ":")), quote=True)
    return f'<div class="fam-gr" data-fam-gr="{dados}">{svg}</div>'


def svg_barras(rotulos, valores, destaque_ultimo=True, altura=190, fmt=lambda v: pc(v, 0), cores=None, aria="", largura=720, periodos=None) -> str:
    """Barras verticais de percentuais (0 a 100%), uma por rótulo."""
    n = len(valores)
    if not n:
        return ""
    W, H, top, base = largura, altura, 22, altura - 26
    cls = "chart" if largura >= 600 else "chart mini"
    vals = [v for v in valores if v is not None]
    mn = max(0.0, min(vals) - 0.15) if vals else 0
    mn = (int(mn * 10)) / 10
    passo = (W - 20) / n
    bw = min(46, passo * 0.66)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">']
    out.append(f'<line x1="10" y1="{base}" x2="{W - 10}" y2="{base}" stroke="#C6D2DC"/>')
    for i, (r, v) in enumerate(zip(rotulos, valores)):
        x = 10 + i * passo + (passo - bw) / 2
        ult = destaque_ultimo and i == n - 1
        if v is not None:
            h = max(2, (v - mn) / (1 - mn) * (base - top)) if 1 - mn else 2
            cor = (cores[i] if cores else ("#2A9DE0" if ult else "#A9D8F5"))
            out.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{cor}"/>')
            out.append(f'<text x="{x + bw / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle" font-size="12" '
                       f'fill="#3D424A" font-weight="{700 if ult else 400}">{esc(fmt(v))}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle" font-size="12" fill="#5A6070">{esc(r)}</text>')
    out.append("</svg>")
    nota = f'<p class="nota">Eixo começa em {pc(mn, 0)} para mostrar melhor as diferenças.</p>' if mn > 0 else ""
    serie = {"n": "No horário", "v": [round(v * 100, 2) if v is not None else None for v in valores], "c": "#2A9DE0"}
    if cores:
        serie["cs"] = list(cores)
    cfg = {"t": "b", "p": list(periodos or rotulos), "d": 1, "suf": "%", "z": 0, "vl": 1, "s": [serie]}
    if not destaque_ultimo:
        cfg["hl"] = 0
    if periodos is None:
        cfg["w"] = 0
    # com período em data o desenhista mostra o eixo e os botões de período; a nota do eixo truncado deixa de valer
    return fam_gr(cfg, f'<div class="{cls}">' + "".join(out) + "</div>", aria)


def serie_13(B: Base, tabela: dict, chave) -> tuple[list, list, list]:
    """Pontualidade mês a mês em todos os meses da base (o gráfico oferece 1 ano e total); devolve rótulos, valores e períodos."""
    rot, val = [], []
    for m in B.lista:
        a = tabela[m].get(chave) if chave is not None else tabela[m]
        rot.append(mes_curto(m))
        val.append(a.p_pont if a and a.med >= 10 else None)
    return rot, val, list(B.lista)


def faq_html(pares) -> tuple[str, dict]:
    corpo = '<section class="card"><h2>Perguntas rápidas</h2><div class="faq">' + "".join(
        f"<div><h3>{esc(p)}</h3><p>{esc(r)}</p></div>" for p, r in pares) + "</div></section>"
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": p, "acceptedAnswer": {"@type": "Answer", "text": r}} for p, r in pares]}
    return corpo, ld


def min_txt(v) -> str:
    if v is None:
        return "–"
    v = round(v)
    return f"{v} min" if v < 60 else f"{v // 60}h{v % 60:02d}"


# ---------------------------------------------------------------- páginas
def pg_inicio(B: Base, cias_rank, aero_pag, rota_pag, voo_pag, fim) -> str:
    T, T0 = B.tot[B.ref], B.tot.get(B.ant)
    mes = mes_nome(B.ref)
    lead = (f"Em {mes}, <strong>{pc(T.p_pont)}</strong> dos voos domésticos chegaram no horário e "
            f"<strong>{pc(T.p_canc)}</strong> foram cancelados. Entre os que atrasaram mais de 30 minutos, "
            f"o atraso médio foi de <strong>{min_txt(T.media_atr)}</strong>.")
    # companhias
    linhas = []
    for c in cias_rank:
        a, a12 = B.cia[B.ref][c], B.soma(B.cia, c, B.u12)
        linhas.append(f'<tr><td><a href="/companhias/{B.cia_slug(c)}/">{esc(B.cia_nome(c))}</a></td>'
                      f'<td style="min-width:200px">{meter(a.p_pont)}</td><td class="r num">{pc(a.p_canc)}</td>'
                      f'<td class="r num">{min_txt(a.media_atr)}</td><td class="r num">{pc(a12.p_pont)}</td>'
                      f'<td class="r num">{nf(a.prev)}</td></tr>')
    tab_cias = ('<div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th>'
                '<th scope="col" class="r">Cancelados</th><th scope="col" class="r">Atraso médio dos atrasados</th>'
                f'<th scope="col" class="r">No horário em 12 meses</th><th scope="col" class="r">Voos previstos</th></tr></thead><tbody>{"".join(linhas)}</tbody></table></div>')
    # aeroportos
    grandes = [a for a, x in B.aero[B.ref].items() if x.prev >= MIN_AERO_RANK and a in aero_pag]
    grandes.sort(key=lambda a: B.aero[B.ref][a].p_pont or 0, reverse=True)

    def lista_aero(lst):
        return '<ul class="rank">' + "".join(
            f'<li><span><a href="/aeroportos/{B.aero_slug(a)}/">{esc(B.cod(a))}</a> <span class="small">{esc(B.aero_nome(a))}</span></span>'
            f'<span class="num"><b>{pc(B.aero[B.ref][a].p_pont)}</b></span></li>' for a in lst) + "</ul>"
    # rotas
    rotas = [r for r, x in B.rota[B.ref].items() if x.prev >= MIN_ROTA_RANK and r in rota_pag]
    rotas.sort(key=lambda r: B.rota[B.ref][r].p_pont or 0)

    def linhas_rotas(lst):
        return "".join(
            f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(o, d)}/">{esc(B.cod(o))} → {esc(B.cod(d))}</a> '
            f'<span class="small">{esc(B.cidade(o))} → {esc(B.cidade(d))}</span></td>'
            f'<td class="r num"><b>{pc(B.rota[B.ref][(o, d)].p_pont)}</b></td><td class="r num">{pc(B.rota[B.ref][(o, d)].p_canc)}</td>'
            f'<td class="r num">{nf(B.rota[B.ref][(o, d)].prev)}</td></tr>' for o, d in lst)
    cab_rotas = ('<thead><tr><th scope="col">Rota</th><th scope="col" class="r">No horário</th>'
                 '<th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead>')
    # voos
    voos = [k for k, x in B.voo[B.ref].items() if x.med >= MIN_VOO_RANK and k in voo_pag]
    voos.sort(key=lambda k: (B.voo[B.ref][k].p_pont or 0, -B.voo[B.ref][k].med))
    piores_voos = "".join(
        f'<tr><td><a href="/voos/{B.voo_slug(c, n)}/">{esc(B.cod_voo(c, n))}</a></td><td class="wrap">{esc(voo_pag[(c, n)])}</td>'
        f'<td class="r num"><b>{pc(B.voo[B.ref][(c, n)].p_pont)}</b></td><td class="r num">{min_txt(B.voo[B.ref][(c, n)].media_atr)}</td></tr>'
        for c, n in voos[:10])
    rot, val, pers = serie_13(B, B.tot, None)
    corpo = f"""
<section class="hero">
<span class="kicker">Voos domésticos · {mes}</span>
<h1>Pontualidade dos voos no Brasil</h1>
<p class="lead">{lead}</p>
<div class="busca" role="search"><label for="busca" class="sr">Buscar voo, rota, aeroporto ou companhia</label>
<input id="busca" type="search" autocomplete="off" placeholder="Voo (LA 3300), rota (GRU SSA), cidade ou aeroporto"><div id="busca-res" aria-live="polite"></div></div>
{seletor_rota(B, rota_pag)}
</section>
{fim_card(B, fim)}
{resumo_card_home(B)}
{tiles_acc(T, T0)}
{mapa_card_home(B, aero_pag)}
{dem_card_home(B)}
{explora_card_home(B)}
{preco_card_home(B)}
<section class="card"><div class="card-head"><h2>Ranking das companhias em {mes}</h2><span class="small">Companhias com mais de {nf(MIN_CIA_RANK)} voos no mês</span></div>
{tab_cias}
<p class="nota">No horário = chegada até 30 minutos depois do previsto, mesmo critério da ANAC.</p></section>
<section class="card"><h2>Pontualidade mês a mês</h2>{svg_barras(rot, val, periodos=pers, aria="Percentual de voos domésticos no horário mês a mês")}</section>
<div class="grid2">
<section class="card"><h2>Aeroportos mais pontuais</h2>{lista_aero(grandes[:6])}<p class="nota">Partidas no horário em {mes}, aeroportos com mais de {nf(MIN_AERO_RANK)} partidas.</p></section>
<section class="card"><h2>Aeroportos menos pontuais</h2>{lista_aero(list(reversed(grandes[-6:])))}<p class="nota"><a href="/aeroportos/">Ver todos os aeroportos</a></p></section>
</div>
<section class="card"><div class="card-head"><h2>Rotas que mais atrasaram</h2><span class="small">Rotas com mais de {MIN_ROTA_RANK} voos em {mes}</span></div>
<div class="tw"><table>{cab_rotas}<tbody>{linhas_rotas(rotas[:10])}</tbody></table></div>
<p class="nota"><a href="/rotas/">Ver todas as rotas</a></p></section>
<section class="card"><div class="card-head"><h2>Voos que mais atrasaram</h2><span class="small">Voos com pelo menos {MIN_VOO_RANK} viagens em {mes}</span></div>
<div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Trecho</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio dos atrasados</th></tr></thead><tbody>{piores_voos}</tbody></table></div></section>
{direitos_card_home()}
"""
    desc = (f"{cap(mes)}: {pc(T.p_pont)} dos voos domésticos chegaram no horário e {pc(T.p_canc)} foram cancelados. "
            "Ranking de companhias, aeroportos, rotas e voos com dados oficiais da ANAC.")
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": "Voo em Números", "url": BASE + "/",
               "inLanguage": "pt-BR"}
    return pagina(B, "/", f"Pontualidade dos voos no Brasil: {mes} | Voo em Números", desc, corpo, "/", jsonld=[site_ld])


def fim_card(B: Base, fim) -> str:
    """Faixa de destaque do fim de ano, logo abaixo do topo da página inicial."""
    if not fim:
        return ""
    D = {}
    for m in fim["meses"]:
        for k, v in B.meses[m]["dias"].items():
            D[k] = [x + y for x, y in zip(D.get(k, [0, 0, 0, 0]), v)]
    S = [0, 0, 0, 0]
    piores = []
    for d in fim["dias"]:
        v = D.get(d.isoformat())
        if v:
            S = [x + y for x, y in zip(S, v)]
            if v[2]:
                piores.append((v[3] / v[2], d))
    ano = fim["ano"]
    resumo = ""
    if S[2] and S[0]:
        pior = min(piores)
        resumo = (f' Entre 19/12/{ano} e 04/01/{ano + 1}, <strong>{pc(S[3] / S[2])}</strong> dos voos chegaram no horário e '
                  f'<strong>{pc(S[1] / S[0])}</strong> foram cancelados. O pior dia foi {pior[1].day} de {MESES[pior[1].month - 1]} ({pc(pior[0])} no horário).')
    return (f'<section class="card dark destaque"><span class="kicker">Em destaque</span><h2>Vai viajar no fim do ano?</h2>'
            f'<p>Veja como foram os atrasos e cancelamentos no Natal e Ano-Novo de {ano}, dia a dia, por companhia e por aeroporto.{resumo}</p>'
            f'<div class="btns"><a class="btn" href="/fim-de-ano/" style="background:#F2B33D;color:#14161A">Ver o fim de ano</a></div></section>')


def pg_companhias(B: Base, cias_pag) -> str:
    linhas = []
    for c in cias_pag:
        a, a12 = B.cia[B.ref].get(c, Acc()), B.soma(B.cia, c, B.u12)
        linhas.append(f'<tr><td><a href="/companhias/{B.cia_slug(c)}/">{esc(B.cia_nome(c))}</a></td>'
                      f'<td class="r num">{pc(a.p_pont)}</td><td class="r num">{pc(a.p_canc)}</td>'
                      f'<td class="r num">{pc(a12.p_pont)}</td><td class="r num">{nf(a12.prev)}</td></tr>')
    corpo = f"""<section class="hero"><h1>Companhias aéreas</h1>
<p class="lead">Pontualidade e cancelamentos das companhias nos voos domésticos, com dados oficiais da ANAC até {mes_nome(B.ref)}.</p></section>
<section class="card"><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col" class="r">No horário em {mes_curto(B.ref)}</th>
<th scope="col" class="r">Cancelados em {mes_curto(B.ref)}</th><th scope="col" class="r">No horário em 12 meses</th><th scope="col" class="r">Voos em 12 meses</th></tr></thead>
<tbody>{"".join(linhas)}</tbody></table></div></section>"""
    return pagina(B, "/companhias/", "Companhias aéreas: pontualidade e cancelamentos | Voo em Números",
                  f"Ranking de pontualidade e cancelamentos de LATAM, GOL, Azul e outras companhias nos voos domésticos até {mes_nome(B.ref)}.",
                  corpo, "/companhias/", migalhas=[("", "Companhias")])


def pg_cia(B: Base, c: str, aero_pag, rota_pag, voo_pag) -> str:
    nome = B.cia_nome(c)
    a, a0, a12 = B.cia[B.ref].get(c, Acc()), B.cia.get(B.ant, {}).get(c), B.soma(B.cia, c, B.u12)
    mes = mes_nome(B.ref)
    rot, val, pers = serie_13(B, B.cia, c)
    # aeroportos da companhia
    aer = [(o, x) for (cc, o), x in B.cia_aero[B.ref].items() if cc == c and x.prev >= 100 and o in aero_pag]
    aer.sort(key=lambda t: t[1].p_pont or 0)
    linhas_aer = "".join(f'<tr><td><a href="/{"companhias/" + B.cia_slug(c) + "/" if (c, o) in B.pag_ca else "aeroportos/"}{B.aero_slug(o)}/">{esc(B.cod(o))}</a> <span class="small">{esc(B.aero_nome(o))}</span></td>'
                         f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>'
                         for o, x in aer[:10])
    # rotas
    rts = []
    for (cc, o, d) in {k for m in B.u3 for k in B.cia_rota[m] if k[0] == c}:
        x = B.soma(B.cia_rota, (c, o, d), B.u3)
        if x.prev >= 60 and (o, d) in rota_pag:
            rts.append(((o, d), x))
    rts.sort(key=lambda t: t[1].p_pont or 0)

    def lin_rotas(lst):
        return "".join(f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(o, d)}/">{esc(B.cod(o))} → {esc(B.cod(d))}</a> '
                       f'<span class="small">{esc(B.cidade(o))} → {esc(B.cidade(d))}</span></td><td class="r num"><b>{pc(x.p_pont)}</b></td>'
                       f'<td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>' for (o, d), x in lst)
    cab = ('<thead><tr><th scope="col">Rota</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th>'
           '<th scope="col" class="r">Voos</th></tr></thead>')
    # voos
    vs = [(k, B.soma(B.voo, k, B.u3)) for k in voo_pag if k[0] == c]
    vs = [(k, x) for k, x in vs if x.med >= 30]
    vs.sort(key=lambda t: (t[1].p_pont or 0, -t[1].med))

    def lin_voos(lst):
        return "".join(f'<tr><td><a href="/voos/{B.voo_slug(*k)}/">{esc(B.cod_voo(*k))}</a></td><td class="wrap">{esc(voo_pag[k])}</td>'
                       f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td></tr>' for k, x in lst)
    cabv = ('<thead><tr><th scope="col">Voo</th><th scope="col">Trecho</th><th scope="col" class="r">No horário</th>'
            '<th scope="col" class="r">Cancelados</th></tr></thead>')
    faq, ld = faq_html([
        (f"A {nome} atrasa muito?",
         f"Em {mes}, {pc(a.p_pont)} dos voos domésticos da {nome} chegaram até 30 minutos depois do previsto. "
         f"Nos últimos 12 meses, foram {pc(a12.p_pont)}."),
        (f"Quantos voos da {nome} foram cancelados?",
         f"Em {mes}, a {nome} cancelou {nf(a.canc)} de {nf(a.prev)} voos previstos ({pc(a.p_canc)})."),
        (f"Quanto tempo atrasam os voos da {nome}?",
         f"Entre os voos que atrasaram mais de 30 minutos em {mes}, o atraso médio na chegada foi de {min_txt(a.media_atr)}. "
         f"{pc(a.p_a60)} dos voos chegaram com mais de 1 hora de atraso."),
    ])
    corpo = f"""<section class="hero"><span class="kicker">Companhia aérea · {mes}</span><h1>{esc(nome)}: pontualidade e cancelamentos</h1>
<p class="lead">Em {mes}, <strong>{pc(a.p_pont)}</strong> dos voos domésticos da {esc(nome)} chegaram no horário e <strong>{pc(a.p_canc)}</strong> foram cancelados.</p></section>
{tiles_acc(a, a0)}
{dem_cia(B, c)}
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, periodos=pers, aria=f"Percentual de voos da {nome} no horário mês a mês")}</section>
<section class="card"><div class="card-head"><h2>Aeroportos com mais atrasos da {esc(nome)}</h2><span class="small">Partidas em {mes}, mínimo de 100</span></div>
<div class="tw"><table><thead><tr><th scope="col">Aeroporto</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{linhas_aer}</tbody></table></div></section>
<div class="grid2">
<section class="card"><div class="card-head"><h2>Rotas menos pontuais</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table>{cab}<tbody>{lin_rotas(rts[:8])}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Rotas mais pontuais</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table>{cab}<tbody>{lin_rotas(list(reversed(rts[-8:])))}</tbody></table></div></section>
</div>
<div class="grid2">
<section class="card"><div class="card-head"><h2>Voos que mais atrasam</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table>{cabv}<tbody>{lin_voos(vs[:10])}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Voos mais pontuais</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table>{cabv}<tbody>{lin_voos(list(reversed(vs[-10:])))}</tbody></table></div></section>
</div>
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/companhias/{B.cia_slug(c)}/", f"{nome}: pontualidade e cancelamentos em {mes} | Voo em Números",
                  f"{cap(mes)}: {pc(a.p_pont)} dos voos da {nome} chegaram no horário e {pc(a.p_canc)} foram cancelados. Rotas, aeroportos e voos que mais atrasam.",
                  corpo, "/companhias/", migalhas=[("/companhias/", "Companhias"), ("", nome)], jsonld=[ld])


def pg_aeroportos(B: Base, aero_pag) -> str:
    por_uf = defaultdict(list)
    for a in aero_pag:
        por_uf[B.uf(a) or "–"].append(a)
    blocos = []
    for uf in sorted(por_uf):
        itens = sorted(por_uf[uf], key=lambda a: B.aero_nome(a))
        lis = "".join(f'<li><span><a href="/aeroportos/{B.aero_slug(a)}/">{esc(B.cod(a))}</a> <span class="small">{esc(B.aero_nome(a))}</span></span>'
                      f'<span class="num small">{pc(B.soma(B.aero, a, B.u3).p_pont)}</span></li>' for a in itens)
        blocos.append(f'<div><h3>{esc(uf)}</h3><ul class="rank">{lis}</ul></div>')
    corpo = f"""<section class="hero"><h1>Aeroportos</h1>
<p class="lead">Pontualidade das partidas em {len(aero_pag)} aeroportos com voos regulares, por estado. Percentual de voos no horário nos últimos 3 meses.</p></section>
<section class="card"><div class="cols">{"".join(blocos)}</div></section>"""
    return pagina(B, "/aeroportos/", "Aeroportos do Brasil: atrasos e cancelamentos | Voo em Números",
                  "Pontualidade e cancelamentos dos voos que partem de cada aeroporto do Brasil, com dados oficiais da ANAC.",
                  corpo, "/aeroportos/", migalhas=[("", "Aeroportos")])


def pg_aero(B: Base, o: str, rota_pag, voo_pag) -> str:
    nome, cod = B.aero_nome(o), B.cod(o)
    mes = mes_nome(B.ref)
    a, a0, a3 = B.aero[B.ref].get(o, Acc()), B.aero.get(B.ant, {}).get(o), B.soma(B.aero, o, B.u3)
    base_txt = mes
    if a.prev < 30:
        a, a0, base_txt = a3, None, "últimos 3 meses"
    rot, val, pers = serie_13(B, B.aero, o)
    # companhias
    cs = [(c, x) for (c, oo), x in B.cia_aero[B.ref].items() if oo == o and x.prev >= 10]
    cs.sort(key=lambda t: -t[1].prev)
    lin_c = "".join(f'<tr><td>{(f"<a href=/companhias/{B.cia_slug(c)}/{B.aero_slug(o)}/>" + esc(B.cia_nome(c)) + "</a>") if (c, o) in B.pag_ca else B.link_cia(c)}</td><td style="min-width:180px">{meter(x.p_pont)}</td>'
                    f'<td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>' for c, x in cs)
    # destinos
    ds = [(d, B.soma(B.rota, (o, d), B.u3)) for (oo, d) in rota_pag if oo == o]
    ds.sort(key=lambda t: -t[1].prev)
    lin_d = "".join(f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(o, d)}/">{esc(B.cod(d))}</a> <span class="small">{esc(B.aero_nome(d))}</span></td>'
                    f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>'
                    for d, x in ds)
    # voos que partem daqui
    vs = []
    for k in voo_pag:
        x = B.voo_legs[k].get(next(iter([ld for ld in B.voo_legs[k] if ld[0] == o]), None))
        if x and x.med >= 20:
            vs.append((k, x))
    vs.sort(key=lambda t: (t[1].p_pont or 0, -t[1].med))
    lin_v = "".join(f'<tr><td><a href="/voos/{B.voo_slug(*k)}/">{esc(B.cod_voo(*k))}</a></td><td class="wrap">{esc(voo_pag[k])}</td>'
                    f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{min_txt(x.media_atr)}</td></tr>' for k, x in vs[:10])
    pior_c = min(cs, key=lambda t: t[1].p_pont or 1) if cs else None
    pares = [
        (f"O aeroporto {B.nome_cod(o)} atrasa muito?",
         f"Em {base_txt}, {pc(a.p_pont)} das partidas de {cod} chegaram ao destino no horário (até 30 minutos de atraso) e {pc(a.p_canc)} foram canceladas."),
        (f"Quantos voos saem de {B.nome_cod(o)}?",
         f"Em {mes}, estavam previstas {nf(B.aero[B.ref].get(o, Acc()).prev)} partidas de voos domésticos regulares em {cod}."),
    ]
    if pior_c and len(cs) > 1:
        pares.append((f"Qual companhia atrasa mais em {cod}?",
                      f"Em {mes}, a {B.cia_nome(pior_c[0])} teve a menor pontualidade nas partidas de {cod}: {pc(pior_c[1].p_pont)} no horário."))
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Aeroporto · {esc(B.uf(o))}</span><h1>{esc(B.nome_cod(o))}: atrasos e cancelamentos</h1>
<p class="lead">Partidas de voos domésticos regulares. Em {base_txt}, <strong>{pc(a.p_pont)}</strong> chegaram no horário e <strong>{pc(a.p_canc)}</strong> foram cancelados.</p>
{links_cidade_aero(B, o)}</section>
{tiles_acc(a, a0, "Partidas previstas")}
{dem_aero(B, o)}
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, periodos=pers, aria=f"Percentual de partidas de {cod} no horário mês a mês")}</section>
<section class="card"><div class="card-head"><h2>Por companhia em {mes}</h2></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Destinos a partir de {esc(cod)}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Destino</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_d}</tbody></table></div></section>
{f'<section class="card"><div class="card-head"><h2>Voos que mais atrasam saindo de {esc(cod)}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Trecho</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio dos atrasados</th></tr></thead><tbody>{lin_v}</tbody></table></div></section>' if lin_v else ""}
{faq}"""
    return pagina(B, f"/aeroportos/{B.aero_slug(o)}/", f"Aeroporto {B.nome_cod(o)}: atrasos e cancelamentos | Voo em Números",
                  f"{cap(base_txt)}: {pc(a.p_pont)} das partidas de {cod} chegaram no horário e {pc(a.p_canc)} foram canceladas. Companhias, destinos e voos que mais atrasam.",
                  corpo, "/aeroportos/", migalhas=[("/aeroportos/", "Aeroportos"), ("", B.nome_cod(o))], jsonld=[ld],
                  continuar=itens_cidade(B, o))


def seletor_rota(B: Base, rota_pag) -> str:
    """Duas listas, "De" e "Para", que levam à página da rota (aparece só com JavaScript)."""
    aeros = {x for r in rota_pag for x in r}
    def _rot(a):
        nm = B.aero_nome(a)  # "São Paulo (Congonhas)" vira "São Paulo – Congonhas (CGH)"
        if nm.endswith(")") and " (" in nm:
            nm = nm[:-1].replace(" (", " – ", 1)
        return f"{nm} ({B.cod(a)})"
    rotulo = {a: _rot(a) for a in aeros}
    rotas = {}
    for o, d in rota_pag:
        rotas.setdefault(o, []).append([d, B.rota_slug(o, d)])
    dados = html.escape(json.dumps({"a": rotulo, "r": rotas}, ensure_ascii=False, separators=(",", ":")), quote=True)
    return (f'<div class="rs" data-rotas="{dados}" hidden><label>De<select class="rs-de"></select></label>'
            '<label>Para<select class="rs-para" disabled></select></label>'
            '<button type="button" class="btn rs-ir" disabled>Ver a rota</button></div>')


def pg_rotas(B: Base, rota_pag) -> str:
    rs = sorted(rota_pag, key=lambda r: -B.soma(B.rota, r, B.u3).prev)
    lin = "".join(f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(o, d)}/">{esc(B.cod(o))} → {esc(B.cod(d))}</a> '
                  f'<span class="small">{esc(B.aero_nome(o))} → {esc(B.aero_nome(d))}</span></td>'
                  f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>'
                  for (o, d), x in ((r, B.soma(B.rota, r, B.u3)) for r in rs[:200]))
    corpo = f"""<section class="hero"><h1>Rotas</h1>
<p class="lead">Escolha a origem e o destino para ver a pontualidade e o preço de qualquer uma das {nf(len(rota_pag))} rotas diretas. Abaixo, as 200 com mais voos nos últimos 3 meses.</p>
{seletor_rota(B, rota_pag)}
<div class="busca" role="search"><label for="busca" class="sr">Buscar rota</label><input id="busca" type="search" autocomplete="off" placeholder="Ex.: GRU SSA, Recife, Congonhas"><div id="busca-res" aria-live="polite"></div></div></section>
<section class="card"><div class="tw"><table><thead><tr><th scope="col">Rota</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos (3 meses)</th></tr></thead><tbody>{lin}</tbody></table></div></section>"""
    return pagina(B, "/rotas/", "Rotas aéreas no Brasil: atrasos e cancelamentos | Voo em Números",
                  "Pontualidade e cancelamentos das rotas domésticas com mais voos no Brasil, com dados oficiais da ANAC.",
                  corpo, "/rotas/", migalhas=[("", "Rotas")])


PERIODOS = [("Madrugada (0h–6h)", 0, 6), ("Manhã (6h–12h)", 6, 12), ("Tarde (12h–18h)", 12, 18), ("Noite (18h–24h)", 18, 24)]


def trajeto_btn(B: Base, o: str, d: str) -> str:
    k = (cid_slug(B, o), cid_slug(B, d))
    return (f'<a class="btn sec" href="/trajetos/{k[0]}-para-{k[1]}/">Todos os voos {esc(B.cidade(o))} → {esc(B.cidade(d))}</a>'
            if k in B.pag_pares else "")


def pg_rota(B: Base, o: str, d: str, rota_pag, voo_pag) -> str:
    co, cd = B.cod(o), B.cod(d)
    no, nd = B.aero_nome(o), B.aero_nome(d)
    a3 = B.soma(B.rota, (o, d), B.u3)
    am, am0 = B.rota[B.ref].get((o, d)), B.rota.get(B.ant, {}).get((o, d))
    mes = mes_nome(B.ref)
    usa_mes = am is not None and am.prev >= 30
    a, a0, base_txt = (am, am0, mes) if usa_mes else (a3, None, "últimos 3 meses")
    rot, val, pers = serie_13(B, B.rota, (o, d))
    # companhias
    cs = []
    for c in {k[0] for m in B.u3 for k in B.cia_rota[m] if k[1] == o and k[2] == d}:
        x = B.soma(B.cia_rota, (c, o, d), B.u3)
        if x.prev:
            cs.append((c, x))
    cs.sort(key=lambda t: -(t[1].p_pont or 0))
    lin_c = "".join(f'<tr><td>{B.link_cia(c)}</td><td style="min-width:180px">{meter(x.p_pont)}</td>'
                    f'<td class="r num">{pc(x.p_canc)}</td><td class="r num">{min_txt(x.media_atr)}</td><td class="r num">{nf(x.prev)}</td></tr>' for c, x in cs)
    # voos
    vs = []
    per = [Acc() for _ in PERIODOS]
    for (c, n), legs in B.voo_legs.items():
        x = legs.get((o, d))
        if not x or not x.prev:
            continue
        hora = B.voo_hora[(c, n, o, d)].most_common(1)[0][0] if B.voo_hora[(c, n, o, d)] else ""
        vs.append(((c, n), x, hora))
        if hora:
            h = int(hora[:2])
            for i, (_, h0, h1) in enumerate(PERIODOS):
                if h0 <= h < h1:
                    per[i].soma(x)
    vs.sort(key=lambda t: (-(t[1].p_pont if t[1].med >= 5 else -1), t[2]))
    lin_v = "".join(
        f'<tr><td>{f"<a href=/voos/{B.voo_slug(*k)}/>{esc(B.cod_voo(*k))}</a>" if k in voo_pag else esc(B.cod_voo(*k))}</td>'
        f'<td>{esc(B.cia_nome(k[0]))}</td><td class="num">{esc(h)}</td><td class="r num"><b>{pc(x.p_pont) if x.med >= 5 else "–"}</b></td>'
        f'<td class="r num">{min_txt(x.spos / x.med) if x.med >= 5 else "–"}</td><td class="r num">{pc(x.p_canc)}</td></tr>'
        for k, x, h in vs)
    # períodos e dias da semana
    per_html = "".join(f'<div style="display:flex;flex-direction:column;gap:6px"><div style="display:flex;justify-content:space-between;font-size:14px">'
                       f'<span>{nome}</span><span class="num"><b>{pc(x.p_pont)}</b> <span class="small">({nf(x.med)} voos)</span></span></div>{meter(x.p_pont).split("<b>")[0]}</div></div>'
                       for (nome, _, _), x in zip(PERIODOS, per) if x.med >= 10)
    sem = [[0, 0] for _ in range(7)]
    for m in B.u3:
        for i, (med, pont) in enumerate(B.meses[m]["rota_semana"].get(f"{o}-{d}", [[0, 0]] * 7)):
            sem[i][0] += med
            sem[i][1] += pont
    sem_val = [(p / m if m >= 8 else None) for m, p in sem]
    validos = [v for v in sem_val if v is not None]
    cores = ["#C2410C" if (v is not None and validos and v == min(validos)) else "#2A9DE0" for v in sem_val]
    sem_html = svg_barras(DIAS_CURTO, sem_val, destaque_ultimo=False, altura=200, cores=cores, largura=420,
                          aria=f"Pontualidade por dia da semana na rota {co}-{cd}") if len(validos) >= 5 else '<p class="small">Poucos voos para comparar os dias da semana.</p>'
    dur = ""
    if a3.dprev and a3.dreal:
        n_med = a3.med
        dur = f"A duração real média foi de {min_txt(a3.dreal / n_med)}, contra {min_txt(a3.dprev / n_med)} previstos."
    melhor_v = next((t for t in vs if t[1].med >= 10), None)
    melhor_c = cs[0] if len(cs) > 1 else None
    pior_p = min([(nome, x) for (nome, _, _), x in zip(PERIODOS, per) if x.med >= 20], key=lambda t: t[1].p_pont, default=None)
    melhor_p = max([(nome, x) for (nome, _, _), x in zip(PERIODOS, per) if x.med >= 20], key=lambda t: t[1].p_pont, default=None)
    pares = [(f"Quanto atrasam os voos de {B.cidade(o)} para {B.cidade(d)}?",
              f"Em {base_txt}, {pc(a.p_pont)} dos voos {co}–{cd} chegaram no horário (até 30 minutos de atraso) e {pc(a.p_canc)} foram cancelados. "
              f"Entre os que atrasaram mais de 30 minutos, o atraso médio foi de {min_txt(a.media_atr)}.")]
    if melhor_v:
        pares.append((f"Qual o voo mais pontual de {B.cidade(o)} para {B.cidade(d)}?",
                      f"Nos últimos 3 meses, o {B.cod_voo(*melhor_v[0])} da {B.cia_nome(melhor_v[0][0])}, com saída prevista às {melhor_v[2]}, "
                      f"chegou no horário em {pc(melhor_v[1].p_pont)} das vezes."))
    if melhor_c:
        pares.append((f"Qual companhia é mais pontual na rota {co}–{cd}?",
                      f"Nos últimos 3 meses, a {B.cia_nome(melhor_c[0])}, com {pc(melhor_c[1].p_pont)} dos voos no horário."))
    if pior_p and melhor_p and pior_p[0] != melhor_p[0]:
        pares.append((f"Qual o melhor horário para voar de {co} para {cd}?",
                      f"Voos com saída na {melhor_p[0].split(' (')[0].lower()}: {pc(melhor_p[1].p_pont)} no horário, contra "
                      f"{pc(pior_p[1].p_pont)} na {pior_p[0].split(' (')[0].lower()}, nos últimos 3 meses."))
    preco, pares_p, res_p = bloco_preco(B, [f"{o}-{d}"], f"{B.cidade(o)} para {B.cidade(d)}", "r")
    pares = pares_p + pares if pares_p else pares
    faq, ld = faq_html(pares)
    volta = (d, o) in rota_pag
    def _vol(k):
        x = B.soma(B.rota, k, B.u3)
        return x.prev if x else 0
    def _links(ks, rotulo):
        return "".join(f'<a class="btn sec" href="/rotas/{B.rota_slug(*k)}/">{esc(B.cod(k[0]))} → {esc(B.cod(k[1]))}{rotulo(k)}</a>' for k in ks)
    outras_o = sorted((k for k in rota_pag if k[0] == o and k != (o, d)), key=lambda k: -_vol(k))[:8]
    outras_d = sorted((k for k in rota_pag if k[1] == d and k != (o, d) and k != (d, o)), key=lambda k: -_vol(k))[:8]
    rel_html = ""
    if outras_o:
        rel_html += f'<section class="card"><h2>Outras rotas saindo de {esc(B.cidade(o))} ({esc(co)})</h2><div class="btns">{_links(outras_o, lambda k: " · " + esc(B.cidade(k[1])))}</div></section>'
    if outras_d:
        rel_html += f'<section class="card"><h2>Outras rotas chegando a {esc(B.cidade(d))} ({esc(cd)})</h2><div class="btns">{_links(outras_d, lambda k: " · " + esc(B.cidade(k[0])))}</div></section>'
    corpo = f"""<section class="hero"><span class="kicker">Rota · voos diretos</span><h1>{esc(B.nome_cod(o))} → {esc(B.nome_cod(d))}</h1>
<p class="lead">Em {base_txt}, <strong>{pc(a.p_pont)}</strong> dos voos chegaram no horário e <strong>{pc(a.p_canc)}</strong> foram cancelados. {dur}</p>
<div class="btns">{f'<a class="btn sec" href="/rotas/{B.rota_slug(d, o)}/">Ver a volta: {esc(cd)} → {esc(co)}</a>' if volta else ""}{f'<a class="btn sec" href="/aeroportos/{B.aero_slug(o)}/">Aeroporto {esc(co)}</a>' if o in B.pag_aero else ""}{f'<a class="btn sec" href="/aeroportos/{B.aero_slug(d)}/">Aeroporto {esc(cd)}</a>' if d in B.pag_aero else ""}{trajeto_btn(B, o, d)}</div></section>
{tiles_acc(a, a0)}
{preco}
{dem_rota(B, o, d)}
<section class="card"><div class="card-head"><h2>Por companhia nesta rota</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Atraso médio dos atrasados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Os voos desta rota, do mais ao menos pontual</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Companhia</th><th scope="col">Saída prevista</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio</th><th scope="col" class="r">Cancelados</th></tr></thead><tbody>{lin_v}</tbody></table></div>
<p class="nota">Atraso médio = média do atraso na chegada, contando todos os voos realizados (os que chegaram adiantados contam como zero).</p></section>
<div class="grid2">
<section class="card"><h2>Melhor horário para voar</h2>{per_html or '<p class="small">Poucos voos para comparar os horários.</p>'}<p class="nota">Pelo horário previsto de saída, últimos 3 meses.</p></section>
<section class="card"><h2>Por dia da semana</h2>{sem_html}</section>
</div>
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, periodos=pers, aria=f"Percentual de voos {co}-{cd} no horário mês a mês")}</section>
{rel_html}
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/rotas/{B.rota_slug(o, d)}/", f"Voos {B.cidade(o)} ({co}) → {B.cidade(d)} ({cd}): atrasos e {'preço' if res_p else 'cancelamentos'} | Voo em Números",
                  (f"Tarifa média de {rs(res_p['media'])} em {mes_nome(B.tar.ref)}, com curva de preços e evolução em 13 meses. " if res_p else "")
                  + f"{cap(base_txt)}: {pc(a.p_pont)} dos voos {co}–{cd} chegaram no horário e {pc(a.p_canc)} foram cancelados. Veja o voo e a companhia mais pontuais.",
                  corpo, "/rotas/", migalhas=[("/rotas/", "Rotas"), ("", f"{co} → {cd}")], jsonld=[ld],
                  continuar=itens_cidade(B, d)[:2] + itens_cidade(B, o)[:1])


# Link de afiliado de indenização (ex.: AirHelp): URL em afiliado_indenizacao.txt na raiz; vazio ou ausente = sem link
_AFI = RAIZ / "afiliado_indenizacao.txt"
AFILIADO_INDENIZACAO = _AFI.read_text(encoding="utf-8").strip() if _AFI.exists() else ""
if AFILIADO_INDENIZACAO and not AFILIADO_INDENIZACAO.startswith("https://"):
    AFILIADO_INDENIZACAO = ""


def calc_atraso_voo(cod: str, a) -> str:
    """"Seu voo atrasou?": o que a companhia deve oferecer conforme a espera (Res. ANAC 400/2016, com a Res. 813/2026)."""
    tot = a.med or 0
    p2 = (a.b[2] + a.b[3]) / tot if tot else None
    p4 = a.b[3] / tot if tot else None
    hist = ""
    if p2 == 0:
        hist = f'<p class="small">No histórico do {esc(cod)}, nenhuma viagem chegou com mais de 2 horas de atraso nos últimos 3 meses.</p>'
    elif p2 is not None:
        hist = (f'<p class="small">No histórico do {esc(cod)}, {pc(p2)} das viagens chegaram com mais de 2 horas de atraso '
                f'e {pc(p4)} com mais de 4 horas (últimos 3 meses).</p>')
    afi = ""
    if AFILIADO_INDENIZACAO:
        afi = (f'<p class="pub"><span class="small">Publicidade</span> Teve atraso longo ou cancelamento e a companhia não resolveu? '
               f'<a href="{esc(AFILIADO_INDENIZACAO)}" target="_blank" rel="sponsored noopener">Veja se o seu caso pode ter indenização</a>. '
               'O serviço cobra uma parte do valor só se você receber; também dá para reclamar sem custo na ANAC, no consumidor.gov.br ou no Juizado Especial.</p>')
    base = '<li>Informação clara sobre o motivo, a nova previsão e as alternativas, por canais digitais e no aeroporto.</li>'
    comida = '<li><b>Alimentação</b>: crédito, refeição ou solução equivalente.</li>'
    opcoes = ('<li><b>Você escolhe</b>: outro voo, reembolso integral da passagem ou seguir por outro meio de transporte.</li>'
              '<li><b>Hospedagem e transporte</b> de ida e volta, se precisar passar a noite (quem mora na cidade pode ficar só com o transporte).</li>')
    casos = [("Menos de 2 horas", base, ""),
             ("De 2 a 4 horas", base + comida, ""),
             ("Mais de 4 horas", base + comida + opcoes, afi),
             ("Voo cancelado", base + '<li><b>Você escolhe</b>: outro voo, reembolso integral ou outro meio de transporte.</li>'
              + '<li>Alimentação a partir de 2 horas de espera e hospedagem a partir de 4 horas, se precisar passar a noite.</li>', afi)]
    det = "".join(f'<details class="calc" name="atr"{" open" if i == 0 else ""}><summary>{t}</summary><ul>{li}</ul>{extra}</details>'
                  for i, (t, li, extra) in enumerate(casos))
    return (f'<section class="card" id="atrasou"><h2>Seu voo atrasou? O que a companhia deve oferecer</h2>'
            f'<p class="small">Toque no tempo de espera no aeroporto:</p>{det}{hist}'
            '<p class="nota">Regras da ANAC (Resolução 400/2016, atualizada em outubro de 2026). A assistência vale mesmo com mau tempo. '
            'Se não receber, guarde comprovantes e reclame no balcão, no SAC e na ANAC. <a href="/direitos/">Guia completo dos seus direitos</a>.</p></section>')



def botao_ao_vivo(c: str, n: str) -> str:
    """Abre o voo em tempo real no Flightradar24 (só para companhias com código IATA conhecido)."""
    iata = CIAS.get(c, ("", "", ""))[1]
    if not iata or not n.isdigit():
        return ""
    fr = {"TAM": "jj"}.get(c, iata.lower())  # no Flightradar24 os voos da LATAM Brasil aparecem como JJ, e não LA
    return (f'<a class="btn" href="https://www.flightradar24.com/data/flights/{fr}{n}" target="_blank" '
            f'rel="noopener nofollow">Acompanhe o voo {iata} {n} ↗</a>')


DIARIO_ARQ = RAIZ / "data" / "voo_a_voo.json"
SEM_CURTO = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
VOO_A_VOO_VISIVEIS = 7


def carrega_diario() -> dict | None:
    try:
        return json.loads(DIARIO_ARQ.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _situacao(r) -> tuple[str, str]:
    """(texto, classe) de uma viagem: [dia, prevista, saiu, chegou, atraso, cancelado]."""
    if r[5]:
        return "Cancelado", "vv-canc"
    if r[4] is None:
        return "Sem registro", ""
    if r[4] <= 30:
        return "No horário", "vv-ok"
    return f"Atrasou {min_txt(r[4]).replace(' ', '&nbsp;')}", "vv-atr"


def voo_a_voo(B, c: str, n: str, o: str, d: str, cod: str):
    """Cartão com cada viagem do voo no mês mais recente publicado pela ANAC. Devolve (html, par de FAQ ou None)."""
    D = getattr(B, "diario", None)
    if not D:
        return "", None
    regs = D.get("voos", {}).get(f"{c}|{n}|{o}|{d}")
    if not regs:
        return "", None
    mes = D["mes"]
    ano, mm = int(mes[:4]), int(mes[5:])
    mes_n = nome_mes(mes)
    linhas = []
    for r in sorted(regs, key=lambda r: (r[0], r[1]), reverse=True):
        dia = dt.date(ano, mm, r[0])
        txt, cls = _situacao(r)
        linhas.append(f'<tr><td class="num">{r[0]:02d}/{mm:02d}<span class="small">{SEM_CURTO[dia.weekday()]}</span></td><td class="num">{esc(r[1])}</td>'
                      f'<td class="num">{esc(r[2]) or "–"}</td><td class="num">{esc(r[3]) or "–"}</td><td class="{cls}">{txt}</td></tr>')
    cab = ('<thead><tr><th scope="col">Dia</th><th scope="col">Previsto</th><th scope="col">Saiu</th>'
           '<th scope="col">Chegou</th><th scope="col">Situação</th></tr></thead>')
    tab = f'<div class="tw"><table class="vv" data-sem-export data-sem-compartilhar>{cab}<tbody>{"".join(linhas[:VOO_A_VOO_VISIVEIS])}</tbody></table></div>'
    if len(linhas) > VOO_A_VOO_VISIVEIS:
        tab += (f'<details class="calc"><summary>Ver os outros {len(linhas) - VOO_A_VOO_VISIVEIS} dias de {mes_n}</summary>'
                f'<div class="tw"><table class="vv" data-sem-export data-sem-compartilhar>{cab}<tbody>{"".join(linhas[VOO_A_VOO_VISIVEIS:])}</tbody></table></div></details>')
    ok = sum(1 for r in regs if not r[5] and r[4] is not None and r[4] <= 30)
    atr = [r for r in regs if not r[5] and r[4] is not None and r[4] > 30]
    canc = sum(1 for r in regs if r[5])
    partes = [f"{ok} no horário"]
    if atr:
        partes.append(f"{len(atr)} com atraso de mais de 30 min")
    if canc:
        partes.append(f"{canc} cancelad{'a' if canc == 1 else 'as'}")
    resumo = f"Em {mes_n} de {ano}, o {esc(cod)} tinha {len(regs)} {'viagem prevista' if len(regs) == 1 else 'viagens previstas'} de {esc(B.cod(o))} para {esc(B.cod(d))}: " + ", ".join(partes[:-1]) + (" e " if len(partes) > 1 else "") + partes[-1] + "."
    pior = max(atr, key=lambda r: r[4]) if atr else None
    if pior:
        resumo += f" O maior atraso foi em {pior[0]:02d}/{mm:02d}: {min_txt(pior[4])} na chegada."
    ao_vivo = botao_ao_vivo(c, n)
    html = (f'<section class="card" id="voo-a-voo"><div class="card-head"><h2>Voo a voo em {mes_n}</h2>'
            f'<span class="small">{esc(B.cod(o))} → {esc(B.cod(d))}</span></div><p>{resumo}</p>{tab}'
            f'<p class="nota">Horários locais. "No horário" = chegou até 30 min depois do previsto. A ANAC publica cada mês com cerca de 2 meses de atraso, '
            f'por isso {mes_n} é o mês mais recente.{" Para saber como está o voo hoje, use o botão de acompanhamento ao vivo." if ao_vivo else ""}</p></section>')
    faq = (f"Quantas vezes o voo {cod} atrasou em {mes_n}?",
           re.sub(r"<[^>]+>", "", resumo))
    return html, faq


def pg_voo(B: Base, k, trecho: str, voo_pag) -> str:
    c, n = k
    cod, cia = B.cod_voo(c, n), B.cia_nome(c)
    legs = sorted(B.voo_legs[k].items(), key=lambda t: -t[1].prev)
    a = Acc()
    for _, x in legs:
        a.soma(x)
    rot, val, pers = serie_13(B, B.voo, k)
    lin_l = []
    for (o, d), x in legs:
        hora = B.voo_hora[(c, n, o, d)].most_common(1)[0][0] if B.voo_hora[(c, n, o, d)] else ""
        info = B.voo_info.get((c, n, o, d), ("", "", 0))
        lin_l.append(f'<tr><td class="wrap">{B.link_rota(o, d, esc(B.cod(o)) + " → " + esc(B.cod(d)))} '
                     f'<span class="small">{esc(B.cidade(o))} → {esc(B.cidade(d))}</span></td><td class="num">{esc(hora)}</td>'
                     f'<td>{esc(info[1])}</td><td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>')
    # comparação com outros voos do trecho principal
    (o, d), _ = legs[0]
    outros = []
    for kk, lg in B.voo_legs.items():
        x = lg.get((o, d))
        if x and x.med >= 10:
            h = B.voo_hora[(kk[0], kk[1], o, d)].most_common(1)[0][0] if B.voo_hora[(kk[0], kk[1], o, d)] else ""
            outros.append((kk, x, h))
    outros.sort(key=lambda t: -(t[1].p_pont or 0))
    pos = next((i for i, t in enumerate(outros, 1) if t[0] == k), None)
    lin_o = "".join(f'<tr{" style=background:var(--acc-l)" if kk == k else ""}><td>{f"<a href=/voos/{B.voo_slug(*kk)}/>{esc(B.cod_voo(*kk))}</a>" if kk in voo_pag and kk != k else esc(B.cod_voo(*kk))}</td>'
                    f'<td>{esc(B.cia_nome(kk[0]))}</td><td class="num">{esc(h)}</td><td class="r num"><b>{pc(x.p_pont)}</b></td></tr>' for kk, x, h in outros[:15])
    dist = [("Até 30 min (no horário)", a.pont), ("30 a 60 min", a.b[0]), ("1 a 2 horas", a.b[1]), ("2 a 4 horas", a.b[2]), ("Mais de 4 horas", a.b[3])]
    dist_html = "".join(f'<div style="display:flex;flex-direction:column;gap:4px"><div style="display:flex;justify-content:space-between;font-size:14px">'
                        f'<span>{nome}</span><span class="num">{nf(q)} voos</span></div>{meter(q / a.med if a.med else None, ruim=i > 0)}</div>'
                        for i, (nome, q) in enumerate(dist))
    hora0 = B.voo_hora[(c, n, o, d)].most_common(1)[0][0] if B.voo_hora[(c, n, o, d)] else ""
    rank_txt, alt_html = "", ""
    if pos and len(outros) > 2:
        lugar_r = "o mais pontual" if pos == 1 else "o menos pontual" if pos == len(outros) else f"o {pos}º mais pontual"
        rank_txt = f" É {lugar_r} entre {len(outros)} voos diretos {esc(B.cod(o))} → {esc(B.cod(d))}."
        melhor = outros[0]
        if pos > 1 and melhor[1].p_pont is not None and a.p_pont is not None and melhor[1].p_pont - a.p_pont >= 0.05:
            mk = melhor[0]
            nome_m = (f'<a href="/voos/{B.voo_slug(*mk)}/">{esc(B.cod_voo(*mk))}</a>' if mk in voo_pag else esc(B.cod_voo(*mk)))
            alt_html = (f'<section class="card destaque"><p><b>Quer chegar no horário?</b> O {nome_m} ({esc(B.cia_nome(mk[0]))}'
                        f'{f", saída às {esc(melhor[2])}" if melhor[2] else ""}) é o mais pontual de {esc(B.cod(o))} para {esc(B.cod(d))}: '
                        f'chegou no horário em <b>{pc(melhor[1].p_pont)}</b> das viagens, contra {pc(a.p_pont)} do {esc(cod)}.</p></section>')
    pares = [(f"O voo {cod} costuma atrasar?",
              f"Nos últimos 3 meses, o {cod} da {cia} ({trecho}) chegou no horário em {pc(a.p_pont)} das vezes e foi cancelado em {pc(a.p_canc)} dos dias previstos."),
             (f"Quanto tempo atrasa o voo {cod}?",
              f"Quando atrasou mais de 30 minutos, o atraso médio na chegada foi de {min_txt(a.media_atr)}. "
              f"{pc(a.p_a60)} das viagens chegaram com mais de 1 hora de atraso.")]
    if pos and len(outros) > 1:
        lugar = ("o mais pontual" if pos == 1 else "o menos pontual" if pos == len(outros) else f"o {pos}º mais pontual")
        pares.append((f"O {cod} é um dos voos mais pontuais de {B.cod(o)} para {B.cod(d)}?",
                      f"Ele é {lugar} entre {len(outros)} voos diretos {B.cod(o)}–{B.cod(d)} com pelo menos 10 viagens nos últimos 3 meses."))
    vv_html, vv_faq = voo_a_voo(B, c, n, o, d, cod)
    if vv_faq:
        pares.insert(1, vv_faq)
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Voo · {esc(cia)}</span><h1>Voo {esc(cod)}: {esc(trecho)}</h1>
<p class="lead">Nos últimos 3 meses, o {esc(cod)}{f" (saída prevista às {hora0})" if hora0 else ""} chegou no horário em <strong>{pc(a.p_pont)}</strong> das viagens e foi cancelado em <strong>{pc(a.p_canc)}</strong> dos dias previstos.{rank_txt}</p>
<div class="btns"><a class="btn" href="#atrasou">Seu voo atrasou?</a>{B.link_rota(o, d, "Ver a rota " + esc(B.cod(o)) + " → " + esc(B.cod(d))).replace("<a ", '<a class="btn sec" ', 1) if (o, d) in B.pag_rotas else ""}</div></section>
<div class="tiles">{tile("Chegou no horário", pc(a.p_pont), "até 30 min de atraso")}{tile("Cancelado", pc(a.p_canc), f"{nf(a.canc)} de {nf(a.prev)} previstos")}{tile("Atraso médio quando atrasa", min_txt(a.media_atr), "atrasos acima de 30 min")}{tile("Atrasos acima de 1 hora", pc(a.p_a60), f"{nf(a.b[1] + a.b[2] + a.b[3])} viagens")}</div>
<section class="card"><div class="card-head"><h2>Trechos deste voo</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Trecho</th><th scope="col">Saída prevista</th><th scope="col">Avião</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelado</th><th scope="col" class="r">Previstos</th></tr></thead><tbody>{"".join(lin_l)}</tbody></table></div></section>
{vv_html}
{calc_atraso_voo(cod, a)}
{f'<div class="btns" style="margin:0 0 16px">{botao_ao_vivo(c, n)}</div>' if botao_ao_vivo(c, n) else ""}
{alt_html}
{preco_card_voo(B, o, d)}
<div class="grid2">
<section class="card"><h2>Quanto ele atrasa</h2>{dist_html}<p class="nota">Atraso na chegada das {nf(a.med)} viagens realizadas nos últimos 3 meses.</p></section>
<section class="card"><div class="card-head"><h2>Outros voos {esc(B.cod(o))} → {esc(B.cod(d))}</h2><span class="small">Do mais ao menos pontual</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Companhia</th><th scope="col">Saída</th><th scope="col" class="r">No horário</th></tr></thead><tbody>{lin_o}</tbody></table></div></section>
</div>
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, periodos=pers, aria=f"Percentual de viagens do voo {cod} no horário mês a mês")}</section>
{linha_destino(B, d)}
{faq}"""
    # título no formato da busca ("ad 4942", "voo 2914 azul"): quem procura quer saber horário e se o voo atrasa
    return pagina(B, f"/voos/{B.voo_slug(c, n)}/", f"Voo {cod} {cia} ({trecho}): horário e atrasos, {pc(a.p_pont)} no horário",
                  f"O voo {cod} da {cia} ({trecho}){f' sai às {hora0}' if hora0 else ''} e chegou no horário em {pc(a.p_pont)} das vezes "
                  f"nos últimos 3 meses, com {pc(a.p_canc)} de cancelamentos. Veja o atraso médio, o histórico e o status ao vivo.",
                  corpo, "/rotas/", migalhas=[("/companhias/" + B.cia_slug(c) + "/", cia), ("", f"Voo {cod}")], jsonld=[ld],
                  continuar=itens_cidade(B, d)[:2] + itens_cidade(B, o)[:1])


def periodo_fim(B: Base):
    """Último fim de ano com dezembro e janeiro completos nos dados."""
    for m in reversed(B.lista):
        a, mm = m.split("-")
        if mm == "01" and f"{int(a) - 1}-12" in B.meses:
            ano = int(a) - 1
            ini, fim = dt.date(ano, 12, 19), dt.date(ano + 1, 1, 4)
            dias = [ini + dt.timedelta(days=i) for i in range((fim - ini).days + 1)]
            return {"ano": ano, "dias": dias, "meses": [f"{ano}-12", f"{ano + 1}-01"], "nov": f"{ano}-11"}
    return None


def pg_fim(B: Base, fim, aero_pag) -> str:
    ano = fim["ano"]
    def junta(dst, src):
        for k, v in src.items():
            dst[k] = [x + y for x, y in zip(dst.get(k, [0, 0, 0, 0]), v)]
    D = {}
    DC = defaultdict(dict)
    DA = defaultdict(dict)
    for m in fim["meses"]:
        junta(D, B.meses[m]["dias"])
        for c, dd in B.meses[m]["dias_cia"].items():
            junta(DC[c], dd)
        for a, dd in B.meses[m]["aero_dia"].items():
            junta(DA[a], dd)
    # piores dias de dezembro inteiro (fora do período das festas)
    dez = sorted(((k, v[3] / v[2], v[1]) for k, v in D.items() if k.startswith(f"{ano}-12") and v[2] >= 500), key=lambda t: t[1])
    antes = [t for t in dez[:2] if t[0] < f"{ano}-12-19"]
    dez_txt = ""
    if antes:
        dez_txt = (" Os piores dias de dezembro, porém, vieram antes das festas: " + " e ".join(
            f"{int(k[8:])}/12 ({pc(p)} no horário, {nf(c)} cancelamentos)" for k, p, c in antes) + ".")
    chaves = [d.isoformat() for d in fim["dias"]]

    def tot(dd):
        s = [0, 0, 0, 0]
        for k in chaves:
            v = dd.get(k)
            if v:
                s = [x + y for x, y in zip(s, v)]
        return s
    S = tot(D)
    p_pont = S[3] / S[2] if S[2] else None
    p_canc = S[1] / S[0] if S[0] else None
    nov = B.tot.get(fim["nov"])
    vals = [(D[k][3] / D[k][2]) if k in D and D[k][2] else None for k in chaves]
    rots = [f"{d.day:02d}/{d.month:02d}" for d in fim["dias"]]
    validos = [v for v in vals if v is not None]
    corte = sorted(validos)[2] if len(validos) > 3 else 0
    cores = ["#C2410C" if v is not None and v <= corte else "#2A9DE0" for v in vals]
    graf = svg_barras(rots, vals, destaque_ultimo=False, altura=210, cores=cores,
                      aria=f"Pontualidade diária dos voos domésticos de 19/12/{ano} a 04/01/{ano + 1}")
    piores = sorted([(k, v) for k, v in zip(fim["dias"], vals) if v is not None], key=lambda t: t[1])[:3]
    piores_txt = ", ".join(f"{d.day} de {MESES[d.month - 1]} ({pc(v)})" for d, v in piores)
    # companhias
    lin_c = []
    for c, dd in DC.items():
        s = tot(dd)
        if s[0] >= 500:
            lin_c.append((c, s))
    lin_c.sort(key=lambda t: -(t[1][3] / t[1][2] if t[1][2] else 0))
    tab_c = "".join(f'<tr><td>{B.link_cia(c)}</td><td style="min-width:180px">{meter(s[3] / s[2] if s[2] else None)}</td>'
                    f'<td class="r num">{pc(s[1] / s[0] if s[0] else None)}</td><td class="r num">{nf(s[0])}</td></tr>' for c, s in lin_c)
    # aeroportos
    la = []
    for a, dd in DA.items():
        s = tot(dd)
        if s[0] >= 600 and a in aero_pag:
            la.append((a, s))
    la.sort(key=lambda t: (t[1][3] / t[1][2] if t[1][2] else 1))
    tab_a = "".join(f'<tr><td><a href="/aeroportos/{B.aero_slug(a)}/">{esc(B.cod(a))}</a> <span class="small">{esc(B.aero_nome(a))}</span></td>'
                    f'<td class="r num"><b>{pc(s[3] / s[2] if s[2] else None)}</b></td><td class="r num">{pc(s[1] / s[0] if s[0] else None)}</td><td class="r num">{nf(s[0])}</td></tr>'
                    for a, s in la[:12])
    comp = ""
    if nov and nov.med and p_pont is not None:
        dif = 100 * (p_pont - nov.p_pont)
        comp = (f" Em novembro de {ano}, um mês comum, eram {pc(nov.p_pont)} no horário: "
                f"{'uma queda' if dif < 0 else 'uma alta'} de {nf(abs(dif), 1)} pontos percentuais.")
    pares = [(f"Os voos atrasam mais no fim de ano?",
              f"Entre 19 de dezembro de {ano} e 4 de janeiro de {ano + 1}, {pc(p_pont)} dos voos domésticos chegaram no horário e {pc(p_canc)} foram cancelados.{comp}"),
             ("Quais foram os piores dias para voar?", f"Os dias com menor pontualidade foram {piores_txt}.")]
    if lin_c:
        c, s = lin_c[0]
        pares.append(("Qual companhia foi mais pontual no fim de ano?",
                      f"A {B.cia_nome(c)}, com {pc(s[3] / s[2])} dos voos no horário entre 19/12/{ano} e 04/01/{ano + 1}."))
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Natal e Ano-Novo de {ano}</span><h1>Voos no fim de ano: como foram atrasos e cancelamentos</h1>
<p class="lead">Entre 19 de dezembro de {ano} e 4 de janeiro de {ano + 1}, <strong>{pc(p_pont)}</strong> dos voos domésticos chegaram no horário e <strong>{pc(p_canc)}</strong> foram cancelados.{comp}{dez_txt}</p></section>
<div class="tiles">{tile("Chegaram no horário", pc(p_pont), "até 30 min de atraso")}{tile("Cancelados", pc(p_canc), f"{nf(S[1])} voos")}{tile("Voos previstos", nf(S[0]), f"em {len(chaves)} dias")}{tile("Pior dia", f"{piores[0][0].day:02d}/{piores[0][0].month:02d}" if piores else "–", f"{pc(piores[0][1])} no horário" if piores else "")}</div>
<section class="card"><h2>Dia a dia</h2>{graf}<p class="nota">Em laranja, os 3 dias com menor pontualidade.</p></section>
<div class="grid2">
<section class="card"><h2>Por companhia</h2><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{tab_c}</tbody></table></div></section>
<section class="card"><h2>Aeroportos com mais atrasos</h2><div class="tw"><table><thead><tr><th scope="col">Aeroporto</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{tab_a}</tbody></table></div><p class="nota">Aeroportos com pelo menos 600 partidas no período.</p></section>
</div>
{faq}"""
    return pagina(B, "/fim-de-ano/", f"Voos no fim de ano: atrasos e cancelamentos no Natal e Ano-Novo de {ano} | Voo em Números",
                  f"Entre 19/12/{ano} e 04/01/{ano + 1}, {pc(p_pont)} dos voos domésticos chegaram no horário e {pc(p_canc)} foram cancelados. Piores dias, companhias e aeroportos.",
                  corpo, "/fim-de-ano/", migalhas=[("", "Fim de ano")], jsonld=[ld])


# Sugestões e críticas: a mensagem chega por e-mail via FormSubmit (sem cadastro e sem servidor próprio).
# Para esconder o e-mail do HTML, troque FORM_EMAIL pelo código aleatório que o FormSubmit envia após a ativação.
FORM_EMAIL = "oleoemnumeros@gmail.com"
FORM_JS = """<script>
(function () {
  var f = document.getElementById("sug"); if (!f || !window.fetch) return;
  var msg = document.getElementById("sug-msg"), ok = document.getElementById("enviado"), b = f.querySelector("button");
  try { var r = document.referrer; if (r && new URL(r).host === location.host && r.indexOf("/sugestoes/") < 0) f.elements.pagina.value = r; } catch (e) {}
  f.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (f.elements._honey.value) return;
    b.disabled = true; msg.textContent = "Enviando…";
    var d = {}; new FormData(f).forEach(function (v, k) { if (k !== "_next") d[k] = v; });
    fetch("https://formsubmit.co/ajax/__EMAIL__", {method: "POST", headers: {"Content-Type": "application/json", "Accept": "application/json"}, body: JSON.stringify(d)})
      .then(function (x) { return x.json(); })
      .then(function (j) {
        if (j && (j.success === true || j.success === "true")) { ok.className += " on"; f.hidden = true; ok.focus(); }
        else throw new Error("falhou");
      })
      .catch(function () { b.disabled = false; msg.textContent = "Não foi possível enviar agora. Tente de novo em instantes ou escreva para __EMAIL__."; });
  });
})();
</script>"""


def form_sugestoes(nome_site: str, base: str) -> str:
    """Corpo da página /sugestoes/: formulário com envio sem sair da página e alternativa sem JavaScript."""
    return (
        '<p class="lede">Viu um erro, sentiu falta de um dado ou tem uma ideia? Escreva aqui. Cada mensagem chega ao e-mail do portal e é lida por uma pessoa.</p>'
        '<div class="sug-ok" id="enviado" tabindex="-1" role="status"><strong>Mensagem enviada. Obrigado!</strong>'
        '<p>Lemos todas. Se você deixou um e-mail, a resposta vai para ele.</p></div>'
        f'<form class="sug" id="sug" method="post" action="https://formsubmit.co/{FORM_EMAIL}">'
        '<label>Tipo de mensagem<select name="tipo"><option>Sugestão</option><option>Crítica</option>'
        '<option>Erro em um dado ou página</option><option>Outro assunto</option></select></label>'
        '<label>Sua mensagem<textarea name="mensagem" required minlength="10" maxlength="3000" rows="6" placeholder="Conte o que você viu, sentiu falta ou sugere. Se for um erro, diga a página e o número."></textarea></label>'
        '<label><span>Seu nome <span class="opc">(opcional)</span></span><input name="nome" maxlength="80" autocomplete="name"></label>'
        '<label><span>Seu e-mail, se quiser resposta <span class="opc">(opcional)</span></span><input type="email" name="email" maxlength="120" autocomplete="email"></label>'
        f'<input type="hidden" name="_subject" value="[{esc(nome_site)}] Sugestão ou crítica">'
        '<input type="hidden" name="_template" value="table">'
        f'<input type="hidden" name="_next" value="{base}/sugestoes/#enviado">'
        f'<input type="hidden" name="site" value="{esc(nome_site)}">'
        '<input type="hidden" name="pagina" value="">'
        '<input class="hp" type="text" name="_honey" tabindex="-1" autocomplete="off" aria-hidden="true">'
        '<button type="submit">Enviar mensagem</button>'
        '<p class="sug-msg" id="sug-msg" role="status" aria-live="polite"></p></form>'
        '<p class="small">O envio passa pelo serviço FormSubmit (formsubmit.co), que entrega a mensagem ao e-mail do portal. '
        'Não pedimos cadastro nem guardamos mais nada além do que você escrever. '
        f'Se preferir, escreva direto para <a href="mailto:{FORM_EMAIL}">{FORM_EMAIL}</a>.</p>'
        + FORM_JS.replace("__EMAIL__", FORM_EMAIL))


def pg_sugestoes(B: Base) -> str:
    corpo = ('<section class="hero"><h1>Sugestões e críticas</h1></section><section class="card prose">'
             + form_sugestoes("Voo em Números", BASE) + "</section>")
    return pagina(B, "/sugestoes/", "Sugestões e críticas | Voo em Números",
                  "Envie uma sugestão, crítica ou correção para o Voo em Números. A mensagem chega por e-mail e é lida por uma pessoa.",
                  corpo, "/sugestoes/", migalhas=[("", "Sugestões e críticas")])


# Páginas de privacidade e contato (exigidas para anúncios e boa prática de LGPD). O texto é o mesmo em toda a Família em Números.
PRIVACIDADE_HTML = """<p class="lede">Esta página explica quais dados o __NOME__ coleta, por que coleta e quais são os seus direitos. Em resumo: não pedimos cadastro, não vendemos dados e não usamos cookies de rastreamento próprios.</p>
<p class="small">Última atualização: 18 de novembro de 2026.</p>

<h2>Quem somos</h2>
<p>O __NOME__ faz parte da Família em Números, um grupo de portais independentes que organizam dados públicos do Brasil. Não temos ligação com órgãos do governo nem com as empresas citadas nos dados. Para qualquer assunto de privacidade, escreva para <a href="mailto:__EMAIL__">__EMAIL__</a>.</p>

<h2>O que coletamos e para quê</h2>
<ul>
<li><strong>Estatísticas de visitas.</strong> Usamos o GoatCounter, um contador sem cookies que guarda dados agregados, como a página aberta, o site de origem, o tipo de aparelho e de navegador e o país. Ele não identifica quem visita. Serve para saber quais páginas são úteis.</li>
<li><strong>Mensagens.</strong> Se você usar o formulário de <a href="__HREF_SUG__">Sugestões e críticas</a> ou escrever para o e-mail do portal, recebemos o que você escrever e, se informar, o seu nome e o seu e-mail. Usamos só para ler e responder. O formulário é entregue pelo serviço FormSubmit (formsubmit.co).</li>
<li><strong>Dados técnicos de acesso.</strong> O site é hospedado no GitHub Pages, que, como qualquer servidor, pode registrar o endereço IP de quem acessa. As fontes de letra vêm do Google Fonts, que também recebe o endereço IP de quem abre a página.__MAPA__</li>
</ul>

<h2>Anúncios</h2>
<p>Podemos exibir anúncios do Google AdSense para custear o projeto. Quando houver anúncios, o Google e os seus parceiros podem usar cookies e identificadores do navegador para mostrar anúncios com base nas suas visitas a este e a outros sites. Você pode gerenciar ou desativar a personalização em <a href="https://adssettings.google.com" rel="noopener" target="_blank">adssettings.google.com</a>, saber mais em <a href="https://policies.google.com/technologies/ads?hl=pt-BR" rel="noopener" target="_blank">como o Google usa dados de sites parceiros</a> e bloquear cookies nas configurações do seu navegador. Os anúncios não mudam os números mostrados nem a forma como os dados são organizados.</p>

<h2>Cookies e armazenamento no navegador</h2>
<p>O __NOME__ não define cookies de rastreamento. Para lembrar uma preferência, como o período escolhido nos gráficos, o site usa o armazenamento local do seu navegador. Essa informação fica no seu aparelho e não é enviada a nós. Se houver anúncios, os cookies serão os do Google, descritos acima.</p>

<h2>O que publicamos</h2>
<p>Os números vêm de bases públicas e aparecem de forma agregada (país, estado, município, empresa, campo, aeroporto ou rota, por exemplo). O site não pede nem publica dados pessoais de pessoas físicas.</p>

<h2>Compartilhamento</h2>
<p>Não vendemos nem alugamos dados. Os serviços citados acima (__SERV__) recebem apenas o que é necessário para funcionar.</p>

<h2>Seus direitos</h2>
<p>Pela Lei Geral de Proteção de Dados (Lei nº 13.709/2018), você pode pedir a confirmação de que tratamos dados seus, o acesso, a correção ou a eliminação deles, entre outros direitos. Escreva para <a href="mailto:__EMAIL__">__EMAIL__</a>. Guardamos as mensagens só pelo tempo necessário para responder e as apagamos quando você pedir.</p>

<h2>Mudanças nesta página</h2>
<p>Podemos atualizar este texto. A data da última atualização fica no topo. Dúvidas? Veja a página de <a href="__HREF_CONT__">contato</a>.</p>"""

CONTATO_HTML = """<p class="lede">Encontrou um erro, tem uma sugestão ou quer falar com a gente? Escreva para <a href="mailto:__EMAIL__">__EMAIL__</a> ou use o <a href="__HREF_SUG__">formulário de sugestões e críticas</a>. Lemos todas as mensagens e respondemos quando você deixa um e-mail para retorno.</p>

<h2>Sobre o que você pode escrever</h2>
<ul>
<li><strong>Erro em um dado ou página.</strong> Envie o endereço da página e o número que parece errado. Conferimos na fonte oficial e corrigimos.</li>
<li><strong>Sugestões.</strong> Um dado que faz falta, uma página nova ou uma melhoria no site.</li>
<li><strong>Imprensa e parcerias.</strong> Uso dos dados em reportagens, estudos e projetos. Os dados são públicos, mas gostamos de saber onde são usados.</li>
<li><strong>Privacidade.</strong> Pedidos sobre dados pessoais, conforme a <a href="__HREF_PRIV__">política de privacidade</a>.</li>
</ul>

<h2>Importante</h2>
<p>O __NOME__ é um projeto independente, sem ligação com órgãos do governo nem com as empresas citadas nos dados. __ESPECIFICO__</p>
<p class="small">O __NOME__ faz parte da Família em Números, um grupo de portais que organizam dados públicos do Brasil.</p>"""

_ESPECIFICO = 'Problema com o seu voo, bagagem ou reembolso? Fale com a companhia aérea e, se não resolver, registre a reclamação no <a href="https://www.consumidor.gov.br" rel="noopener" target="_blank">consumidor.gov.br</a> ou na ANAC. Veja também o <a href="/direitos/">guia de direitos do passageiro</a>.'


def _texto_legal(modelo: str) -> str:
    """Troca os marcadores do texto pelo nome do portal, e-mail e endereços das páginas."""
    trocas = {"__NOME__": "Voo em Números", "__EMAIL__": FORM_EMAIL, "__SERV__": "GoatCounter, FormSubmit, GitHub e Google", "__MAPA__": "",
              "__HREF_SUG__": "/sugestoes/", "__HREF_CONT__": "/contato/", "__HREF_PRIV__": "/privacidade/", "__ESPECIFICO__": _ESPECIFICO}
    for k, v in trocas.items():
        modelo = modelo.replace(k, v)
    return modelo


def pg_privacidade(B: Base) -> str:
    corpo = "<section class=\"hero\"><h1>Política de privacidade</h1></section><section class=\"card prose\">" + _texto_legal(PRIVACIDADE_HTML) + "</section>"
    return pagina(B, "/privacidade/", "Privacidade | Voo em Números",
                  "Como o Voo em Números trata dados: o que coleta, anúncios do Google AdSense, cookies e seus direitos pela LGPD.",
                  corpo, "/privacidade/", migalhas=[("", "Privacidade")])


def pg_contato(B: Base) -> str:
    corpo = "<section class=\"hero\"><h1>Contato</h1></section><section class=\"card prose\">" + _texto_legal(CONTATO_HTML) + "</section>"
    return pagina(B, "/contato/", "Contato | Voo em Números",
                  "Fale com o Voo em Números: e-mail, formulário de sugestões, erros em dados, imprensa e parcerias.",
                  corpo, "/contato/", migalhas=[("", "Contato")])


def pg_sobre(B: Base) -> str:
    corpo = f"""<section class="hero"><h1>Como funciona</h1></section>
<section class="card prose">
<p>O Voo em Números organiza os dados públicos de voos da Agência Nacional de Aviação Civil (ANAC) para mostrar, de forma simples, quanto atrasam e quanto são cancelados os voos domésticos no Brasil, por companhia, aeroporto, rota e número de voo.</p>
<h2>De onde vêm os dados</h2>
<p>Da base <strong>Voo Regular Ativo (VRA)</strong>, publicada pela ANAC todo mês, com um registro para cada voo regular previsto: companhia, número do voo, aeroportos, horários previstos e realizados e se o voo foi cancelado. Um robô baixa cada mês novo assim que ele é publicado e atualiza o site sozinho. Os dados atuais vão até {mes_nome(B.ref)}.</p>
<h2>Passageiros e ocupação</h2>
<p>Os números de passageiros, assentos e ocupação vêm de outra base da ANAC, a <strong>Dados Estatísticos do Transporte Aéreo</strong>, informada pelas empresas aéreas. Entram voos domésticos regulares e passageiros pagos. Ocupação é passageiros-quilômetros pagos divididos por assentos-quilômetros oferecidos. Essa base chega com cerca de dois meses de atraso e é atualizada pelo robô toda semana.</p>
<h2>O que entra</h2>
<ul><li>Voos domésticos regulares de passageiros (linha doméstica, código "N" na base da ANAC).</li>
<li>Ficam de fora voos internacionais, voos só de carga, táxi aéreo e voos sem horário previsto.</li></ul>
<h2>Como medimos</h2>
<ul><li><strong>No horário</strong>: voo que chegou ao destino até 30 minutos depois do horário previsto, ou antes. É o mesmo corte que a ANAC usa para classificar atrasos.</li>
<li><strong>Cancelados</strong>: voos registrados como cancelados, sobre o total de voos previstos.</li>
<li><strong>Atraso médio dos atrasados</strong>: média do atraso na chegada dos voos que chegaram mais de 30 minutos depois do previsto.</li>
<li>Os horários são os registrados pela ANAC, no horário local.</li>
<li>Rankings só incluem quem tem volume suficiente de voos, para evitar conclusões com poucos dados. Os mínimos aparecem em cada tabela.</li></ul>
<h2>Limitações</h2>
<p>A base não informa o motivo do atraso ou do cancelamento, nem diferencia cancelamentos avisados com antecedência dos feitos em cima da hora. Um cancelamento planejado semanas antes, com o passageiro remanejado, conta igual a um cancelamento no dia. Os números descrevem o passado e não garantem o que vai acontecer com um voo específico.</p>
<h2>Quem faz</h2>
<p>O Voo em Números faz parte da Família em Números, um grupo de portais independentes que organizam dados públicos do Brasil. Não tem ligação com a ANAC nem com companhias aéreas. Encontrou um erro ou tem uma sugestão? <a href="/sugestoes/">Use o formulário</a> ou escreva para <a href="mailto:oleoemnumeros@gmail.com">oleoemnumeros@gmail.com</a>.</p>
</section>"""
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": "Pontualidade dos voos domésticos no Brasil",
          "description": "Pontualidade e cancelamentos dos voos domésticos regulares no Brasil, por companhia, aeroporto, rota e voo, a partir da base VRA da ANAC.",
          "url": BASE + "/sobre/", "creator": {"@type": "Organization", "name": "Voo em Números"},
          "isBasedOn": "https://siros.anac.gov.br/siros/registros/diversos/vra/", "inLanguage": "pt-BR",
          "temporalCoverage": f"{B.lista[0]}/{B.ref}", "spatialCoverage": "Brasil"}
    return pagina(B, "/sobre/", "Como funciona | Voo em Números",
                  "De onde vêm os dados do Voo em Números, o que entra e como medimos atrasos e cancelamentos dos voos domésticos.",
                  corpo, "/sobre/", migalhas=[("", "Como funciona")], jsonld=[ld])


# ---------------------------------------------------------------- direitos do passageiro
DIREITOS_REVISAO = "12/11/2026"
FONTES_DIREITOS = [
    ("Agência gov: Anac atualiza regras sobre atrasos e cancelamentos",
     "https://agenciagov.ebc.com.br/noticias/202609/anac-atualiza-regras-sobre-atrasos-e-cancelamentos-e-amplia-deveres-de-informacao-aos-passageiros"),
    ("ANAC, Agência Nacional de Aviação Civil", "https://www.gov.br/anac/pt-br"),
    ("consumidor.gov.br, canal oficial de reclamações", "https://www.consumidor.gov.br/"),
]


def aviso_direitos() -> str:
    return ('<section class="card aviso"><div><h2>Seu voo atrasou ou foi cancelado?</h2>'
            '<p>A companhia precisa oferecer alimentação, hospedagem e opções de reacomodação ou reembolso, conforme o tempo de espera. '
            'Veja o que você pode exigir.</p></div><div class="btns"><a class="btn" href="/direitos/">Ver meus direitos</a></div></section>')


def direitos_card_home() -> str:
    return ('<section class="card dark"><h2>Voo atrasado ou cancelado? Veja seus direitos</h2>'
            '<p>Alimentação a partir de 2 horas, hospedagem a partir de 4, reembolso e reacomodação. As regras da ANAC em vigor desde 26 de outubro de 2026, em linguagem simples.</p>'
            '<div class="btns"><a class="btn" href="/direitos/" style="background:#F2B33D;color:#14161A">Ler o guia</a></div></section>')


def pg_direitos(B: Base) -> str:
    T = B.tot[B.ref]
    mes = mes_nome(B.ref)
    n_a1 = T.b[1] + T.b[2] + T.b[3]
    n_a2 = T.b[2] + T.b[3]
    n_a4 = T.b[3]
    p1, p2, p4 = (n_a1 / T.med if T.med else None), (n_a2 / T.med if T.med else None), (n_a4 / T.med if T.med else None)
    dados = f"""<section class="card"><div class="card-head"><h2>Isso acontece com que frequência?</h2><span class="small">Voos domésticos em {mes}</span></div>
<div class="tiles">{tile("Atraso acima de 1 hora", pc(p1), f"{nf(n_a1)} voos")}{tile("Atraso acima de 2 horas", pc(p2), f"{nf(n_a2)} voos")}{tile("Atraso acima de 4 horas", pc(p4), f"{nf(n_a4)} voos")}{tile("Voos cancelados", pc(T.p_canc), f"{nf(T.canc)} voos")}</div>
<p class="nota">Atraso medido na chegada, com os dados da ANAC. O tempo que você espera no aeroporto pode ser diferente. Os direitos abaixo contam a partir da espera no aeroporto.</p></section>"""
    tabela = """<section class="card"><h2>O que a companhia deve oferecer, hora a hora</h2>
<div class="tw"><table class="direitos"><thead><tr><th scope="col">Situação</th><th scope="col">O que você pode exigir</th></tr></thead><tbody>
<tr><td><b>Assim que o problema é conhecido</b></td><td>Informação clara, por canais digitais e no aeroporto: o que houve, a nova previsão de partida, as alternativas de reacomodação e como pedir assistência. A informação deve mostrar data e hora da última atualização.</td></tr>
<tr><td><b>Mais de 2 horas de espera</b></td><td>Alimentação adequada: crédito para alimentação, refeição ou solução equivalente.</td></tr>
<tr><td><b>Mais de 4 horas de espera</b></td><td>Você escolhe entre ser reacomodado em outro voo, receber o reembolso integral da passagem ou seguir viagem por outro meio de transporte. Se for preciso passar a noite, a companhia paga hospedagem e transporte de ida e volta. Se você mora na cidade, pode ficar só com o transporte.</td></tr>
<tr><td><b>Voo cancelado ou interrompido</b></td><td>As mesmas opções: reacomodação, reembolso integral ou outro meio de transporte. A assistência (alimentação, hospedagem e transporte) segue a mesma escala de tempo de espera.</td></tr>
</tbody></table></div>
<p class="nota">A assistência continua obrigatória mesmo quando o atraso ou o cancelamento vem de mau tempo ou outro caso de força maior. O que muda nesses casos é a discussão sobre indenização, que segue a lei e pode ser decidida na Justiça.</p></section>"""
    blocos = """<div class="grid2">
<section class="card"><h2>Overbooking (embarque negado)</h2>
<p>É a preterição: a companhia vendeu mais passagens do que lugares. Ela deve procurar voluntários antes de negar o embarque a alguém. Quem é impedido de embarcar tem direito a assistência material, às opções de reacomodação, reembolso ou outro transporte e à informação por escrito, se pedir.</p></section>
<section class="card"><h2>Bagagem extraviada</h2>
<p>A companhia tem até 7 dias para localizar e entregar a bagagem em voos domésticos, e até 21 dias em voos internacionais. Registre o problema no balcão da companhia ainda no aeroporto, antes de sair, e guarde o protocolo.</p></section>
<section class="card"><h2>Se você pagou do próprio bolso</h2>
<p>Em situações excepcionais, como limitação de infraestrutura do aeroporto ou falta comprovada de fornecedores locais, a companhia pode não conseguir prestar a assistência diretamente. Nesses casos ela reembolsa alimentação, transporte e hospedagem necessários e razoáveis, em até 7 dias depois de você apresentar os comprovantes. Guarde todas as notas.</p></section>
<section class="card"><h2>E a indenização?</h2>
<p>As regras da ANAC definem assistência, reacomodação e reembolso. A indenização por danos morais ou materiais depende de cada caso e de como a lei e os tratados se aplicam. Quando a companhia não presta a assistência devida, muitos passageiros recorrem ao Juizado Especial Cível. Não dá para prometer resultado.</p></section>
</div>"""
    passos = """<section class="card"><h2>Passo a passo para reclamar</h2>
<ol class="passos">
<li><b>Guarde as provas.</b> Cartão de embarque, e-mails e mensagens da companhia, prints do aplicativo com o horário, notas fiscais e fotos. Anote a hora em que o atraso foi informado.</li>
<li><b>Peça a assistência na hora.</b> Procure o balcão da companhia no aeroporto. Se não resolver, fale com o setor de atendimento da administração do aeroporto.</li>
<li><b>Reclame na companhia</b> pelo SAC e guarde o número do protocolo.</li>
<li><b>Sem solução, registre na ANAC</b> pela plataforma de reclamações da agência e, se quiser, no consumidor.gov.br e no Procon da sua cidade.</li>
<li><b>Procure a Justiça se precisar</b> pedir indenização. Causas de menor valor correm no Juizado Especial Cível, e até 20 salários mínimos não exigem advogado.</li>
</ol></section>"""
    mudou = """<section class="card"><h2>O que mudou em outubro de 2026</h2>
<p>A Resolução 813/2026 da ANAC alterou a Resolução 400/2016 e passou a valer em 26 de outubro de 2026. Em resumo:</p>
<ul>
<li>A companhia deve avisar, antes da compra, que o voo pode mudar por clima e requisitos de segurança.</li>
<li>Em atrasos, cancelamentos e interrupções, a companhia deve informar por canais digitais e manter os dados atualizados.</li>
<li>Foi criado o reembolso de despesas pagas pelo passageiro nas situações excepcionais descritas acima.</li>
<li>Em eventos de grande impacto, a ANAC pode definir regras temporárias para a assistência.</li>
<li>Os prazos de alimentação (2 horas) e hospedagem (4 horas) continuam os mesmos. A regra antiga que falava em comunicação gratuita após 1 hora foi retirada do texto.</li>
</ul></section>"""
    pares = [
        ("Quanto tempo de atraso dá direito a alimentação?",
         "A partir de 2 horas de espera a companhia deve oferecer alimentação adequada, em crédito, refeição ou solução equivalente."),
        ("Quando a companhia deve pagar hotel?",
         "Depois de 4 horas de espera, se for preciso passar a noite, a companhia deve oferecer hospedagem e transporte de ida e volta. Quem mora na cidade pode ficar só com o transporte."),
        ("O que fazer quando o voo atrasa mais de 4 horas?",
         "Você escolhe entre reacomodação em outro voo, reembolso integral da passagem ou execução do serviço por outro meio de transporte."),
        ("Mau tempo muda o direito à assistência?",
         "Não. A assistência material é obrigatória mesmo em caso fortuito ou força maior. A discussão sobre indenização é que depende da lei e do caso."),
        ("Em quanto tempo a bagagem extraviada deve ser entregue?",
         "Em até 7 dias nos voos domésticos e até 21 dias nos internacionais."),
        ("Como reclamar de uma companhia aérea?",
         "Guarde as provas, peça a assistência no balcão, registre a reclamação no SAC da companhia e, sem solução, na plataforma da ANAC ou no consumidor.gov.br."),
    ]
    faq, ld = faq_html(pares)
    fontes = '<section class="card"><h2>Fontes</h2><ul class="fontes">' + "".join(
        f'<li><a href="{u}" rel="noopener nofollow" target="_blank">{esc(t)}</a></li>' for t, u in FONTES_DIREITOS) + \
        f'</ul><p class="nota">Texto revisado em {DIREITOS_REVISAO}, com base na Resolução 400/2016 da ANAC e nas alterações da Resolução 813/2026. ' \
        'É um guia informativo em linguagem simples e não substitui o texto oficial nem a orientação de um advogado. ' \
        'O Voo em Números não tem ligação com a ANAC nem com as companhias aéreas.</p></section>'
    corpo = f"""<section class="hero"><span class="kicker">Guia · regras da ANAC em vigor desde 26/10/2026</span>
<h1>Voo atrasado ou cancelado: quais são seus direitos</h1>
<p class="lead">Quanto você espera no aeroporto define o que a companhia aérea precisa oferecer. Aqui está o resumo do que vale hoje, com o que muda em cada caso e como reclamar.</p>
<div class="btns"><a class="btn" href="/companhias/">Ver quais companhias mais atrasam</a><a class="btn sec" href="/mapa/">Ver o mapa de pontualidade</a></div></section>
{dados}
{tabela}
{blocos}
{passos}
{mudou}
{faq}
{fontes}"""
    return pagina(B, "/direitos/", "Voo atrasado ou cancelado: seus direitos (regras da ANAC 2026) | Voo em Números",
                  "O que a companhia aérea deve oferecer quando o voo atrasa ou é cancelado: alimentação após 2 horas, hospedagem após 4, reembolso e reacomodação. Regras da ANAC em vigor desde 26/10/2026.",
                  corpo, "/direitos/", migalhas=[("", "Direitos do passageiro")], jsonld=[ld])


# ---------------------------------------------------------------- mapa
MAPA_LON0, MAPA_LAT0, MAPA_ESC = -74.2, 5.4, 14.5
MAPA_COS = 0.966
MAPA_W, MAPA_H = 575, 585
FAIXAS_MAPA = [  # (limite inferior, cor, rótulo)
    (0.92, "#1D4E89", "92% ou mais"),
    (0.89, "#6FA8DC", "89% a 92%"),
    (0.86, "#F0A35E", "86% a 89%"),
    (0.0, "#B4380B", "menos de 86%"),
]


def mapa_xy(lon: float, lat: float):
    return (lon - MAPA_LON0) * MAPA_COS * MAPA_ESC, (MAPA_LAT0 - lat) * MAPA_ESC


def cor_pont(p: float) -> str:
    for lim, cor, _ in FAIXAS_MAPA:
        if p >= lim:
            return cor
    return FAIXAS_MAPA[-1][1]


def pontos_mapa(B: Base, aero_pag):
    """Aeroportos com coordenadas e volume suficiente no último mês."""
    res = []
    for o in aero_pag:
        x = B.aero[B.ref].get(o)
        g = B.iata.get(o, {})
        if not x or x.prev < 60 or x.med < 30 or "lat" not in g:
            continue
        res.append((o, x, g["lat"], g["lon"]))
    res.sort(key=lambda t: -t[1].prev)
    return res


def svg_mapa(B: Base, aero_pag, compacto: bool = False) -> str:
    est = json.loads((RAIZ / "data" / "brasil_estados.json").read_text(encoding="utf-8"))
    caminhos = []
    for uf, polys in est.items():
        d = ""
        for ring in polys:
            d += "M" + "L".join(f"{mapa_xy(lon, lat)[0]:.1f},{mapa_xy(lon, lat)[1]:.1f}" for lon, lat in ring) + "Z"
        caminhos.append(f'<path d="{d}"/>')
    pts = pontos_mapa(B, aero_pag)
    pontos, rotulos, usados = [], [], []
    for o, x, lat, lon in pts:
        cx, cy = mapa_xy(lon, lat)
        r = max(3.2, min(13, (x.prev ** 0.5) * 0.19))
        nome = f"{B.cod(o)} · {B.aero_nome(o)}: {pc(x.p_pont)} no horário, {pc(x.p_canc)} cancelados"
        pontos.append(f'<a href="/aeroportos/{B.aero_slug(o)}/"><circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{cor_pont(x.p_pont)}" '
                      f'fill-opacity=".88" stroke="#fff" stroke-width="1"><title>{esc(nome)}</title></circle></a>')
    # rótulos dos maiores aeroportos, sem sobreposição
    for o, x, lat, lon in pts[:40]:
        if len(rotulos) >= (9 if compacto else 14):
            break
        cx, cy = mapa_xy(lon, lat)
        r = max(3.2, min(13, (x.prev ** 0.5) * 0.19))
        caixa = (cx + r + 2, cy - 6, cx + r + 2 + 24, cy + 6)
        if any(not (caixa[2] < u[0] or caixa[0] > u[2] or caixa[3] < u[1] or caixa[1] > u[3]) for u in usados):
            continue
        if caixa[2] > MAPA_W:
            continue
        usados.append(caixa)
        rotulos.append(f'<text x="{caixa[0]:.1f}" y="{cy + 4:.1f}">{esc(B.cod(o))}</text>')
    # pontos de aeroportos sem rótulo já cobertos pelo caixa; bolinhas por cima do desenho
    return (f'<svg class="mapa-svg" viewBox="0 0 {MAPA_W} {MAPA_H}" role="img" aria-label="Mapa do Brasil com os aeroportos coloridos pela pontualidade dos voos em {mes_nome(B.ref)}">'
            f'<g class="estados">{"".join(caminhos)}</g><g>{"".join(pontos)}</g><g class="rot">{"".join(rotulos)}</g></svg>')


def legenda_mapa() -> str:
    return ('<ul class="legenda">' + "".join(
        f'<li><i style="background:{cor}"></i>{rot}</li>' for _, cor, rot in FAIXAS_MAPA) + '</ul>'
        '<p class="nota">Cor = percentual de partidas que chegaram no horário. Tamanho = número de voos. Toque ou clique em um aeroporto para ver os detalhes.</p>')


def mapa_card_home(B: Base, aero_pag) -> str:
    return (f'<section class="card"><div class="card-head"><h2>Mapa da pontualidade</h2><span class="small">Aeroportos de partida em {mes_nome(B.ref)}</span></div>'
            f'<div class="mapa-box">{svg_mapa(B, aero_pag, True)}</div>{legenda_mapa()}'
            '<div class="btns"><a class="btn sec" href="/mapa/">Abrir o mapa completo e o ranking por estado</a></div></section>')


def pg_mapa(B: Base, aero_pag) -> str:
    mes = mes_nome(B.ref)
    pts = pontos_mapa(B, aero_pag)
    grandes = [t for t in pts if t[1].prev >= MIN_AERO_RANK]
    grandes.sort(key=lambda t: -(t[1].p_pont or 0))

    def lista(lst):
        return '<ul class="rank">' + "".join(
            f'<li><span><a href="/aeroportos/{B.aero_slug(o)}/">{esc(B.cod(o))}</a> <span class="small">{esc(B.aero_nome(o))}</span></span>'
            f'<span class="num"><b>{pc(x.p_pont)}</b></span></li>' for o, x, _, _ in lst) + "</ul>"
    # por estado
    por_uf = defaultdict(Acc)
    for o, x in B.aero[B.ref].items():
        uf = B.uf(o)
        if uf and len(uf) == 2:
            por_uf[uf].soma(x)
    ufs = [(uf, a) for uf, a in por_uf.items() if a.prev >= 300 and a.med]
    ufs.sort(key=lambda t: -(t[1].p_pont or 0))
    lin_uf = "".join(f'<tr><td><b>{esc(uf)}</b></td><td style="min-width:200px">{meter(a.p_pont)}</td>'
                     f'<td class="r num">{pc(a.p_canc)}</td><td class="r num">{nf(a.prev)}</td></tr>' for uf, a in ufs)
    melhor, pior = (grandes[0], grandes[-1]) if grandes else (None, None)
    lead = f"Cada bolinha é um aeroporto brasileiro, colorido pela pontualidade das partidas em {mes}."
    if melhor and pior:
        lead += (f" Entre os grandes, <strong>{esc(B.cidade(melhor[0]))}</strong> teve a maior pontualidade ({pc(melhor[1].p_pont)}) "
                 f"e <strong>{esc(B.cidade(pior[0]))}</strong> a menor ({pc(pior[1].p_pont)}).")
    pares = [("Qual aeroporto do Brasil é mais pontual?",
              (f"Em {mes}, entre os aeroportos com mais de {nf(MIN_AERO_RANK)} partidas, {B.nome_cod(melhor[0])} teve a maior pontualidade: {pc(melhor[1].p_pont)} das partidas chegaram ao destino no horário." if melhor else "")),
             ("Qual estado tem os voos mais pontuais?",
              (f"Em {mes}, as partidas de aeroportos de {ufs[0][0]} foram as mais pontuais, com {pc(ufs[0][1].p_pont)} chegando no horário." if ufs else ""))]
    pares = [p for p in pares if p[1]]
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Mapa · {mes}</span><h1>Mapa da pontualidade dos aeroportos do Brasil</h1>
<p class="lead">{lead}</p></section>
<section class="card"><div class="mapa-box grande">{svg_mapa(B, aero_pag)}</div>{legenda_mapa()}</section>
<div class="grid2">
<section class="card"><h2>Grandes aeroportos mais pontuais</h2>{lista(grandes[:8])}<p class="nota">Aeroportos com mais de {nf(MIN_AERO_RANK)} partidas em {mes}.</p></section>
<section class="card"><h2>Grandes aeroportos menos pontuais</h2>{lista(list(reversed(grandes[-8:])))}<p class="nota"><a href="/aeroportos/">Ver todos os aeroportos</a></p></section>
</div>
<section class="card"><div class="card-head"><h2>Pontualidade por estado</h2><span class="small">Partidas do estado em {mes}</span></div>
<div class="tw"><table><thead><tr><th scope="col">Estado</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{lin_uf}</tbody></table></div>
<p class="nota">Estados com pelo menos 300 partidas no mês. O estado é o do aeroporto de partida.</p></section>
{aviso_direitos()}
{faq}"""
    return pagina(B, "/mapa/", f"Mapa da pontualidade dos aeroportos do Brasil: {mes} | Voo em Números",
                  f"Mapa com a pontualidade das partidas em cada aeroporto brasileiro em {mes} e ranking por estado. Dados oficiais da ANAC.",
                  corpo, "/mapa/", migalhas=[("", "Mapa")], jsonld=[ld] if pares else [])


# ---------------------------------------------------------------- demanda: passageiros e ocupação
DEM_ARQ = RAIZ / "data" / "demanda.json"
MIN_PAX_ROTA_RANK = 3000     # passageiros no mês para a rota entrar nos rankings de ocupação
MIN_PAX_AERO_DISP = 5000     # passageiros embarcados no mês para o aeroporto entrar no gráfico


class Dm:
    """Soma de passageiros, assentos-km (ASK), passageiros-km (RPK), decolagens e assentos."""
    __slots__ = ("pax", "ask", "rpk", "dec", "ass")

    def __init__(self):
        self.pax = self.ask = self.rpk = self.dec = self.ass = 0

    def add(self, v):
        self.pax += v[0]; self.ask += v[1]; self.rpk += v[2]; self.dec += v[3]; self.ass += v[4]
        return self

    @property
    def ocup(self):
        return self.rpk / self.ask if self.ask else None


class Demanda:
    def __init__(self, arq: Path):
        d = json.loads(arq.read_text(encoding="utf-8"))
        self.mensal = {m: Dm().add(v) for m, v in d["mensal"].items()}
        self.meses = sorted(d["linhas"])
        self.ref = self.meses[-1]
        self.ant = mes_ant_ano(self.ref)
        self.atualizado = d.get("atualizado_em")
        self.cia, self.aero, self.rota = {}, {}, {}
        for m, lst in d["linhas"].items():
            C, A, R = defaultdict(Dm), defaultdict(Dm), defaultdict(Dm)
            for emp, o, dd, *v in lst:
                C[emp].add(v); A[o].add(v); R[(o, dd)].add(v)
            self.cia[m], self.aero[m], self.rota[m] = C, A, R
        ms = sorted(m for m in self.mensal if m <= self.ref)
        self.u13 = ms[-13:]
        self.todos = ms


def abrevia(v: float) -> str:
    if v >= 1e6:
        return nf(v / 1e6, 1) + " mi"
    if v >= 1e4:
        return nf(v / 1e3, 0) + " mil"
    return nf(v)


def var_pct(a, b) -> str:
    if not a or not b:
        return ""
    v = a / b - 1
    if abs(v) < 0.0005:
        return "igual a um ano antes"
    return f'<span class="{"up" if v > 0 else "down"}">{"▲" if v > 0 else "▼"} {nf(abs(v) * 100, 1)}%</span> contra um ano antes'


def tiles_dem(a: Dm, a0) -> str:
    a0 = a0 if a0 and a0.pax else None
    return '<div class="tiles">' + "".join([
        tile("Passageiros pagos", abrevia(a.pax), var_pct(a.pax, a0.pax if a0 else None)),
        tile("Ocupação dos voos", pc(a.ocup), delta_pp(a.ocup, a0.ocup if a0 else None, True)),
        tile("Assentos oferecidos", abrevia(a.ass), var_pct(a.ass, a0.ass if a0 else None)),
        tile("Decolagens", nf(a.dec), var_pct(a.dec, a0.dec if a0 else None)),
    ]) + "</div>"


def bloco_demanda(D, a, a0, titulo: str, nota: str) -> str:
    if not D or not a or a.pax < 1 or not a.ask:
        return ""
    return (f'<section class="card"><div class="card-head"><h2>{titulo}</h2><span class="small">{mes_nome(D.ref)}</span></div>'
            f'{tiles_dem(a, a0)}<p class="nota">{nota} Ocupação = passageiros-quilômetros pagos ÷ assentos-quilômetros oferecidos. '
            'Fonte: ANAC, Dados Estatísticos do Transporte Aéreo.</p></section>')


def dem_aero(B, o: str) -> str:
    D = B.dem
    if not D:
        return ""
    return bloco_demanda(D, D.aero[D.ref].get(o), D.aero.get(D.ant, {}).get(o), "Passageiros e ocupação",
                         f"Passageiros pagos embarcados em {esc(B.cod(o))}, em voos domésticos regulares.")


def dem_rota(B, o: str, d: str) -> str:
    D = B.dem
    if not D:
        return ""
    return bloco_demanda(D, D.rota[D.ref].get((o, d)), D.rota.get(D.ant, {}).get((o, d)), "Passageiros e ocupação",
                         f"Passageiros pagos no sentido {esc(B.cod(o))} → {esc(B.cod(d))}, somando as companhias.")


def dem_cia(B, c: str) -> str:
    D = B.dem
    if not D:
        return ""
    a = D.cia[D.ref].get(c)
    part = f" Participação: {pc(a.pax / D.mensal[D.ref].pax)} dos passageiros dos voos domésticos regulares do país." if a and D.mensal[D.ref].pax else ""
    return bloco_demanda(D, a, D.cia.get(D.ant, {}).get(c), "Passageiros e ocupação", f"Passageiros pagos em voos domésticos regulares.{part}")


def dem_card_home(B) -> str:
    D = B.dem
    if not D:
        return ""
    T, T0 = D.mensal[D.ref], D.mensal.get(D.ant)
    return (f'<section class="card"><div class="card-head"><h2>Quantos passageiros voam?</h2><span class="small">Voos domésticos regulares em {mes_nome(D.ref)}</span></div>'
            f'{tiles_dem(T, T0)}<div class="btns"><a class="btn sec" href="/demanda/">Ver passageiros, ocupação e se aeroporto lotado atrasa mais</a></div></section>')


def pearson(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs); syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / (sxx * syy) ** 0.5 if sxx and syy else None


def forca(r: float) -> str:
    a = abs(r)
    return "muito fraca" if a < 0.2 else "fraca" if a < 0.4 else "moderada" if a < 0.6 else "forte" if a < 0.8 else "muito forte"


def svg_barras_valor(rotulos, valores, fmt, aria="", altura=190, largura=720, periodos=None) -> str:
    n = len(valores)
    W, H, top, base = largura, altura, 22, altura - 26
    mx = max(valores) if valores else 1
    passo = (W - 20) / n
    bw = min(46, passo * 0.66)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">',
           f'<line x1="10" y1="{base}" x2="{W - 10}" y2="{base}" stroke="#C6D2DC"/>']
    for i, (r, v) in enumerate(zip(rotulos, valores)):
        x = 10 + i * passo + (passo - bw) / 2
        h = max(2, v / mx * (base - top))
        ult = i == n - 1
        out.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{"#2A9DE0" if ult else "#A9D8F5"}"/>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle" font-size="12" fill="#3D424A" font-weight="{700 if ult else 400}">{esc(fmt(v))}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle" font-size="12" fill="#5A6070">{esc(r)}</text>')
    out.append("</svg>")
    cfg = {"t": "b", "p": list(periodos or rotulos), "d": 1, "suf": " mi", "u": "milhões", "vl": 1, "vd": 1,
           "s": [{"n": "Passageiros", "v": [round(v / 1e6, 3) for v in valores], "c": "#2A9DE0"}]}
    return fam_gr(cfg, '<div class="chart">' + "".join(out) + "</div>", aria)


def svg_dispersao(B, pts) -> str:
    """pts: lista de (icao, passageiros, pontualidade). Eixo x em escala logarítmica."""
    import math
    W, H, ml, mr, mt, mb = 640, 400, 52, 16, 16, 44
    xs = [math.log10(p[1]) for p in pts]
    ys = [p[2] for p in pts]
    x0, x1 = math.floor(min(xs) * 2) / 2, math.ceil(max(xs) * 2) / 2
    y0, y1 = math.floor(min(ys) * 20) / 20, math.ceil(max(ys) * 20) / 20

    def px(x): return ml + (x - x0) / (x1 - x0) * (W - ml - mr)
    def py(y): return H - mb - (y - y0) / (y1 - y0) * (H - mt - mb)
    out = [f'<svg class="disp" viewBox="0 0 {W} {H}" role="img" aria-label="Gráfico de dispersão: passageiros embarcados e pontualidade de cada aeroporto em {mes_nome(B.dem.ref)}">']
    y = y0
    while y <= y1 + 1e-9:
        out.append(f'<line x1="{ml}" y1="{py(y):.1f}" x2="{W - mr}" y2="{py(y):.1f}" stroke="#EAEFF3"/>'
                   f'<text x="{ml - 8}" y="{py(y) + 4:.1f}" text-anchor="end" font-size="12" fill="#5A6070">{pc(y, 0)}</text>')
        y += 0.05
    for e, rot in ((3, "1 mil"), (4, "10 mil"), (5, "100 mil"), (6, "1 milhão")):
        if x0 <= e <= x1:
            out.append(f'<line x1="{px(e):.1f}" y1="{mt}" x2="{px(e):.1f}" y2="{H - mb}" stroke="#EAEFF3"/>'
                       f'<text x="{px(e):.1f}" y="{H - mb + 18}" text-anchor="middle" font-size="12" fill="#5A6070">{rot}</text>')
    out.append(f'<text x="{(ml + W - mr) / 2:.0f}" y="{H - 6}" text-anchor="middle" font-size="12" fill="#3D424A">Passageiros embarcados no mês (escala logarítmica)</text>')
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx:
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        a = my - b * mx
        out.append(f'<line x1="{px(x0):.1f}" y1="{py(a + b * x0):.1f}" x2="{px(x1):.1f}" y2="{py(a + b * x1):.1f}" stroke="#2A9DE0" stroke-width="1.5" stroke-dasharray="5 4"/>')
    rotulados = {p[0] for p in sorted(pts, key=lambda t: -t[1])[:8]} | {max(pts, key=lambda t: t[2])[0], min(pts, key=lambda t: t[2])[0]}
    for o, pax, pp in pts:
        cx, cy = px(math.log10(pax)), py(pp)
        nome = f"{B.cod(o)} · {B.aero_nome(o)}: {nf(pax)} passageiros, {pc(pp)} no horário"
        circ = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#2A9DE0" fill-opacity=".72" stroke="#fff" stroke-width="1"><title>{esc(nome)}</title></circle>'
        out.append(f'<a href="/aeroportos/{B.aero_slug(o)}/">{circ}</a>')
        if o in rotulados:
            out.append(f'<text class="rt" x="{cx + 7:.1f}" y="{cy + 4:.1f}" font-size="11" font-weight="600" fill="#14161A">{esc(B.cod(o))}</text>')
    out.append(f'<text x="14" y="{(mt + H - mb) / 2:.0f}" font-size="12" fill="#3D424A" text-anchor="middle" transform="rotate(-90 14 {(mt + H - mb) / 2:.0f})">Chegaram no horário</text>')
    out.append("</svg>")
    return '<div class="mapa-box grande">' + "".join(out) + "</div>"


def pg_demanda(B: Base, aero_pag, rota_pag) -> str:
    D = B.dem
    mes = mes_nome(D.ref)
    T, T0 = D.mensal[D.ref], D.mensal.get(D.ant)
    # evolução
    rot = [mes_curto(m) for m in D.todos]
    graf_pax = svg_barras_valor(rot, [D.mensal[m].pax for m in D.todos], lambda v: nf(v / 1e6, 1), periodos=D.todos,
                                aria="Passageiros pagos, em milhões, mês a mês")
    graf_oc = svg_barras(rot, [D.mensal[m].ocup for m in D.todos], periodos=D.todos, aria="Ocupação dos voos mês a mês")
    # companhias
    cs = sorted(((c, x) for c, x in D.cia[D.ref].items() if x.pax >= 20000), key=lambda t: -t[1].pax)
    lin_c = "".join(f'<tr><td>{B.link_cia(c)}</td><td class="r num">{abrevia(x.pax)}</td><td class="r num">{pc(x.pax / T.pax)}</td>'
                    f'<td style="min-width:180px">{meter(x.ocup)}</td><td class="r num">{abrevia(x.ass)}</td></tr>' for c, x in cs)
    # aeroportos
    ae = sorted(D.aero[D.ref].items(), key=lambda t: -t[1].pax)
    ae = [(o, x) for o, x in ae if x.pax > 0][:15]
    lin_a = "".join(
        f'<tr><td class="wrap">{B.link_aero(o, esc(B.cod(o)))} <span class="small">{esc(B.aero_nome(o))}</span></td>'
        f'<td class="r num">{abrevia(x.pax)}</td><td class="r num">{pc(x.ocup)}</td>'
        f'<td class="r num">{pc(B.aero[B.ref][o].p_pont) if o in B.aero[B.ref] else "–"}</td></tr>' for o, x in ae)
    # rotas
    rs = [(r, x) for r, x in D.rota[D.ref].items() if x.pax >= MIN_PAX_ROTA_RANK and x.ocup]
    top_pax = sorted(rs, key=lambda t: -t[1].pax)[:10]
    cheias = sorted(rs, key=lambda t: -t[1].ocup)[:8]
    vazias = sorted(rs, key=lambda t: t[1].ocup)[:8]

    def lin_r(lst):
        return "".join(f'<tr><td class="wrap">{B.link_rota(o, d, esc(B.cod(o)) + " → " + esc(B.cod(d)))} '
                       f'<span class="small">{esc(B.cidade(o))} → {esc(B.cidade(d))}</span></td>'
                       f'<td class="r num">{abrevia(x.pax)}</td><td class="r num"><b>{pc(x.ocup)}</b></td></tr>' for (o, d), x in lst)
    cab_r = '<thead><tr><th scope="col">Rota</th><th scope="col" class="r">Passageiros</th><th scope="col" class="r">Ocupação</th></tr></thead>'
    # pontualidade x volume: aeroportos
    pts = []
    for o, x in D.aero[D.ref].items():
        a = B.aero[B.ref].get(o)
        if a and a.prev >= 300 and a.med >= 100 and x.pax >= MIN_PAX_AERO_DISP and o in aero_pag:
            pts.append((o, x.pax, a.p_pont))
    import math
    r_aero = pearson([math.log10(p[1]) for p in pts], [p[2] for p in pts]) if len(pts) >= 8 else None
    pts_s = sorted(pts, key=lambda t: -t[1])
    top10 = Acc(); resto = Acc()
    for o, _, _ in pts_s[:10]:
        top10.soma(B.aero[B.ref][o])
    for o, _, _ in pts_s[10:]:
        resto.soma(B.aero[B.ref][o])
    # pontualidade x ocupação: rotas em quartis
    rp = []
    for (o, d), x in D.rota[D.ref].items():
        a = B.rota[B.ref].get((o, d))
        if a and a.prev >= MIN_ROTA_RANK and x.pax >= MIN_PAX_ROTA_RANK and x.ocup:
            rp.append(((o, d), x.ocup, a))
    r_rota = pearson([t[1] for t in rp], [t[2].p_pont for t in rp]) if len(rp) >= 20 else None
    rp.sort(key=lambda t: t[1])
    quartis = []
    if len(rp) >= 20:
        q = len(rp) // 4
        for i, nome in enumerate(("25% das rotas mais vazias", "Segundo quarto", "Terceiro quarto", "25% das rotas mais cheias")):
            grupo = rp[i * q:(i + 1) * q] if i < 3 else rp[3 * q:]
            ac = Acc()
            for _, _, a in grupo:
                ac.soma(a)
            oc = sum(t[1] for t in grupo) / len(grupo)
            quartis.append((nome, oc, ac.p_pont, ac.p_canc))
    lin_q = "".join(f'<tr><td>{n}</td><td class="r num">{pc(oc)}</td><td style="min-width:180px">{meter(pp)}</td><td class="r num">{pc(pcn)}</td></tr>'
                    for n, oc, pp, pcn in quartis)
    # texto interpretativo
    if r_aero is not None:
        sent = "mais passageiros, menor a pontualidade" if r_aero < 0 else "mais passageiros, maior a pontualidade"
        interp_aero = (f"A relação entre passageiros e pontualidade é <strong>{forca(r_aero)}</strong> (coeficiente de correlação {nf(r_aero, 2)}): "
                       f"em geral, {sent}. " if abs(r_aero) >= 0.2 else
                       f"A relação entre passageiros e pontualidade é <strong>muito fraca</strong> (coeficiente de correlação {nf(r_aero, 2)}): o tamanho do aeroporto, sozinho, não explica os atrasos. ")
        interp_aero += (f"Os 10 aeroportos com mais passageiros tiveram {pc(top10.p_pont)} de partidas no horário, contra {pc(resto.p_pont)} nos demais.")
    else:
        interp_aero = ""
    nota_corr = "Correlação mostra associação, não causa: aeroportos grandes também têm mais voos em horários de pico, mais conexões e clima diferente."
    if r_rota is not None:
        sent_r = "mais cheia a rota, menor a pontualidade" if r_rota < 0 else "mais cheia a rota, maior a pontualidade"
        interp_rota = (f"Entre as rotas, a relação entre ocupação e pontualidade é <strong>{forca(r_rota)}</strong> (coeficiente {nf(r_rota, 2)})"
                       + (f": em geral, {sent_r}." if abs(r_rota) >= 0.2 else "."))
    else:
        interp_rota = ""
    # FAQ
    pares = [(f"Quantos passageiros voaram no Brasil em {mes}?",
              f"Em {mes}, as companhias aéreas transportaram {nf(T.pax)} passageiros pagos em voos domésticos regulares, com ocupação de {pc(T.ocup)}."),
             ("Qual a ocupação média dos voos no Brasil?",
              f"Em {mes}, a ocupação (passageiros-quilômetros pagos sobre assentos-quilômetros oferecidos) foi de {pc(T.ocup)} nos voos domésticos regulares."),
             ("Qual aeroporto do Brasil tem mais passageiros?",
              f"Em {mes}, o aeroporto com mais passageiros embarcados em voos domésticos regulares foi {B.nome_cod(ae[0][0])}, com {nf(ae[0][1].pax)}." if ae else "")]
    if interp_aero:
        pares.append(("Aeroporto lotado atrasa mais?",
                      re.sub(r"<[^>]+>", "", interp_aero) + " " + nota_corr))
    pares = [p for p in pares if p[1]]
    faq, ld = faq_html(pares)
    disp = (f'<section class="card"><div class="card-head"><h2>Aeroporto lotado atrasa mais?</h2><span class="small">{len(pts)} aeroportos, {mes}</span></div>'
            f'<p>{interp_aero}</p>{svg_dispersao(B, pts) if len(pts) >= 8 else ""}'
            f'<p class="nota">Cada ponto é um aeroporto com ao menos {nf(MIN_PAX_AERO_DISP)} passageiros embarcados no mês. A linha tracejada é a tendência. {nota_corr}</p></section>') if interp_aero else ""
    quart = (f'<section class="card"><div class="card-head"><h2>Voo cheio atrasa mais?</h2><span class="small">{len(rp)} rotas, {mes}</span></div>'
             f'<p>{interp_rota}</p><div class="tw"><table><thead><tr><th scope="col">Grupo de rotas</th><th scope="col" class="r">Ocupação média</th>'
             f'<th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th></tr></thead><tbody>{lin_q}</tbody></table></div>'
             f'<p class="nota">Rotas com ao menos {nf(MIN_PAX_ROTA_RANK)} passageiros e {MIN_ROTA_RANK} voos no mês, divididas em quatro grupos pela ocupação. {nota_corr}</p></section>') if quartis else ""
    corpo = f"""<section class="hero"><span class="kicker">Demanda · {mes}</span><h1>Passageiros e ocupação dos voos no Brasil</h1>
<p class="lead">Em {mes}, as companhias aéreas transportaram <strong>{nf(T.pax)}</strong> passageiros em voos domésticos regulares, com <strong>{pc(T.ocup)}</strong> dos assentos ocupados.</p></section>
{tiles_dem(T, T0)}
<section class="card"><h2>Passageiros por mês</h2>{graf_pax}<p class="nota">Milhões de passageiros pagos, voos domésticos regulares.</p></section>
<section class="card"><h2>Ocupação por mês</h2>{graf_oc}</section>
<section class="card"><div class="card-head"><h2>Companhias em {mes}</h2><span class="small">Passageiros pagos e ocupação</span></div>
<div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col" class="r">Passageiros</th><th scope="col" class="r">Participação</th><th scope="col">Ocupação</th><th scope="col" class="r">Assentos</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Aeroportos com mais passageiros</h2><span class="small">Embarques em {mes}</span></div>
<div class="tw"><table><thead><tr><th scope="col">Aeroporto</th><th scope="col" class="r">Passageiros</th><th scope="col" class="r">Ocupação</th><th scope="col" class="r">No horário</th></tr></thead><tbody>{lin_a}</tbody></table></div></section>
{disp}
{quart}
<section class="card"><div class="card-head"><h2>Rotas com mais passageiros</h2><span class="small">Em {mes}, nos dois sentidos separados</span></div>
<div class="tw"><table>{cab_r}<tbody>{lin_r(top_pax)}</tbody></table></div></section>
<div class="grid2">
<section class="card"><div class="card-head"><h2>Rotas mais cheias</h2><span class="small">Mínimo de {nf(MIN_PAX_ROTA_RANK)} passageiros</span></div><div class="tw"><table>{cab_r}<tbody>{lin_r(cheias)}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Rotas mais vazias</h2><span class="small">Mínimo de {nf(MIN_PAX_ROTA_RANK)} passageiros</span></div><div class="tw"><table>{cab_r}<tbody>{lin_r(vazias)}</tbody></table></div></section>
</div>
<section class="card"><h2>Como lemos os números</h2><p>Os dados são da base Dados Estatísticos do Transporte Aéreo, da ANAC, informada pelas próprias empresas. Entram só voos domésticos regulares e passageiros pagos (os gratuitos ficam de fora). Ocupação é passageiros-quilômetros pagos (RPK) divididos por assentos-quilômetros oferecidos (ASK), a medida que o setor usa. A base chega com cerca de dois meses de atraso, e cada sentido de uma rota aparece separado.</p></section>
{faq}"""
    return pagina(B, "/demanda/", f"Passageiros e ocupação dos voos no Brasil: {mes} | Voo em Números",
                  f"Em {mes}, {nf(T.pax)} passageiros voaram em voos domésticos regulares, com {pc(T.ocup)} de ocupação. Companhias, aeroportos, rotas e a relação com atrasos.",
                  corpo, "/demanda/", migalhas=[("", "Passageiros e ocupação")], jsonld=[ld])


# ---------------------------------------------------------------- cidades, estados, trajetos, companhia × aeroporto e rankings
UF_NOME = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
           "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
           "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
           "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
           "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}
UF_DE = {"AC": "do Acre", "AL": "de Alagoas", "AP": "do Amapá", "AM": "do Amazonas", "BA": "da Bahia", "CE": "do Ceará", "DF": "do Distrito Federal",
         "ES": "do Espírito Santo", "GO": "de Goiás", "MA": "do Maranhão", "MT": "de Mato Grosso", "MS": "de Mato Grosso do Sul",
         "MG": "de Minas Gerais", "PA": "do Pará", "PB": "da Paraíba", "PR": "do Paraná", "PE": "de Pernambuco", "PI": "do Piauí",
         "RJ": "do Rio de Janeiro", "RN": "do Rio Grande do Norte", "RS": "do Rio Grande do Sul", "RO": "de Rondônia", "RR": "de Roraima",
         "SC": "de Santa Catarina", "SP": "de São Paulo", "SE": "de Sergipe", "TO": "do Tocantins"}


def uf_de(uf: str) -> str:
    return UF_DE.get(uf, "de " + uf)


def uf_em(uf: str) -> str:
    d = uf_de(uf)
    return {"do": "no", "da": "na", "de": "em"}[d.split()[0]] + d[len(d.split()[0]):]


MIN_CID_3M = 60          # partidas + chegadas previstas em 3 meses para a cidade ganhar página
MIN_CIA_AERO_3M = 300    # voos previstos em 3 meses para "companhia em aeroporto"


def cid_slug(B: Base, icao: str) -> str:
    return slug(f"{B.cidade(icao)}-{B.uf(icao)}")


def uf_slug(uf: str) -> str:
    return slug(UF_NOME.get(uf, uf))


def periodo3(B: Base) -> str:
    a, b = B.u3[0], B.u3[-1]
    if a.split("-")[0] == b.split("-")[0]:
        return f"{MESES[int(a.split('-')[1]) - 1]} a {mes_nome(b)}"
    return f"{mes_nome(a)} a {mes_nome(b)}"


def periodo3_curto(B: Base) -> str:
    a, b = B.u3[0], B.u3[-1]
    ma, mb = MES_CURTO[int(a.split("-")[1]) - 1], MES_CURTO[int(b.split("-")[1]) - 1]
    return f"{ma} a {mb}/{b.split('-')[0]}" if a.split("-")[0] == b.split("-")[0] else f"{ma}/{a.split('-')[0]} a {mb}/{b.split('-')[0]}"


def monta_cidades(B: Base, todos_aero):
    """Agrupa aeroportos por cidade e estado; só ganham página as cidades com movimento mínimo."""
    grupos = defaultdict(list)
    for a in sorted(todos_aero):
        if B.uf(a):
            grupos[(B.cidade(a), B.uf(a))].append(a)
    B.cid, B.est = {}, defaultdict(list)
    for (n, u), aeros in grupos.items():
        dep, chg = Acc(), Acc()
        for a in aeros:
            dep.soma(B.soma(B.aero, a, B.u3))
            chg.soma(B.soma(B.chg, a, B.u3))
        if dep.prev + chg.prev >= MIN_CID_3M:
            s = slug(f"{n}-{u}")
            B.cid[s] = {"nome": n, "uf": u, "aeros": aeros, "dep": dep, "chg": chg}
            B.est[u].append(s)
    B.pag_est = {u for u in B.est if u in UF_NOME}
    # pares de cidades: todas as combinações de aeroportos que têm página de rota
    B.pares = defaultdict(list)
    for o, d in B.pag_rotas:
        so, sd = cid_slug(B, o), cid_slug(B, d)
        if so != sd:
            B.pares[(so, sd)].append((o, d))
    B.pag_pares = {k for k, v in B.pares.items() if len(v) >= 2 and k[0] in B.cid and k[1] in B.cid}


def link_cidade(B: Base, s: str, texto=None) -> str:
    c = B.cid.get(s)
    t = esc(texto or (c["nome"] if c else s))
    return f'<a href="/cidades/{s}/">{t}</a>' if c else f"<b>{t}</b>"


def link_trajeto(B: Base, so: str, sd: str, texto: str) -> str:
    if (so, sd) in B.pag_pares:
        return f'<a href="/trajetos/{so}-para-{sd}/">{esc(texto)}</a>'
    combos = B.pares.get((so, sd), [])
    if len(combos) == 1:
        return f'<a href="/rotas/{B.rota_slug(*combos[0])}/">{esc(texto)}</a>'
    if sd in B.cid:
        return f'<a href="/cidades/{sd}/">{esc(texto)}</a>'
    return f"<b>{esc(texto)}</b>"


def links_cidade_aero(B: Base, o: str) -> str:
    s = cid_slug(B, o)
    bt = []
    if s in B.cid:
        bt.append(f'<a class="btn sec" href="/cidades/{s}/">Voos em {esc(B.cidade(o))}: saídas e chegadas</a>')
    if B.uf(o) in B.pag_est:
        bt.append(f'<a class="btn sec" href="/estados/{uf_slug(B.uf(o))}/">Aeroportos {esc(uf_de(B.uf(o)))}</a>')
    return f'<div class="btns">{"".join(bt)}</div>' if bt else ""


def serie_aeros(B: Base, tabela: dict, aeros):
    rot, val = [], []
    for m in B.lista:
        a = Acc()
        for x in aeros:
            if x in tabela[m]:
                a.soma(tabela[m][x])
        rot.append(mes_curto(m))
        val.append(a.p_pont if a.med >= 10 else None)
    return rot, val, list(B.lista)


def sem_pred(B: Base, pred):
    sem = [[0, 0] for _ in range(7)]
    for m in B.u3:
        for k, v in B.meses[m]["rota_semana"].items():
            o, d = k.split("-")
            if pred(o, d):
                for i, (med, pont) in enumerate(v):
                    sem[i][0] += med
                    sem[i][1] += pont
    return [(p / m if m >= 8 else None) for m, p in sem]


def per_pred(B: Base, pred):
    per = [Acc() for _ in PERIODOS]
    for (c, n, o, d), cnt in B.voo_hora.items():
        if not cnt or not pred(o, d):
            continue
        x = B.voo_legs[(c, n)].get((o, d))
        if not x or not x.prev:
            continue
        h = int(cnt.most_common(1)[0][0][:2])
        for i, (_, h0, h1) in enumerate(PERIODOS):
            if h0 <= h < h1:
                per[i].soma(x)
    return per


def html_semana_per(B: Base, sem_val, per, aria: str, rotulo: str):
    """Dois cartões lado a lado: melhor horário e dia da semana. Devolve (html, melhor_dia, pior_dia, melhor_per, pior_per)."""
    validos = [v for v in sem_val if v is not None]
    cores = ["#C2410C" if (v is not None and validos and v == min(validos)) else "#2A9DE0" for v in sem_val]
    sem_html = (svg_barras(DIAS_CURTO, sem_val, destaque_ultimo=False, altura=200, cores=cores, largura=420, aria=aria)
                if len(validos) >= 5 else '<p class="small">Poucos voos para comparar os dias da semana.</p>')
    per_html = "".join(f'<div style="display:flex;flex-direction:column;gap:6px"><div style="display:flex;justify-content:space-between;font-size:14px">'
                       f'<span>{nome}</span><span class="num"><b>{pc(x.p_pont)}</b> <span class="small">({nf(x.med)} voos)</span></span></div>{meter(x.p_pont).split("<b>")[0]}</div></div>'
                       for (nome, _, _), x in zip(PERIODOS, per) if x.med >= 10)
    html_ = (f'<div class="grid2"><section class="card"><h2>Melhor horário para voar</h2>{per_html or "<p class=small>Poucos voos para comparar os horários.</p>"}'
             f'<p class="nota">{rotulo}, pelo horário previsto de saída, últimos 3 meses.</p></section>'
             f'<section class="card"><h2>Por dia da semana</h2>{sem_html}<p class="nota">{rotulo}, últimos 3 meses.</p></section></div>')
    dias = None
    if len(validos) >= 5:
        dias = (DIAS_SEMANA[sem_val.index(max(validos))], DIAS_SEMANA[sem_val.index(min(validos))], max(validos), min(validos))
    pers = [(nome.split(" (")[0].lower(), x) for (nome, _, _), x in zip(PERIODOS, per) if x.med >= 20]
    pm = (max(pers, key=lambda t: t[1].p_pont), min(pers, key=lambda t: t[1].p_pont)) if len(pers) >= 2 else None
    return html_, dias, pm


def dem_soma_aeros(B: Base, aeros, titulo="Passageiros e ocupação", nota=""):
    D = B.dem
    if not D:
        return ""

    def s(m):
        t = Dm()
        for a in aeros:
            x = D.aero.get(m, {}).get(a)
            if x:
                t.pax += x.pax; t.ask += x.ask; t.rpk += x.rpk; t.dec += x.dec; t.ass += x.ass
        return t
    return bloco_demanda(D, s(D.ref), s(D.ant), titulo, nota)


def dem_soma_rotas(B: Base, combos):
    D = B.dem
    if not D:
        return ""

    def s(m):
        t = Dm()
        for k in combos:
            x = D.rota.get(m, {}).get(k)
            if x:
                t.pax += x.pax; t.ask += x.ask; t.rpk += x.rpk; t.dec += x.dec; t.ass += x.ass
        return t
    return bloco_demanda(D, s(D.ref), s(D.ant), "Passageiros e ocupação", "Passageiros pagos somando os aeroportos que ligam as duas cidades, em voos domésticos regulares.")


def agrupa_cidades(B: Base, aeros, lado: str):
    """Soma dos voos por cidade do outro lado: lado='dest' (para onde voam) ou 'orig' (de onde vêm)."""
    S = set(aeros)
    g = defaultdict(Acc)
    for m in B.u3:
        for (o, d), x in B.rota[m].items():
            if lado == "dest" and o in S and d not in S:
                g[cid_slug(B, d)].soma(x)
            elif lado == "orig" and d in S and o not in S:
                g[cid_slug(B, o)].soma(x)
    return sorted(((s, x) for s, x in g.items() if x.prev >= 30), key=lambda t: -t[1].prev)


def pg_cidade(B: Base, s: str, aero_pag, rota_pag, voo_pag) -> str:
    c = B.cid[s]
    nome, uf, aeros = c["nome"], c["uf"], c["aeros"]
    mes = mes_nome(B.ref)
    dep_m, chg_m = Acc(), Acc()
    dep_a, chg_a = Acc(), Acc()
    for a in aeros:
        dep_m.soma(B.soma(B.aero, a, [B.ref])); chg_m.soma(B.soma(B.chg, a, [B.ref]))
        dep_a.soma(B.soma(B.aero, a, [B.ant])); chg_a.soma(B.soma(B.chg, a, [B.ant]))
    dep3, chg3 = c["dep"], c["chg"]
    if dep_m.prev >= 30:
        dep, dep0, base_txt = dep_m, dep_a, mes
    else:
        dep, dep0, base_txt = dep3, None, "últimos 3 meses"
    rot, val, pers = serie_aeros(B, B.aero, aeros)
    rot_c, val_c, _ = serie_aeros(B, B.chg, aeros)
    # saindo x chegando
    lin_sc = "".join(
        f'<tr><td><b>{lado}</b></td><td style="min-width:180px">{meter(x.p_pont)}</td><td class="r num">{pc(x.p_canc)}</td>'
        f'<td class="r num">{pc(x.p_a60)}</td><td class="r num">{nf(x.prev)}</td></tr>'
        for lado, x in (("Voos que saem", dep3), ("Voos que chegam", chg3)) if x.prev)
    # aeroportos da cidade
    aer_html = ""
    if len(aeros) > 1:
        ls = "".join(f'<tr><td>{B.link_aero(a, esc(B.cod(a)))} <span class="small">{esc(B.aero_nome(a))}</span></td>'
                     f'<td class="r num"><b>{pc(B.soma(B.aero, a, B.u3).p_pont)}</b></td><td class="r num">{pc(B.soma(B.aero, a, B.u3).p_canc)}</td>'
                     f'<td class="r num">{nf(B.soma(B.aero, a, B.u3).prev)}</td></tr>'
                     for a in sorted(aeros, key=lambda a: -B.soma(B.aero, a, B.u3).prev))
        aer_html = (f'<section class="card"><div class="card-head"><h2>Os aeroportos de {esc(nome)}</h2><span class="small">Partidas, últimos 3 meses</span></div>'
                    f'<div class="tw"><table><thead><tr><th scope="col">Aeroporto</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{ls}</tbody></table></div></section>')
    # companhias
    cs = defaultdict(Acc)
    best_ap = {}
    for a in aeros:
        for cc in {k[0] for m in B.u3 for k in B.cia_aero[m] if k[1] == a}:
            x = B.soma(B.cia_aero, (cc, a), B.u3)
            if x.prev:
                cs[cc].soma(x)
                if cc not in best_ap or x.prev > best_ap[cc][1]:
                    best_ap[cc] = (a, x.prev)
    cs_l = sorted(((cc, x) for cc, x in cs.items() if x.prev >= 30), key=lambda t: -t[1].prev)

    def lk_cia(cc):
        a = best_ap[cc][0]
        if (cc, a) in B.pag_ca:
            return f'<a href="/companhias/{B.cia_slug(cc)}/{B.aero_slug(a)}/">{esc(B.cia_nome(cc))}</a>'
        return B.link_cia(cc)
    lin_c = "".join(f'<tr><td>{lk_cia(cc)}</td><td style="min-width:180px">{meter(x.p_pont)}</td><td class="r num">{pc(x.p_canc)}</td>'
                    f'<td class="r num">{nf(x.prev)}</td></tr>' for cc, x in cs_l)
    # destinos e origens
    dests, origs = agrupa_cidades(B, aeros, "dest"), agrupa_cidades(B, aeros, "orig")

    def tab_cid(lst, lado):
        out = []
        for sc, x in lst[:15]:
            alvo = B.cid.get(sc)
            if lado == "dest":
                lk = link_trajeto(B, s, sc, alvo["nome"] if alvo else sc)
            else:
                lk = link_trajeto(B, sc, s, alvo["nome"] if alvo else sc)
            uf2 = f' <span class="small">{esc(alvo["uf"])}</span>' if alvo else ""
            out.append(f'<tr><td class="wrap">{lk}{uf2}</td><td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>')
        return "".join(out)
    cab_cid = '<thead><tr><th scope="col">{}</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead>'
    dest_html = (f'<section class="card"><div class="card-head"><h2>Para onde se voa saindo de {esc(nome)}</h2><span class="small">Últimos 3 meses</span></div>'
                 f'<div class="tw"><table>{cab_cid.format("Destino")}<tbody>{tab_cid(dests, "dest")}</tbody></table></div></section>') if dests else ""
    orig_html = (f'<section class="card"><div class="card-head"><h2>De onde vêm os voos que chegam a {esc(nome)}</h2><span class="small">Pontualidade na chegada, últimos 3 meses</span></div>'
                 f'<div class="tw"><table>{cab_cid.format("Origem")}<tbody>{tab_cid(origs, "orig")}</tbody></table></div></section>') if origs else ""
    # dia da semana e horário
    S = set(aeros)
    sem_val = sem_pred(B, lambda o, d: o in S)
    per = per_pred(B, lambda o, d: o in S)
    sp_html, dias, pm = html_semana_per(B, sem_val, per, f"Pontualidade por dia da semana nos voos que saem de {nome}", f"Voos que saem de {esc(nome)}")
    # voos que mais atrasam saindo da cidade
    vs = []
    for k in voo_pag:
        for (o, d), x in B.voo_legs[k].items():
            if o in S and x.med >= 20:
                vs.append((k, x))
    vs.sort(key=lambda t: (t[1].p_pont or 0, -t[1].med))
    vistos, lin_v = set(), []
    for k, x in vs:
        if k in vistos:
            continue
        vistos.add(k)
        lin_v.append(f'<tr><td><a href="/voos/{B.voo_slug(*k)}/">{esc(B.cod_voo(*k))}</a></td><td class="wrap">{esc(voo_pag[k])}</td>'
                     f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{min_txt(x.media_atr)}</td></tr>')
        if len(lin_v) == 10:
            break
    voos_html = (f'<section class="card"><div class="card-head"><h2>Voos que mais atrasam saindo de {esc(nome)}</h2><span class="small">Últimos 3 meses</span></div>'
                 f'<div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Trecho</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio dos atrasados</th></tr></thead><tbody>{"".join(lin_v)}</tbody></table></div></section>') if lin_v else ""
    # outras cidades do estado
    outras = sorted((x for x in B.est[uf] if x != s), key=lambda x: -(B.cid[x]["dep"].prev + B.cid[x]["chg"].prev))[:12]
    est_html = ""
    if outras:
        bt = "".join(f'<a class="btn sec" href="/cidades/{x}/">{esc(B.cid[x]["nome"])}</a>' for x in outras)
        est_html = (f'<section class="card"><h2>Outras cidades {esc(uf_de(uf))}</h2><div class="btns">{bt}</div>'
                    + (f'<p class="nota"><a href="/estados/{uf_slug(uf)}/">Ver o estado inteiro</a></p>' if uf in B.pag_est else "") + "</section>")
    aero_btns = "".join(f'<a class="btn sec" href="/aeroportos/{B.aero_slug(a)}/">Aeroporto {esc(B.cod(a))}</a>' for a in aeros if a in aero_pag)
    # FAQ
    cods = "/".join(B.cod(a) for a in aeros)
    pares = [
        (f"Os voos em {nome} atrasam muito?",
         f"Em {base_txt}, {pc(dep.p_pont)} dos voos que saíram de {nome} chegaram ao destino no horário (até 30 minutos de atraso) e {pc(dep.p_canc)} foram cancelados."
         + (f" Nos voos que chegaram a {nome} nos últimos 3 meses, {pc(chg3.p_pont)} estavam no horário." if chg3.med >= 30 else "")),
        (f"Quantos voos saem de {nome}?",
         f"Em {mes}, estavam previstas {nf(dep_m.prev)} partidas de voos domésticos regulares em {nome} ({cods}), com {nf(dep_m.canc)} cancelamentos."),
    ]
    if dests:
        top = dests[0]
        pares.append((f"Para onde se voa saindo de {nome}?",
                      f"O destino mais frequente é {B.cid[top[0]]['nome'] if top[0] in B.cid else top[0]}, com {nf(top[1].prev)} voos nos últimos 3 meses. "
                      + ("Os próximos são " + ", ".join(B.cid[t[0]]["nome"] for t in dests[1:4] if t[0] in B.cid) + "." if len(dests) > 1 else "")))
    if len(cs_l) > 1:
        pior = min(cs_l, key=lambda t: t[1].p_pont or 1)
        melhor = max(cs_l, key=lambda t: t[1].p_pont or 0)
        pares.append((f"Qual companhia é mais pontual em {nome}?",
                      f"Nos últimos 3 meses, a {B.cia_nome(melhor[0])} teve {pc(melhor[1].p_pont)} das partidas no horário em {nome}, "
                      f"contra {pc(pior[1].p_pont)} da {B.cia_nome(pior[0])}."))
    if dias:
        pares.append((f"Qual o melhor dia para voar saindo de {nome}?",
                      f"Nos últimos 3 meses, {dias[0]} teve a maior pontualidade ({pc(dias[2])} no horário) e {dias[1]} a menor ({pc(dias[3])})."))
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Cidade · {esc(UF_NOME.get(uf, uf))}</span><h1>Voos em {esc(nome)} ({esc(uf)}): atrasos e cancelamentos</h1>
<p class="lead">Em {base_txt}, <strong>{pc(dep.p_pont)}</strong> dos voos que saíram de {esc(nome)} chegaram no horário e <strong>{pc(dep.p_canc)}</strong> foram cancelados.
{f"Nos que chegaram à cidade, {pc(chg3.p_pont)} estavam no horário (últimos 3 meses)." if chg3.med >= 30 else ""}</p>
<div class="btns">{f'<a class="btn" href="/quando-ir/{s}/">Melhor época para ir a {esc(nome)}</a>' if s in B.quando else ""}{aero_btns}{f'<a class="btn sec" href="/estados/{uf_slug(uf)}/">{esc(UF_NOME[uf])}</a>' if uf in B.pag_est else ""}</div></section>
{tiles_acc(dep, dep0, "Partidas previstas")}
{dem_soma_aeros(B, aeros, nota=f"Passageiros pagos embarcados em {esc(nome)}, em voos domésticos regulares.")}
<section class="card"><div class="card-head"><h2>Saindo e chegando</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Sentido</th><th scope="col">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Mais de 1 hora</th><th scope="col" class="r">Voos previstos</th></tr></thead><tbody>{lin_sc}</tbody></table></div>
<p class="nota">No horário = chegada ao destino até 30 minutos depois do previsto. Nos voos que chegam, vale o horário de chegada em {esc(nome)}.</p></section>
<section class="card"><h2>Mês a mês: voos que saem de {esc(nome)}</h2>{svg_barras(rot, val, periodos=pers, aria=f"Percentual de voos que saem de {nome} no horário mês a mês")}</section>
{aer_html}
<section class="card"><div class="card-head"><h2>Companhias que saem de {esc(nome)}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
{dest_html}
{orig_html}
{sp_html}
{voos_html}
{est_html}
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/cidades/{s}/", f"Voos em {nome} ({uf}): atrasos e cancelamentos | Voo em Números",
                  f"{cap(base_txt)}: {pc(dep.p_pont)} dos voos que saíram de {nome} chegaram no horário e {pc(dep.p_canc)} foram cancelados. Destinos, companhias, melhor dia e horário.",
                  corpo, "/cidades/", migalhas=[("/cidades/", "Cidades"), ("", nome)], jsonld=[ld],
                  continuar=itens_cidade(B, aeros[0]))



# ---------------------------------------------------------------- melhor época para ir
CLIMA_ARQ = RAIZ / "data" / "clima.json"
MES_ABR = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def carrega_clima() -> dict:
    try:
        return json.loads(CLIMA_ARQ.read_text(encoding="utf-8")).get("aeros", {})
    except (OSError, ValueError):
        return {}


def clima_aeros(B: Base, aeros):
    """Clima de uma cidade: estação do Inmet quando existe; senão NASA POWER do aeroporto mais movimentado."""
    C = getattr(B, "clima", {}) or {}
    ordem = sorted(aeros, key=lambda a: -(B.soma(B.chg, a, B.u3).prev))
    for fonte in ("inmet", "nasa"):
        for a in ordem:
            reg = C.get(a, {}).get(fonte)
            if not reg:
                continue
            nasa = C.get(a, {}).get("nasa", {})
            out = {"fonte": fonte, "estacao": reg.get("estacao", "")}
            for v in ("tmax", "tmin", "chuva"):
                serie = list(reg[v])
                # mês sem medição no Inmet: completa com a estimativa da NASA, se houver
                serie = [x if x is not None else (nasa.get(v) or [None] * 12)[i] for i, x in enumerate(serie)]
                if sum(x is None for x in serie) > 2:
                    break
                out[v] = serie
            else:
                out["dias_chuva"] = reg.get("dias_chuva") or [None] * 12
                return out
    return None


def quando_series(B: Base, aeros):
    """Por mês do calendário (0 = janeiro): passagem média (R$, corrigida), passageiros que chegam e % no horário na chegada."""
    S = set(aeros)
    preco, pax, pont = [None] * 12, [None] * 12, [None] * 12
    rot = {}
    T = getattr(B, "tar", None)
    if T:
        meses_t = T.meses[-12:]
        rot["preco"] = (meses_t[0], meses_t[-1])
        tot = T.soma([k for k in T.rotas if k.split("-")[1] in S])
        for m in meses_t:
            if m in tot and tot[m][0] >= 30:
                preco[int(m[5:]) - 1] = tot[m][1] / tot[m][0] * T.fator[m]
    D = getattr(B, "dem", None)
    if D:
        meses_d = D.meses[-12:]
        rot["pax"] = (meses_d[0], meses_d[-1])
        for m in meses_d:
            v = sum(x.pax for (o, d), x in D.rota[m].items() if d in S)
            if v:
                pax[int(m[5:]) - 1] = v
    meses_v = B.lista[-12:]
    rot["pont"] = (meses_v[0], meses_v[-1])
    for m in meses_v:
        a = Acc()
        for x in aeros:
            if x in B.chg[m]:
                a.soma(B.chg[m][x])
        if a.med >= 30:
            pont[int(m[5:]) - 1] = a.p_pont
    return preco, pax, pont, rot


def _idx(vals, f):
    ok = [(v, i) for i, v in enumerate(vals) if v is not None]
    return f(ok)[1] if ok else None


def _top(vals, n, maior=False):
    ok = sorted(((v, i) for i, v in enumerate(vals) if v is not None), reverse=maior)
    return {i for _, i in ok[:n]}


def _lista_meses(idx) -> str:
    nomes = [MESES[i] for i in sorted(idx)]
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def quando_dados(B: Base, s: str):
    c = B.cid[s]
    cl = clima_aeros(B, c["aeros"])
    if not cl:
        return None
    preco, pax, pont, rot = quando_series(B, c["aeros"])
    chuva = cl["chuva"]
    med_ch = sorted(x for x in chuva if x is not None)[len([x for x in chuva if x is not None]) // 2]
    precos_ok = [p for p in preco if p is not None]
    pax_ok = [p for p in pax if p]
    med_x = sorted(pax_ok)[len(pax_ok) // 2] if len(pax_ok) >= 8 else None
    # bons meses: menos chuva e menos movimento (fora da alta temporada) que a mediana do ano da própria cidade.
    # A passagem não entra: a ANAC informa a tarifa pelo mês da COMPRA, não da viagem.
    bons = [i for i in range(12) if chuva[i] is not None and chuva[i] <= med_ch
            and (med_x is None or (pax[i] and pax[i] <= med_x))]
    if not bons:
        bons = sorted(_top(chuva, 3))
    return {"c": c, "cl": cl, "preco": preco, "pax": pax, "pont": pont, "rot": rot, "bons": bons,
            "seco": _idx(chuva, min), "chuvoso": _idx(chuva, max),
            "quente": _idx(cl["tmax"], max), "frio": _idx(cl["tmin"], min),
            "barato": _idx(preco, min) if len(precos_ok) >= 8 else None,
            "caro": _idx(preco, max) if len(precos_ok) >= 8 else None,
            "cheio": _idx(pax, max) if sum(p is not None for p in pax) >= 8 else None,
            "vazio": _idx(pax, min) if sum(p is not None for p in pax) >= 8 else None}


def quando_origens(B: Base, aeros, rota_pag, n=8):
    """De onde mais se voa para a cidade, com passagem média de 12 meses e o mês mais barato de cada origem."""
    T = getattr(B, "tar", None)
    if not T:
        return ""
    S = set(aeros)
    meses_t = T.meses[-12:]
    linhas = []
    for k, ser in T.rotas.items():
        o, d = k.split("-")
        if d not in S or B.cidade(o) == B.cidade(d):
            continue
        q = sum(ser[m][0] for m in meses_t if m in ser)
        if q < 300:
            continue
        sv = sum(ser[m][1] * T.fator[m] for m in meses_t if m in ser)
        mens = [(ser[m][1] / ser[m][0] * T.fator[m], m) for m in meses_t if m in ser and ser[m][0] >= 30]
        mb = min(mens)[1] if len(mens) >= 8 else None
        linhas.append((q, o, d, sv / q, mb))
    linhas.sort(reverse=True)
    if not linhas:
        return ""
    corpo = "".join(
        f'<tr><td class="wrap">{B.link_rota(o, d, esc(B.cidade(o)) + " (" + esc(B.cod(o)) + ")") if (o, d) in rota_pag else esc(B.cidade(o)) + " (" + esc(B.cod(o)) + ")"}</td>'
        f'<td class="r num"><b>{rs(p)}</b></td><td class="r">{MESES[int(mb[5:]) - 1] if mb else "–"}</td></tr>'
        for q, o, d, p, mb in linhas[:n])
    return corpo


def pg_quando(B: Base, s: str, rota_pag) -> str:
    q = quando_dados(B, s)
    c, cl = q["c"], q["cl"]
    nome, uf, aeros = c["nome"], c["uf"], c["aeros"]
    tmax, tmin, chuva = cl["tmax"], cl["tmin"], cl["chuva"]
    preco, pax, pont = q["preco"], q["pax"], q["pont"]
    secos, chuvosos = _top(chuva, 3), _top(chuva, 3, True)
    cheios = _top([p or None for p in pax], 3, True) if q["cheio"] is not None else set()
    lin = []
    for i in range(12):
        ch_cls = "vv-ok" if i in secos else "vv-atr" if i in chuvosos else ""
        t = f'<b>{nf(tmax[i])}°</b> / {nf(tmin[i])}°' if tmax[i] is not None and tmin[i] is not None else "–"
        dc = f'<span class="small" style="display:block">{nf(cl["dias_chuva"][i])} dias</span>' if cl["dias_chuva"][i] is not None else ""
        lin.append(f'<tr{" class=bom" if i in q["bons"] else ""}><td><b>{MES_ABR[i]}</b></td><td class="num">{t}</td>'
                   f'<td class="num {ch_cls}">{nf(chuva[i]) + " mm" if chuva[i] is not None else "–"}'
                   f'{dc}</td>'
                   f'<td class="num{" vv-atr" if i in cheios else ""}">{abrevia(pax[i]) if pax[i] else "–"}</td>'
                   f'<td class="num">{pc(pont[i], 0) if pont[i] is not None else "–"}</td></tr>')
    bons_txt = _lista_meses(q["bons"])
    frases = [f"Pelos números, os meses que juntam menos chuva e menos movimento que a média do ano em {esc(nome)} são <strong>{bons_txt}</strong>."
              if q["cheio"] is not None else f"Os meses com menos chuva em {esc(nome)} são <strong>{_lista_meses(secos)}</strong>."]
    frases.append(f"O mais chuvoso é {MESES[q['chuvoso']]} ({nf(chuva[q['chuvoso']])} mm)"
                  + (f" e o de mais passageiros chegando é {MESES[q['cheio']]}" if q["cheio"] is not None else "") + ".")
    tiles = (tile("Mês mais seco", cap(MESES[q["seco"]]), f"{nf(chuva[q['seco']])} mm de chuva")
             + tile("Mês mais chuvoso", cap(MESES[q["chuvoso"]]), f"{nf(chuva[q['chuvoso']])} mm de chuva")
             + (tile("Mais movimentado", cap(MESES[q["cheio"]]), f"{abrevia(pax[q['cheio']])} passageiros chegando") if q["cheio"] is not None else
                tile("Mês mais quente", cap(MESES[q["quente"]]), f"máxima média de {nf(tmax[q['quente']])}°"))
             + (tile("Mais tranquilo", cap(MESES[q["vazio"]]), f"{abrevia(pax[q['vazio']])} passageiros chegando") if q["vazio"] is not None else
                tile("Mês mais frio", cap(MESES[q["frio"]]), f"mínima média de {nf(tmin[q['frio']])}°")))
    rot = q["rot"]
    if cl["fonte"] == "inmet":
        est = re.sub(r"\(([a-zà-ú])", lambda m: "(" + m.group(1).upper(), titulo_pt(cl["estacao"]))
        fonte_cl = f"Clima: Normais Climatológicas 1991–2020 do Inmet, estação {esc(est)} (médias de 30 anos)."
    else:
        fonte_cl = ("Clima: médias de 2001–2020 do NASA POWER para a região do aeroporto, estimadas por satélite e modelo "
                    "(média das máximas e mínimas diárias). São valores aproximados, que servem para comparar os meses entre si: "
                    "perto do mar e na serra a temperatura pode variar alguns graus e a chuva medida no local costuma ser maior.")
    notas = [fonte_cl]
    if "pax" in rot:
        notas.append(f"Passageiros: chegadas em voos domésticos regulares entre {mes_curto(rot['pax'][0])} e {mes_curto(rot['pax'][1])} (ANAC).")
    notas.append(f"No horário: voos que chegaram a {esc(nome)} até 30 minutos depois do previsto, entre {mes_curto(rot['pont'][0])} e {mes_curto(rot['pont'][1])}. "
                 "Em verde, os 3 meses de menos chuva; em laranja, os 3 de mais chuva e os 3 de mais passageiros (alta temporada). Linhas destacadas: menos chuva e menos movimento que a média do ano.")
    compra_html = ""
    if q["barato"] is not None:
        mx = max(p for p in preco if p is not None)
        barras = "".join(
            f'<div class="qb"><span>{MES_ABR[i]}</span><i style="width:{(preco[i] / mx * 100) if preco[i] else 0:.0f}%" class="{"ok" if i == q["barato"] else "ruim" if i == q["caro"] else ""}"></i>'
            f'<b class="num">{rs(preco[i]) if preco[i] is not None else "–"}</b></div>' for i in range(12))
        compra_html = (f'<section class="card" id="quando-comprar"><div class="card-head"><h2>Quando comprar a passagem para {esc(nome)}</h2><span class="small">Tarifa média pelo mês da compra</span></div>'
                       f'<p>Nos últimos 12 meses, quem comprou passagem para {esc(nome)} em <b>{MESES[q["barato"]]}</b> pagou em média <b>{rs(preco[q["barato"]])}</b>; '
                       f'em {MESES[q["caro"]]}, <b>{rs(preco[q["caro"]])}</b>.</p><div class="qbs">{barras}</div>'
                       f'<p class="nota">A ANAC informa o mês em que a passagem foi vendida, não o da viagem. Bilhetes vendidos para {esc(nome)} entre '
                       f'{mes_curto(rot["preco"][0])} e {mes_curto(rot["preco"][1])}, corrigidos pela inflação.</p></section>')
    orig = quando_origens(B, aeros, rota_pag)
    orig_html = (f'<section class="card"><div class="card-head"><h2>Passagem para {esc(nome)} saindo de cada cidade</h2><span class="small">Média de 12 meses</span></div>'
                 f'<div class="tw"><table class="qo"><thead><tr><th scope="col">Saindo de</th><th scope="col" class="r">Passagem média</th><th scope="col" class="r">Compra mais barata em</th></tr></thead>'
                 f'<tbody>{orig}</tbody></table></div><p class="nota">Rotas diretas com mais bilhetes vendidos. Preço médio corrigido pela inflação; o mês indicado é o da compra com menor tarifa média nos últimos 12 meses.</p></section>') if orig else ""
    pares = [(f"Qual a melhor época para ir a {nome}?",
              re.sub(r"<[^>]+>", "", frases[0]) + f" O mês mais seco é {MESES[q['seco']]}, com {nf(chuva[q['seco']])} mm de chuva em média."),
             (f"Qual o mês que mais chove em {nome}?",
              f"{cap(MESES[q['chuvoso']])}, com {nf(chuva[q['chuvoso']])} mm de chuva em média. O mais seco é {MESES[q['seco']]} ({nf(chuva[q['seco']])} mm)."),
             (f"Qual o mês mais frio em {nome}?",
              f"{cap(MESES[q['frio']])}, com mínima média de {nf(tmin[q['frio']])}°C. O mais quente é {MESES[q['quente']]}, com máxima média de {nf(tmax[q['quente']])}°C.")]
    if q["barato"] is not None:
        pares.insert(1, (f"Quando comprar passagem para {nome} sai mais barato?",
                         f"Nos últimos 12 meses, quem comprou em {MESES[q['barato']]} pagou em média {rs(preco[q['barato']])} e quem comprou em "
                         f"{MESES[q['caro']]}, {rs(preco[q['caro']])}, já corrigido pela inflação. A ANAC informa o mês da compra, não o da viagem."))
    if q["cheio"] is not None:
        pares.append((f"Qual o mês com mais turistas em {nome}?",
                      f"Pelo movimento nos aeroportos, {MESES[q['cheio']]} é o mês com mais passageiros chegando a {nome} "
                      f"({abrevia(pax[q['cheio']])}) e {MESES[q['vazio']]} o mais tranquilo ({abrevia(pax[q['vazio']])})."))
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Quando ir · {esc(UF_NOME.get(uf, uf))}</span><h1>Melhor época para ir a {esc(nome)} ({esc(uf)})</h1>
<p class="lead">{" ".join(frases)}</p>
<div class="btns"><a class="btn sec" href="/cidades/{s}/">Voos em {esc(nome)}: atrasos e cancelamentos</a><a class="btn sec" href="/quando-ir/">Outros destinos</a></div></section>
<div class="tiles">{tiles}</div>
{linha_destino(B, aeros[0], quando=False)}
<section class="card" id="mes-a-mes"><div class="card-head"><h2>{esc(nome)} mês a mês</h2><span class="small">Clima e movimento</span></div>
<div class="tw"><table class="qi"><thead><tr><th scope="col">Mês</th><th scope="col">Máx / mín</th><th scope="col">Chuva</th><th scope="col">Chegadas</th><th scope="col">No horário</th></tr></thead><tbody>{"".join(lin)}</tbody></table></div>
<p class="nota">{" ".join(notas)}</p></section>
{compra_html}
{orig_html}
{faq}"""
    desc = (f"{cap(MESES[q['seco']])} é o mês mais seco em {nome} ({nf(chuva[q['seco']])} mm) e {MESES[q['chuvoso']]} o mais chuvoso."
            + (f" Alta temporada em {MESES[q['cheio']]}." if q["cheio"] is not None else "")
            + " Veja temperatura, chuva, movimento mês a mês e quando a passagem sai mais barata.")
    return pagina(B, f"/quando-ir/{s}/", f"Melhor época para ir a {nome}: clima, chuva e preço da passagem mês a mês",
                  desc, corpo, "/quando-ir/", migalhas=[("/quando-ir/", "Quando ir"), ("", nome)], jsonld=[ld],
                  continuar=itens_cidade(B, aeros[0]))


def pg_quando_idx(B: Base) -> str:
    itens = sorted(B.quando, key=lambda s: -(B.cid[s]["chg"].prev))
    lin = []
    for s in itens:
        q = B.quando_dados[s]
        c = q["c"]
        lin.append(f'<tr><td class="wrap"><a href="/quando-ir/{s}/">{esc(c["nome"])}</a> <span class="small">{esc(c["uf"])}</span></td>'
                   f'<td>{MES_ABR[q["seco"]]}</td><td>{MES_ABR[q["vazio"]] if q["vazio"] is not None else "–"}</td>'
                   f'<td class="wrap small">{", ".join(MES_ABR[i] for i in q["bons"])}</td></tr>')
    corpo = f"""<section class="hero"><span class="kicker">Quando ir</span><h1>Melhor época para viajar: clima e preço da passagem por destino</h1>
<p class="lead">Para cada cidade com aeroporto: chuva e temperatura de cada mês, o movimento de passageiros e quando a passagem sai mais barata, com dados do Inmet e da ANAC. Escolha o destino para ver mês a mês.</p></section>
<section class="card"><div class="card-head"><h2>{nf(len(itens))} destinos</h2><span class="small">Do mais ao menos movimentado</span></div>
<div class="tw"><table class="qo"><thead><tr><th scope="col">Destino</th><th scope="col">Menos chuva</th><th scope="col">Menos movimento</th><th scope="col">Melhores meses</th></tr></thead><tbody>{"".join(lin)}</tbody></table></div>
<p class="nota">Melhores meses = chuva e movimento de passageiros abaixo da metade do ano da própria cidade. Clima: Inmet (normais 1991–2020) ou NASA POWER onde não há estação; movimento: passageiros que chegaram em voos domésticos nos últimos 12 meses (ANAC).</p></section>"""
    return pagina(B, "/quando-ir/", "Melhor época para viajar: clima, chuva e preço da passagem por destino no Brasil",
                  f"Quando ir a {nf(len(itens))} destinos do Brasil: mês mais seco, passagem mais barata e movimento de passageiros mês a mês, com dados do Inmet e da ANAC.",
                  corpo, "/quando-ir/", migalhas=[("", "Quando ir")])


def pg_cidades(B: Base) -> str:
    por_uf = defaultdict(list)
    for s, c in B.cid.items():
        por_uf[c["uf"]].append(s)
    blocos = []
    for uf in sorted(por_uf, key=lambda u: UF_NOME.get(u, u)):
        itens = sorted(por_uf[uf], key=lambda s: -B.cid[s]["dep"].prev)
        lis = "".join(f'<li><span><a href="/cidades/{s}/">{esc(B.cid[s]["nome"])}</a></span><span class="num small">{pc(B.cid[s]["dep"].p_pont)}</span></li>' for s in itens)
        titulo = f'<a href="/estados/{uf_slug(uf)}/">{esc(UF_NOME.get(uf, uf))}</a>' if uf in B.pag_est else esc(UF_NOME.get(uf, uf))
        blocos.append(f'<div><h3>{titulo}</h3><ul class="rank">{lis}</ul></div>')
    corpo = f"""<section class="hero"><h1>Voos por cidade e estado</h1>
<p class="lead">Atrasos e cancelamentos em {nf(len(B.cid))} cidades com voos regulares, de {len(por_uf)} estados. O percentual ao lado de cada cidade mostra os voos que saíram dela e chegaram no horário nos últimos 3 meses.</p>
<div class="busca" role="search"><label for="busca" class="sr">Buscar cidade</label><input id="busca" type="search" autocomplete="off" placeholder="Ex.: Salvador, Recife, Foz do Iguaçu"><div id="busca-res" aria-live="polite"></div></div></section>
<section class="card"><div class="cols">{"".join(blocos)}</div></section>"""
    return pagina(B, "/cidades/", "Voos por cidade: atrasos e cancelamentos | Voo em Números",
                  f"Pontualidade e cancelamentos dos voos em {nf(len(B.cid))} cidades do Brasil, por estado, com dados oficiais da ANAC.",
                  corpo, "/cidades/", migalhas=[("", "Cidades")])


def pg_estado(B: Base, uf: str, rota_pag) -> str:
    nome = UF_NOME[uf]
    cidades = B.est[uf]
    aeros = [a for s in cidades for a in B.cid[s]["aeros"]]
    S = set(aeros)
    mes = mes_nome(B.ref)
    dep_m, dep_a, dep3, chg3 = Acc(), Acc(), Acc(), Acc()
    for a in aeros:
        dep_m.soma(B.soma(B.aero, a, [B.ref])); dep_a.soma(B.soma(B.aero, a, [B.ant]))
        dep3.soma(B.soma(B.aero, a, B.u3)); chg3.soma(B.soma(B.chg, a, B.u3))
    if dep_m.prev >= 30:
        dep, dep0, base_txt = dep_m, dep_a, mes
    else:
        dep, dep0, base_txt = dep3, None, "últimos 3 meses"
    rot, val, pers = serie_aeros(B, B.aero, aeros)
    # posição entre os estados
    ranking = []
    for u in B.pag_est:
        x = Acc()
        for s in B.est[u]:
            x.soma(B.cid[s]["dep"])
        if x.prev >= 300:
            ranking.append((u, x.p_pont))
    ranking.sort(key=lambda t: -(t[1] or 0))
    pos = next((i + 1 for i, (u, _) in enumerate(ranking) if u == uf), None)
    # cidades do estado
    lin = "".join(f'<tr><td class="wrap"><a href="/cidades/{s}/">{esc(B.cid[s]["nome"])}</a> <span class="small">{esc("/".join(B.cod(a) for a in B.cid[s]["aeros"]))}</span></td>'
                  f'<td style="min-width:170px">{meter(B.cid[s]["dep"].p_pont)}</td><td class="r num">{pc(B.cid[s]["dep"].p_canc)}</td><td class="r num">{nf(B.cid[s]["dep"].prev)}</td></tr>'
                  for s in sorted(cidades, key=lambda s: -B.cid[s]["dep"].prev))
    # rotas mais movimentadas saindo do estado
    rs = sorted(((r, B.soma(B.rota, r, B.u3)) for r in rota_pag if r[0] in S), key=lambda t: -t[1].prev)[:12]
    lin_r = "".join(f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(o, d)}/">{esc(B.cod(o))} → {esc(B.cod(d))}</a> <span class="small">{esc(B.cidade(o))} → {esc(B.cidade(d))}</span></td>'
                    f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>' for (o, d), x in rs)
    # companhias
    cs = defaultdict(Acc)
    for a in aeros:
        for cc in {k[0] for m in B.u3 for k in B.cia_aero[m] if k[1] == a}:
            cs[cc].soma(B.soma(B.cia_aero, (cc, a), B.u3))
    cs_l = sorted(((cc, x) for cc, x in cs.items() if x.prev >= 100), key=lambda t: -t[1].prev)
    lin_c = "".join(f'<tr><td>{B.link_cia(cc)}</td><td style="min-width:170px">{meter(x.p_pont)}</td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>' for cc, x in cs_l)
    mais_p = max((s for s in cidades if B.cid[s]["dep"].prev >= 150), key=lambda s: B.cid[s]["dep"].p_pont or 0, default=None)
    menos_p = min((s for s in cidades if B.cid[s]["dep"].prev >= 150), key=lambda s: B.cid[s]["dep"].p_pont or 1, default=None)
    pares = [(f"Os voos {uf_em(uf)} atrasam muito?",
              f"Em {base_txt}, {pc(dep.p_pont)} dos voos que saíram de aeroportos {uf_de(uf)} chegaram no horário (até 30 minutos de atraso) e {pc(dep.p_canc)} foram cancelados.")]
    if pos and len(ranking) > 4:
        pares.append((f"{nome} está acima ou abaixo da média do Brasil?",
                      f"Nos últimos 3 meses, {nome} ficou na {pos}ª posição entre {len(ranking)} estados com voos regulares em pontualidade das partidas "
                      f"({pc(dep3.p_pont)} no horário, contra {pc(B.soma_tot(B.u3).p_pont)} no país)."))
    if mais_p and menos_p and mais_p != menos_p:
        pares.append((f"Qual a cidade mais pontual {uf_em(uf)}?",
                      f"Entre as cidades com mais de 150 partidas em 3 meses, {B.cid[mais_p]['nome']} teve a maior pontualidade ({pc(B.cid[mais_p]['dep'].p_pont)}) "
                      f"e {B.cid[menos_p]['nome']} a menor ({pc(B.cid[menos_p]['dep'].p_pont)})."))
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Estado · {esc(uf)}</span><h1>Atrasos e cancelamentos de voos {esc(uf_em(uf))}</h1>
<p class="lead">Em {base_txt}, <strong>{pc(dep.p_pont)}</strong> dos voos que saíram de aeroportos {esc(uf_de(uf))} chegaram no horário e <strong>{pc(dep.p_canc)}</strong> foram cancelados.
{f"O estado ocupa a <strong>{pos}ª posição</strong> entre {len(ranking)} em pontualidade (últimos 3 meses)." if pos and len(ranking) > 4 else ""}</p></section>
{tiles_acc(dep, dep0, "Partidas previstas")}
{dem_soma_aeros(B, aeros, nota=f"Passageiros pagos embarcados em aeroportos {esc(uf_de(uf))}.")}
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, periodos=pers, aria=f"Percentual de voos que saem {uf_de(uf)} no horário mês a mês")}</section>
<section class="card"><div class="card-head"><h2>Cidades {esc(uf_de(uf))} com voos</h2><span class="small">Partidas, últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Cidade</th><th scope="col">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{lin}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Companhias {esc(uf_em(uf))}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Rotas mais movimentadas saindo {esc(uf_de(uf))}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Rota</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_r}</tbody></table></div></section>
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/estados/{uf_slug(uf)}/", f"Atrasos de voos {uf_em(uf)}: aeroportos e cidades | Voo em Números",
                  f"{cap(base_txt)}: {pc(dep.p_pont)} dos voos que saíram de aeroportos {uf_de(uf)} chegaram no horário e {pc(dep.p_canc)} foram cancelados. Cidades, companhias e rotas.",
                  corpo, "/cidades/", migalhas=[("/cidades/", "Cidades"), ("", nome)], jsonld=[ld],
                  continuar=itens_cidade(B, B.cid[max(cidades, key=lambda x: B.cid[x]["dep"].prev)]["aeros"][0]))


def pg_trajeto(B: Base, so: str, sd: str, rota_pag) -> str:
    co, cd = B.cid[so], B.cid[sd]
    combos = sorted(B.pares[(so, sd)], key=lambda k: -B.soma(B.rota, k, B.u3).prev)
    mes = mes_nome(B.ref)
    a3, am, am0 = Acc(), Acc(), Acc()
    for k in combos:
        a3.soma(B.soma(B.rota, k, B.u3)); am.soma(B.soma(B.rota, k, [B.ref])); am0.soma(B.soma(B.rota, k, [B.ant]))
    if am.prev >= 30:
        a, a0, base_txt = am, am0, mes
    else:
        a, a0, base_txt = a3, None, "últimos 3 meses"
    rot, val = [], []
    for m in B.lista:
        x = Acc()
        for k in combos:
            if k in B.rota[m]:
                x.soma(B.rota[m][k])
        rot.append(mes_curto(m))
        val.append(x.p_pont if x.med >= 10 else None)
    # comparação entre as combinações de aeroportos
    stats = [(k, B.soma(B.rota, k, B.u3)) for k in combos]
    melhor = max(stats, key=lambda t: t[1].p_pont or 0)
    lin = "".join(f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(*k)}/">{esc(B.cod(k[0]))} → {esc(B.cod(k[1]))}</a> <span class="small">{esc(B.aero_nome(k[0]))} → {esc(B.aero_nome(k[1]))}</span></td>'
                  f'<td style="min-width:170px">{meter(x.p_pont)}</td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{min_txt(x.media_atr)}</td><td class="r num">{nf(x.prev)}</td></tr>'
                  for k, x in stats)
    # companhias
    cs = defaultdict(Acc)
    for (o, d) in combos:
        for cc in {k[0] for m in B.u3 for k in B.cia_rota[m] if k[1] == o and k[2] == d}:
            cs[cc].soma(B.soma(B.cia_rota, (cc, o, d), B.u3))
    cs_l = sorted(((cc, x) for cc, x in cs.items() if x.prev >= 10), key=lambda t: -(t[1].p_pont or 0))
    lin_c = "".join(f'<tr><td>{B.link_cia(cc)}</td><td style="min-width:170px">{meter(x.p_pont)}</td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>' for cc, x in cs_l)
    CK = set(combos)
    sem_val = sem_pred(B, lambda o, d: (o, d) in CK)
    per = per_pred(B, lambda o, d: (o, d) in CK)
    sp_html, dias, pm = html_semana_per(B, sem_val, per, f"Pontualidade por dia da semana nos voos de {co['nome']} para {cd['nome']}", "Voos entre as duas cidades")
    volta = (sd, so) in B.pag_pares or len(B.pares.get((sd, so), [])) >= 1
    volta_html = f'<a class="btn sec" href="{"/trajetos/%s-para-%s/" % (sd, so) if (sd, so) in B.pag_pares else "/rotas/" + B.rota_slug(*B.pares[(sd, so)][0]) + "/"}">Ver a volta: {esc(cd["nome"])} → {esc(co["nome"])}</a>' if volta else ""
    pares = [
        (f"Quanto atrasam os voos de {co['nome']} para {cd['nome']}?",
         f"Em {base_txt}, {pc(a.p_pont)} dos voos entre as duas cidades chegaram no horário (até 30 minutos de atraso) e {pc(a.p_canc)} foram cancelados, somando {len(combos)} combinações de aeroportos."),
        (f"Qual aeroporto é mais pontual para voar de {co['nome']} para {cd['nome']}?",
         f"Nos últimos 3 meses, o trecho {B.cod(melhor[0][0])} → {B.cod(melhor[0][1])} teve a maior pontualidade: {pc(melhor[1].p_pont)} no horário."),
    ]
    if len(cs_l) > 1:
        pares.append((f"Qual companhia é mais pontual entre {co['nome']} e {cd['nome']}?",
                      f"Nos últimos 3 meses, a {B.cia_nome(cs_l[0][0])}, com {pc(cs_l[0][1].p_pont)} dos voos no horário."))
    if pm:
        pares.append((f"Qual o melhor horário para voar de {co['nome']} para {cd['nome']}?",
                      f"Voos com saída na {pm[0][0]}: {pc(pm[0][1].p_pont)} no horário, contra {pc(pm[1][1].p_pont)} na {pm[1][0]}."))
    preco, pares_p, res_p = bloco_preco(B, [f"{k[0]}-{k[1]}" for k in combos], f"{co['nome']} para {cd['nome']}", "t")
    pares = pares_p + pares if pares_p else pares
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Trajeto entre cidades</span><h1>Voos de {esc(co["nome"])} para {esc(cd["nome"])}</h1>
<p class="lead">Somando todos os aeroportos das duas cidades, em {base_txt}, <strong>{pc(a.p_pont)}</strong> dos voos chegaram no horário e <strong>{pc(a.p_canc)}</strong> foram cancelados.</p>
<div class="btns">{volta_html}<a class="btn sec" href="/cidades/{so}/">{esc(co["nome"])}</a><a class="btn sec" href="/cidades/{sd}/">{esc(cd["nome"])}</a></div></section>
{tiles_acc(a, a0)}
{preco}
{dem_soma_rotas(B, combos)}
<section class="card"><div class="card-head"><h2>Qual aeroporto escolher?</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Trecho</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Atraso médio dos atrasados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin}</tbody></table></div>
<p class="nota">Cada linha é uma rota entre um aeroporto de {esc(co["nome"])} e um de {esc(cd["nome"])}. Toque na rota para ver horários, companhias e voos.</p></section>
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, periodos=list(B.lista), aria=f"Percentual de voos de {co['nome']} para {cd['nome']} no horário mês a mês")}</section>
<section class="card"><div class="card-head"><h2>Por companhia</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
{sp_html}
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/trajetos/{so}-para-{sd}/", f"Voos de {co['nome']} para {cd['nome']}: atrasos e {'preço' if res_p else 'cancelamentos'} | Voo em Números",
                  (f"Tarifa média de {rs(res_p['media'])} em {mes_nome(B.tar.ref)}, com curva de preços. " if res_p else "")
                  + f"{cap(base_txt)}: {pc(a.p_pont)} dos voos de {co['nome']} para {cd['nome']} chegaram no horário e {pc(a.p_canc)} foram cancelados. Compare aeroportos, companhias e horários.",
                  corpo, "/cidades/", migalhas=[("/cidades/", "Cidades"), (f"/cidades/{so}/", co["nome"]), ("", f"para {cd['nome']}")], jsonld=[ld],
                  continuar=itens_cidade(B, cd["aeros"][0])[:2] + itens_cidade(B, co["aeros"][0])[:1])


def pg_cia_aero(B: Base, c: str, o: str, rota_pag, voo_pag) -> str:
    nome, cod, cidade = B.cia_nome(c), B.cod(o), B.cidade(o)
    mes = mes_nome(B.ref)
    am, am0, a3 = B.cia_aero[B.ref].get((c, o), Acc()), B.cia_aero.get(B.ant, {}).get((c, o)), B.soma(B.cia_aero, (c, o), B.u3)
    if am.prev >= 30:
        a, a0, base_txt = am, am0, mes
    else:
        a, a0, base_txt = a3, None, "últimos 3 meses"
    rot, val = [], []
    for m in B.lista:
        x = B.cia_aero[m].get((c, o))
        rot.append(mes_curto(m))
        val.append(x.p_pont if x and x.med >= 10 else None)
    aero3 = B.soma(B.aero, o, B.u3)
    cia3 = B.soma(B.cia, c, B.u3)
    # as companhias do aeroporto
    outras = []
    for cc in {k[0] for m in B.u3 for k in B.cia_aero[m] if k[1] == o}:
        x = B.soma(B.cia_aero, (cc, o), B.u3)
        if x.prev >= 60:
            outras.append((cc, x))
    outras.sort(key=lambda t: -(t[1].p_pont or 0))
    pos = next((i + 1 for i, (cc, _) in enumerate(outras) if cc == c), None)

    def lk(cc):
        return (f'<a href="/companhias/{B.cia_slug(cc)}/{B.aero_slug(o)}/">{esc(B.cia_nome(cc))}</a>' if (cc, o) in B.pag_ca and cc != c
                else f"<b>{esc(B.cia_nome(cc))}</b>" if cc == c else B.link_cia(cc))
    lin_o = "".join(f'<tr><td>{lk(cc)}</td><td style="min-width:170px">{meter(x.p_pont)}</td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>' for cc, x in outras)
    # destinos desta companhia saindo daqui
    ds = []
    for (cc, oo, d) in {k for m in B.u3 for k in B.cia_rota[m] if k[0] == c and k[1] == o}:
        x = B.soma(B.cia_rota, (c, o, d), B.u3)
        if x.prev >= 15:
            ds.append((d, x))
    ds.sort(key=lambda t: -t[1].prev)
    lin_d = "".join(f'<tr><td class="wrap">{(f"<a href=/rotas/{B.rota_slug(o, d)}/>" + esc(B.cod(d)) + "</a>") if (o, d) in rota_pag else esc(B.cod(d))} <span class="small">{esc(B.aero_nome(d))}</span></td>'
                    f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>' for d, x in ds[:20])
    # voos
    vs = []
    for k in voo_pag:
        if k[0] == c:
            for (oo, d), x in B.voo_legs[k].items():
                if oo == o and x.med >= 15:
                    vs.append((k, x))
    vs.sort(key=lambda t: (t[1].p_pont or 0, -t[1].med))
    lin_v = "".join(f'<tr><td><a href="/voos/{B.voo_slug(*k)}/">{esc(B.cod_voo(*k))}</a></td><td class="wrap">{esc(voo_pag[k])}</td>'
                    f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{min_txt(x.media_atr)}</td></tr>' for k, x in vs[:10])
    dif = (a3.p_pont - aero3.p_pont) * 100 if a3.p_pont is not None and aero3.p_pont is not None else None
    pares = [
        (f"A {nome} atrasa em {cidade}?",
         f"Em {base_txt}, {pc(a.p_pont)} dos voos da {nome} que saíram de {cod} chegaram no horário (até 30 minutos de atraso) e {pc(a.p_canc)} foram cancelados."),
        (f"A {nome} é mais pontual que a média em {cod}?",
         f"Nos últimos 3 meses, a {nome} teve {pc(a3.p_pont)} das partidas de {cod} no horário, contra {pc(aero3.p_pont)} do aeroporto como um todo"
         + (f" ({nf(abs(dif), 1)} ponto{'s' if abs(dif) >= 1.5 else ''} percentual{'is' if abs(dif) >= 1.5 else ''} {'acima' if dif > 0 else 'abaixo'})." if dif is not None and abs(dif) >= 0.05 else ".")),
    ]
    if ds:
        pares.append((f"Para onde a {nome} voa saindo de {cidade}?",
                      f"Os destinos mais frequentes nos últimos 3 meses: " + ", ".join(f"{B.cidade(d)} ({B.cod(d)})" for d, _ in ds[:4]) + "."))
    if pos and len(outras) > 2:
        pares.append((f"Qual a posição da {nome} em pontualidade em {cod}?",
                      f"Entre {len(outras)} companhias com voos em {cod}, a {nome} ficou na {pos}ª posição nos últimos 3 meses."))
    faq, ld = faq_html(pares)
    btn_cidade = f'<a class="btn sec" href="/cidades/{cid_slug(B, o)}/">Todos os voos em {esc(cidade)}</a>' if cid_slug(B, o) in B.cid else ""
    corpo = f"""<section class="hero"><span class="kicker">Companhia em aeroporto</span><h1>{esc(nome)} em {esc(cidade)} ({esc(cod)}): atrasos e cancelamentos</h1>
<p class="lead">Em {base_txt}, <strong>{pc(a.p_pont)}</strong> dos voos da {esc(nome)} que saíram de {esc(B.nome_cod(o))} chegaram no horário e <strong>{pc(a.p_canc)}</strong> foram cancelados.</p>
<div class="btns"><a class="btn sec" href="/companhias/{B.cia_slug(c)}/">{esc(nome)} no Brasil</a><a class="btn sec" href="/aeroportos/{B.aero_slug(o)}/">Aeroporto {esc(cod)}</a>{btn_cidade}</div></section>
{tiles_acc(a, a0, "Partidas previstas")}
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, periodos=list(B.lista), aria=f"Percentual de voos da {nome} saindo de {cod} no horário mês a mês")}</section>
<section class="card"><div class="card-head"><h2>As companhias de {esc(cod)}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{lin_o}</tbody></table></div>
<p class="nota">Média da {esc(nome)} no país: {pc(cia3.p_pont)} no horário nos últimos 3 meses.</p></section>
<section class="card"><div class="card-head"><h2>Destinos da {esc(nome)} saindo de {esc(cod)}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Destino</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_d}</tbody></table></div></section>
{f'<section class="card"><div class="card-head"><h2>Voos que mais atrasam</h2><span class="small">{esc(nome)} saindo de {esc(cod)}, últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Trecho</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio dos atrasados</th></tr></thead><tbody>{lin_v}</tbody></table></div></section>' if lin_v else ""}
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/companhias/{B.cia_slug(c)}/{B.aero_slug(o)}/", f"{nome} em {cidade} ({cod}): atrasos e cancelamentos | Voo em Números",
                  f"{cap(base_txt)}: {pc(a.p_pont)} dos voos da {nome} que saíram de {cod} chegaram no horário e {pc(a.p_canc)} foram cancelados. Destinos e voos que mais atrasam.",
                  corpo, "/companhias/", migalhas=[("/companhias/", "Companhias"), (f"/companhias/{B.cia_slug(c)}/", nome), ("", f"em {cod}")], jsonld=[ld],
                  continuar=itens_cidade(B, o))


# rankings: (endereço, título, objeto, ordem)
RANKINGS = [
    ("aeroportos-que-mais-atrasam", "Aeroportos que mais atrasam no Brasil", "aero", "pior", "Qual o aeroporto que mais atrasa no Brasil?"),
    ("aeroportos-mais-pontuais", "Aeroportos mais pontuais do Brasil", "aero", "melhor", "Qual o aeroporto mais pontual do Brasil?"),
    ("aeroportos-com-mais-cancelamentos", "Aeroportos com mais cancelamentos de voos", "aero", "canc", "Qual o aeroporto com mais voos cancelados?"),
    ("rotas-que-mais-atrasam", "Rotas aéreas que mais atrasam", "rota", "pior", "Qual a rota aérea que mais atrasa?"),
    ("rotas-mais-pontuais", "Rotas aéreas mais pontuais", "rota", "melhor", "Qual a rota aérea mais pontual?"),
    ("rotas-com-mais-cancelamentos", "Rotas aéreas com mais cancelamentos", "rota", "canc", "Qual a rota aérea com mais voos cancelados?"),
    ("voos-que-mais-atrasam", "Voos que mais atrasam no Brasil", "voo", "pior", "Qual o voo que mais atrasa no Brasil?"),
    ("voos-mais-pontuais", "Voos mais pontuais do Brasil", "voo", "melhor", "Qual o voo mais pontual do Brasil?"),
]


def dados_ranking(B: Base, obj: str, ordem: str, aero_pag, rota_pag, voo_pag, n: int = 30):
    if obj == "aero":
        itens = [(a, B.soma(B.aero, a, B.u3)) for a in aero_pag]
        itens = [(k, x) for k, x in itens if x.prev >= 3 * MIN_AERO_RANK]
    elif obj == "rota":
        itens = [(r, B.soma(B.rota, r, B.u3)) for r in rota_pag]
        itens = [(k, x) for k, x in itens if x.prev >= 3 * MIN_ROTA_RANK]
    else:
        itens = [(k, B.soma(B.voo, k, B.u3)) for k in voo_pag]
        itens = [(k, x) for k, x in itens if x.prev >= 3 * MIN_VOO_RANK]
    if ordem == "pior":
        itens.sort(key=lambda t: (t[1].p_pont or 0, -t[1].med))
    elif ordem == "melhor":
        itens.sort(key=lambda t: (-(t[1].p_pont or 0), -t[1].med))
    else:
        itens.sort(key=lambda t: (-(t[1].p_canc or 0), -t[1].prev))
    return itens[:n], len(itens)


def nome_item(B: Base, obj: str, k, voo_pag) -> str:
    if obj == "aero":
        return f'<a href="/aeroportos/{B.aero_slug(k)}/">{esc(B.cod(k))}</a> <span class="small">{esc(B.aero_nome(k))}</span>'
    if obj == "rota":
        return (f'<a href="/rotas/{B.rota_slug(*k)}/">{esc(B.cod(k[0]))} → {esc(B.cod(k[1]))}</a> '
                f'<span class="small">{esc(B.cidade(k[0]))} → {esc(B.cidade(k[1]))}</span>')
    return f'<a href="/voos/{B.voo_slug(*k)}/">{esc(B.cod_voo(*k))}</a> <span class="small">{esc(voo_pag[k])}</span>'


def texto_item(B: Base, obj: str, k, voo_pag) -> str:
    if obj == "aero":
        return B.nome_cod(k)
    if obj == "rota":
        return f"{B.cidade(k[0])} ({B.cod(k[0])}) → {B.cidade(k[1])} ({B.cod(k[1])})"
    return f"{B.cod_voo(*k)} ({voo_pag[k]})"


def pg_ranking(B: Base, spec, aero_pag, rota_pag, voo_pag) -> str:
    sl, titulo, obj, ordem, pergunta = spec
    itens, total = dados_ranking(B, obj, ordem, aero_pag, rota_pag, voo_pag)
    per = periodo3(B)
    rot_obj = {"aero": "Aeroporto", "rota": "Rota", "voo": "Voo"}[obj]
    plural = {"aero": "aeroportos", "rota": "rotas", "voo": "voos"}[obj]
    unid = {"aero": "partidas", "rota": "voos", "voo": "viagens"}[obj]
    lin = "".join(
        f'<tr><td class="num">{i}</td><td class="wrap">{nome_item(B, obj, k, voo_pag)}</td>'
        f'<td style="min-width:170px">{meter(x.p_pont, ruim=ordem != "melhor")}</td><td class="r num">{pc(x.p_canc)}</td>'
        f'<td class="r num">{pc(x.p_a60)}</td><td class="r num">{nf(x.prev)}</td></tr>' for i, (k, x) in enumerate(itens, 1))
    k1, x1 = itens[0]
    minimo = {"aero": 3 * MIN_AERO_RANK, "rota": 3 * MIN_ROTA_RANK, "voo": 3 * MIN_VOO_RANK}[obj]
    crit = {"pior": "menor percentual de voos no horário", "melhor": "maior percentual de voos no horário", "canc": "maior percentual de voos cancelados"}[ordem]
    ordem_txt = {"pior": "menos pontual", "melhor": "mais pontual", "canc": "com mais cancelamentos"}[ordem]
    destaque = (f"O {ordem_txt} é" if obj != "rota" else f"A rota {ordem_txt} é") if ordem != "canc" else f"O primeiro em cancelamentos é"
    valor = pc(x1.p_canc) + " cancelados" if ordem == "canc" else pc(x1.p_pont) + " no horário"
    pares = [
        (pergunta,
         f"Nos últimos 3 meses ({per}), o primeiro da lista foi {texto_item(B, obj, k1, voo_pag)}, com {valor} entre {nf(x1.prev)} {unid} previstas."),
        ("Como o ranking é calculado?",
         f"Considera voos domésticos regulares de passageiros nos últimos 3 meses de dados da ANAC. Só entram {plural} com pelo menos {nf(minimo)} {unid} previstas no período, "
         f"para evitar distorções de poucos voos. A ordem usa o {crit}. No horário = chegada até 30 minutos depois do previsto."),
        ("Atrasar muito significa que o voo é ruim ou perigoso?",
         "Não. O atraso mede pontualidade, não segurança. Um voo ou aeroporto pode atrasar por tráfego aéreo, clima, conexões de aeronave ou fila de pista, e a base da ANAC não informa o motivo."),
    ]
    faq, ld = faq_html(pares)
    outros = "".join(f'<a class="btn sec" href="/rankings/{s}/">{esc(t)}</a>' for s, t, *_ in RANKINGS if s != sl)
    corpo = f"""<section class="hero"><span class="kicker">Ranking · {per}</span><h1>{esc(titulo)}</h1>
<p class="lead">{destaque} <strong>{esc(texto_item(B, obj, k1, voo_pag))}</strong>, com {valor.replace(" no horário", " dos voos no horário")} entre {nf(x1.prev)} {unid} previstas. {f"Veja os {len(itens)} primeiros de {nf(total)} {plural} analisados." if total > len(itens) else f"Veja os {nf(total)} {plural} analisados."}</p></section>
<section class="card"><div class="card-head"><h2>{esc(titulo)}</h2><span class="small">{per}</span></div>
<div class="tw"><table><thead><tr><th scope="col">#</th><th scope="col">{rot_obj}</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Mais de 1 hora</th><th scope="col" class="r">{unid.capitalize()}</th></tr></thead><tbody>{lin}</tbody></table></div>
<p class="nota">Só entram {plural} com pelo menos {nf(minimo)} {unid} previstas nos últimos 3 meses. Voos domésticos regulares, dados da ANAC.</p></section>
<section class="card"><h2>Outros rankings</h2><div class="btns">{outros}</div></section>
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/rankings/{sl}/", f"{titulo} ({periodo3_curto(B)}) | Voo em Números",
                  f"{titulo} em {per}: {texto_item(B, obj, k1, voo_pag)} lidera com {valor}. Ranking com {len(itens)} {plural}, dados oficiais da ANAC.",
                  corpo, "/rankings/", migalhas=[("/rankings/", "Rankings"), ("", titulo)], jsonld=[ld])


def pg_rankings(B: Base, aero_pag, rota_pag, voo_pag) -> str:
    cards = []
    for spec in RANKINGS:
        sl, titulo, obj, ordem, _ = spec
        itens, total = dados_ranking(B, obj, ordem, aero_pag, rota_pag, voo_pag, 3)
        if not itens:
            continue
        li = "".join(f'<li><span>{nome_item(B, obj, k, voo_pag)}</span><span class="num"><b>{pc(x.p_canc) if ordem == "canc" else pc(x.p_pont)}</b></span></li>' for k, x in itens)
        cards.append(f'<section class="card"><div class="card-head"><h2><a href="/rankings/{sl}/">{esc(titulo)}</a></h2></div><ul class="rank">{li}</ul>'
                     f'<p class="nota"><a href="/rankings/{sl}/">Ver o ranking completo</a></p></section>')
    corpo = f"""<section class="hero"><span class="kicker">Rankings · {periodo3(B)}</span><h1>Rankings de voos no Brasil</h1>
<p class="lead">Quem mais atrasa, quem mais cancela e quem mais cumpre o horário: aeroportos, rotas e números de voo. Atualizado todo mês com os dados oficiais da ANAC.</p></section>
<div class="grid2">{"".join(cards)}</div>"""
    return pagina(B, "/rankings/", "Rankings de voos: quem mais atrasa e cancela | Voo em Números",
                  f"Rankings de {periodo3(B)}: aeroportos, rotas e voos que mais atrasam, mais cancelam e mais cumprem o horário, com dados oficiais da ANAC.",
                  corpo, "/rankings/", migalhas=[("", "Rankings")])


def explora_card_home(B: Base) -> str:
    bt_cid = "".join(f'<a class="btn sec" href="/cidades/{s}/">{esc(B.cid[s]["nome"])}</a>'
                     for s in sorted(B.cid, key=lambda s: -B.cid[s]["dep"].prev)[:8])
    return (f'<div class="grid2"><section class="card"><div class="card-head"><h2>Voos na sua cidade</h2></div><div class="btns">{bt_cid}'
            f'<a class="btn" href="/cidades/">Todas as cidades e estados</a></div></section>'
            f'<section class="card"><div class="card-head"><h2>Rankings do mês</h2></div><div class="btns">'
            f'<a class="btn sec" href="/rankings/aeroportos-que-mais-atrasam/">Aeroportos que mais atrasam</a>'
            f'<a class="btn sec" href="/rankings/rotas-que-mais-atrasam/">Rotas que mais atrasam</a>'
            f'<a class="btn sec" href="/rankings/voos-que-mais-atrasam/">Voos que mais atrasam</a>'
            f'<a class="btn sec" href="/rankings/voos-mais-pontuais/">Voos mais pontuais</a>'
            f'<a class="btn" href="/rankings/">Todos os rankings</a></div></section></div>')


# ---------------------------------------------------------------- preço das passagens (microdados de tarifas da ANAC)
TAR_ARQ = RAIZ / "data" / "tarifas.json"
CIA_TAR = {"TAM": "LATAM", "GLO": "GOL", "AZU": "Azul"}
COR_TAR = {"": "#2A9DE0", "TAM": "#C2410C", "GLO": "#6B7280", "AZU": "#0F766E"}
MIN_ASS_TOTAL = 150      # assentos no mês para a rota ganhar bloco de preço
MIN_ASS_CIA = 80         # assentos no mês para a companhia ganhar curva própria


class Tarifas:
    def __init__(self, arq: Path):
        d = json.loads(arq.read_text(encoding="utf-8"))
        self.ref, self.atualizado, self.edges = d["ref"], d["atualizado_em"], d["edges"]
        self.nac, self.nac_h, self.rotas, self.cias, self.h = d["nac"], d["nac_h"], d["rotas"], d["cias"], d["h"]
        self.meses = sorted(self.nac)
        ipca = d.get("ipca", {})
        self.real = all(m in ipca for m in self.meses[1:])
        self.fator, f = {}, 1.0
        for m in reversed(self.meses):
            self.fator[m] = f if self.real else 1.0
            f *= 1 + ipca.get(m, 0) / 100

    def soma(self, keys, cia: str = ""):
        tot = {}
        for k in keys:
            src = self.rotas.get(k, {}) if not cia else self.cias.get(k, {}).get(cia, {})
            for m, (q, s) in src.items():
                t = tot.setdefault(m, [0, 0])
                t[0] += q
                t[1] += s
        return tot

    def serie(self, keys, cia: str = "", minq: int = 30):
        tot = self.soma(keys, cia)
        return [(tot[m][1] / tot[m][0] * self.fator[m]) if m in tot and tot[m][0] >= minq else None for m in self.meses]

    def hist(self, keys, cia: str = ""):
        out = None
        for k in keys:
            h = self.h.get(k, {}).get(cia)
            if h:
                out = h[:] if out is None else [a + b for a, b in zip(out, h)]
        return out


def _lim(edges, i):
    return edges[i + 1] if i + 1 < len(edges) else edges[i] * 1.5


def hist_pct(counts, edges, p: float) -> float:
    tot = sum(counts)
    alvo, acc = p * tot, 0
    for i, c in enumerate(counts):
        if c and acc + c >= alvo:
            lo, hi = edges[i], _lim(edges, i)
            return lo + (alvo - acc) / c * (hi - lo)
        acc += c
    return edges[-1]


def hist_cdf(counts, edges, x: float) -> float:
    tot, acc = sum(counts), 0.0
    for i, c in enumerate(counts):
        lo, hi = edges[i], _lim(edges, i)
        if x >= hi:
            acc += c
        elif x > lo:
            acc += c * (x - lo) / (hi - lo)
            break
        else:
            break
    return acc / tot if tot else 0.0


def rs(v, d: int = 0) -> str:
    return "R$ " + nf(v, d)


def nice_step(span: float) -> int:
    for s in (50, 100, 250, 500, 1000, 2000):
        if span / s <= 7:
            return s
    return 2000


def svg_linha_preco(rot, val, aria: str) -> str:
    """Reserva estática do gráfico de 13 meses (a linha interativa a substitui quando há JavaScript)."""
    W, H, ml, mr, mt, mb = 720, 200, 20, 20, 26, 28
    pts = [(i, v) for i, v in enumerate(val) if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    lo, hi = lo - (hi - lo) * 0.25 - 1, hi + (hi - lo) * 0.25 + 1
    n = len(val)
    X = lambda i: ml + i * (W - ml - mr) / max(n - 1, 1)
    Y = lambda v: mt + (hi - v) / (hi - lo) * (H - mt - mb)
    poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pts)
    mx, mn = max(pts, key=lambda t: t[1]), min(pts, key=lambda t: t[1])
    txt = []
    for i, v in {pts[0][0]: pts[0][1], pts[-1][0]: pts[-1][1], mx[0]: mx[1], mn[0]: mn[1]}.items():
        txt.append(f'<text x="{X(i):.1f}" y="{Y(v) - 8:.1f}" text-anchor="middle" font-size="12" fill="#3D424A" font-weight="700">{esc(rs(v))}</text>')
    pontos = "".join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3" fill="#2A9DE0"/>' for i, v in pts)
    eixo = "".join(f'<text x="{X(i):.1f}" y="{H - 8}" text-anchor="middle" font-size="11" fill="#5A6070">{esc(rot[i])}</text>' for i in range(0, n, 2))
    return (f'<div class="chart"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">'
            f'<line x1="{ml}" y1="{H - mb}" x2="{W - mr}" y2="{H - mb}" stroke="#C6D2DC"/>'
            f'<polyline points="{poly}" fill="none" stroke="#2A9DE0" stroke-width="2.5" stroke-linejoin="round"/>{pontos}{"".join(txt)}{eixo}</svg></div>')


def grafico_preco_13m(T: Tarifas, keys, aria: str):
    """Linha do preço médio dos últimos 13 meses: total e, quando há dados, LATAM, GOL e Azul."""
    rot = [mes_curto(m) for m in T.meses]
    todas = T.serie(keys, "", 60)
    if sum(v is not None for v in todas) < 4:
        return "", todas
    series = [{"n": "Todas as companhias", "v": [round(v) if v is not None else None for v in todas], "c": COR_TAR[""]}]
    for cia in CIA_TAR:
        s = T.serie(keys, cia, MIN_ASS_CIA)
        if sum(v is not None for v in s) >= 6:
            series.append({"n": CIA_TAR[cia], "v": [round(v) if v is not None else None for v in s], "c": COR_TAR[cia], "d": 1})
    cfg = {"t": "l", "p": list(T.meses), "l": rot, "s": series, "d": 0, "pre": "R$ ", "w": 0, "z": 0, "lg": 1 if len(series) > 1 else 0}
    return fam_gr(cfg, svg_linha_preco(rot, todas, aria), aria), todas


def svg_curva(counts, edges, uid: str, aria: str):
    """Curva de preços (densidade suavizada) com três faixas: 25% mais baratos, metade do meio e 25% mais caros."""
    W, H, ml, mr, mt, mb = 440, 240, 10, 10, 22, 32
    q = {p: hist_pct(counts, edges, p) for p in (0.01, 0.10, 0.25, 0.5, 0.75, 0.90, 0.98)}
    xlo = max(0, 50 * int(q[0.01] / 50))
    xhi = 50 * (int(q[0.98] / 50) + 1)
    if xhi - xlo < 200:
        xhi = xlo + 200
    px = lambda x: ml + (min(max(x, xlo), xhi) - xlo) / (xhi - xlo) * (W - ml - mr)
    base = H - mb
    h = (xhi - xlo) / 22
    N = 72
    xs = [xlo + (xhi - xlo) * i / (N - 1) for i in range(N)]
    dens = [(hist_cdf(counts, edges, x + h) - hist_cdf(counts, edges, x - h)) / (2 * h) for x in xs]
    mx = max(dens) or 1
    py = lambda dv: base - dv / mx * (base - mt - 14)
    ponto = " ".join(f"{px(x):.1f},{py(dv):.1f}" for x, dv in zip(xs, dens))
    area = f"M{px(xlo):.1f},{base} L{ponto.replace(' ', ' L')} L{px(xhi):.1f},{base} Z"
    cortes = [(0, q[0.25], "#2A9DE0", "Barato"), (q[0.25], q[0.75], "#A9D8F5", "Normal"), (q[0.75], xhi, "#E8833A", "Caro")]
    defs, zonas, rotulos = [], [], []
    for i, (a, b, cor, nome) in enumerate(cortes):
        xa, xb = (ml if i == 0 else px(a)), (W - mr if i == 2 else px(b))
        defs.append(f'<clipPath id="z{uid}{i}"><rect x="{xa:.1f}" y="0" width="{max(xb - xa, 0):.1f}" height="{H}"/></clipPath>')
        zonas.append(f'<path d="{area}" fill="{cor}" clip-path="url(#z{uid}{i})"/>')
        if xb - xa > 44:
            rotulos.append(f'<text x="{(xa + xb) / 2:.1f}" y="{mt + 8}" text-anchor="middle" font-size="14" font-weight="700" fill="#2B3038">{nome}</text>')
    marcas = []
    for p in (0.25, 0.5, 0.75):
        x = px(q[p])
        marcas.append(f'<line x1="{x:.1f}" y1="{mt + 16}" x2="{x:.1f}" y2="{base}" stroke="#3D424A" stroke-width="1" stroke-dasharray="3 3"/>'
                      f'<text x="{min(max(x, 28), W - 28):.1f}" y="{base + 18}" text-anchor="middle" font-size="13" font-weight="700" fill="#2B3038">{esc(nf(q[p]))}</text>')
    passo = nice_step(xhi - xlo)
    ticks = [t for t in range(int(math.ceil(xlo / passo) * passo), int(xhi) + 1, passo)]
    eixo = "".join(f'<line x1="{px(t):.1f}" y1="{base}" x2="{px(t):.1f}" y2="{base + 4}" stroke="#9AA6B2"/>' for t in ticks)
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}"><defs>{"".join(defs)}</defs>{"".join(zonas)}'
           f'<polyline points="{ponto}" fill="none" stroke="#3D424A" stroke-width="1.6"/>'
           f'<line x1="{ml}" y1="{base}" x2="{W - mr}" y2="{base}" stroke="#C6D2DC"/>{eixo}{"".join(rotulos)}{"".join(marcas)}'
           f'<line class="pr-m" x1="0" y1="{mt + 10}" x2="0" y2="{base}" stroke="#111" stroke-width="2.5" visibility="hidden"/>'
           f'<text class="pr-mt" x="0" y="{mt + 6}" text-anchor="middle" font-size="12" font-weight="700" fill="#111" visibility="hidden"></text></svg>')
    meta = {"x0": xlo, "x1": xhi, "a": round(px(xlo), 1), "b": round(px(xhi), 1),
            "q": [round(q[p]) for p in (0.10, 0.25, 0.5, 0.75, 0.90)]}
    return svg, meta


def bloco_curva(T: Tarifas, keys, uid: str, quem: str):
    """Curva do mês mais recente com seletor de companhia e campo para digitar o preço. Devolve (html, mediana, p25, p75)."""
    conjuntos = [("", "Todas as companhias", T.hist(keys, ""))]
    for cia, nome in CIA_TAR.items():
        h = T.hist(keys, cia)
        if h and sum(h) >= MIN_ASS_CIA:
            conjuntos.append((cia, nome, h))
    dados, svgs = {}, []
    for i, (cia, nome, h) in enumerate(conjuntos):
        svg, meta = svg_curva(h, T.edges, f"{uid}{i}", f"Curva de preços de {quem}: {nome}, {mes_nome(T.ref)}")
        meta["c"] = h
        meta["n"] = sum(h)
        meta["nome"] = nome
        dados[cia] = meta
        svgs.append(f'<div class="pr-svg" data-k="{cia}"{"" if i == 0 else " hidden"}>{svg}</div>')
    cfg = {"e": T.edges, "m": mes_nome(T.ref), "d": dados}
    attr = html.escape(json.dumps(cfg, ensure_ascii=False, separators=(",", ":")), quote=True)
    sel = ""
    if len(conjuntos) > 1:
        sel = ('<label>Companhia <select class="pr-sel">' + "".join(f'<option value="{c}">{esc(n)}</option>' for c, n, _ in conjuntos) + "</select></label>")
    h0 = conjuntos[0][2]
    html_ = (f'<div class="pr" data-pr="{attr}"><div class="pr-ctl" hidden>{sel}<label>Preço que você viu (R$)'
             f'<input class="pr-in" type="text" inputmode="decimal" autocomplete="off" placeholder="ex.: 650"></label></div>'
             f'<p class="pr-res" aria-live="polite">Digite o preço que você viu para ver onde ele fica na curva.</p>{"".join(svgs)}'
             f'<p class="nota">Valores em R$ sob as linhas tracejadas: 25% dos bilhetes custaram menos que o primeiro, metade menos que o do meio e 25% mais que o último. Altura da curva = quantidade de bilhetes vendidos naquele preço.</p></div>')
    return html_, hist_pct(h0, T.edges, 0.5), hist_pct(h0, T.edges, 0.25), hist_pct(h0, T.edges, 0.75)


def bloco_preco(B: Base, keys, nome: str, uid: str, titulo: str | None = None):
    """Bloco "Quanto custa" de uma rota ou trajeto. Devolve (html, perguntas do FAQ, resumo ou None)."""
    T = getattr(B, "tar", None)
    if not T:
        return "", [], None
    keys = [k for k in keys if k in T.h]
    h_all = T.hist(keys, "") if keys else None
    tot = T.soma(keys) if keys else {}
    if not h_all or sum(h_all) < MIN_ASS_TOTAL or T.ref not in tot:
        return "", [], None
    ref = T.ref
    media = tot[ref][1] / tot[ref][0]
    m0 = mes_ant_ano(ref)
    var = None
    if m0 in tot and tot[m0][0] >= 150 and tot[ref][0] >= 150:
        var = media / (tot[m0][1] / tot[m0][0] * T.fator[m0]) - 1
    graf, todas = grafico_preco_13m(T, keys, f"Preço médio da passagem de {nome} nos últimos 13 meses")
    curva, med, p25, p75 = bloco_curva(T, keys, uid, nome)
    var_html = ""
    if var is not None and abs(var) >= 0.0005:
        var_html = (f'<span class="{"down" if var > 0 else "up"}">{"▲" if var > 0 else "▼"} {nf(abs(var) * 100, 1)}%</span> '
                    f'contra {mes_curto(m0)}')
    elif var is not None:
        var_html = f"igual a {mes_curto(m0)}"
    tiles = '<div class="tiles">' + "".join([
        tile(f"Tarifa média em {mes_curto(ref)}", rs(media), var_html),
        tile("Metade pagou até", rs(med), "valor mediano"),
        tile("Faixa típica", f"{nf(p25)} a {nf(p75)}", "metade dos bilhetes, em R$"),
        tile("Bilhetes analisados", abrevia(sum(h_all)), f"vendidos em {mes_nome(ref)}"),
    ]) + "</div>"
    # companhias
    lin = []
    for cia, cn in CIA_TAR.items():
        s = T.soma(keys, cia)
        if ref in s and s[ref][0] >= MIN_ASS_CIA:
            a = s[ref][1] / s[ref][0]
            v = ""
            if m0 in s and s[m0][0] >= MIN_ASS_CIA:
                x = a / (s[m0][1] / s[m0][0] * T.fator[m0]) - 1
                v = f'<span class="{"down" if x > 0 else "up"}">{"▲" if x > 0 else "▼"} {nf(abs(x) * 100, 1)}%</span>'
            lin.append((a, f'<tr><td>{esc(cn)}</td><td class="r num"><b>{rs(a)}</b></td><td class="r num">{v or "–"}</td><td class="r num">{abrevia(s[ref][0])}</td></tr>'))
    tab_cia = ""
    if len(lin) > 1:
        tab_cia = ('<h3>Preço médio por companhia</h3><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col" class="r">Tarifa média</th>'
                   f'<th scope="col" class="r">Contra {mes_curto(m0)}</th><th scope="col" class="r">Bilhetes</th></tr></thead><tbody>'
                   + "".join(t for _, t in sorted(lin)) + "</tbody></table></div>")
    amostra = " Esta rota teve poucos bilhetes vendidos no mês, então a média e a curva oscilam mais." if sum(h_all) < 1000 else ""
    corr = (f"Os valores dos meses anteriores estão corrigidos pela inflação (IPCA) para reais de {mes_nome(ref)}, por isso a linha mostra a variação real do preço."
            if T.real else "Os valores não estão corrigidos pela inflação.")
    corpo = f"""<section class="card" id="preco"><div class="card-head"><h2>{esc(titulo or "Quanto custa a passagem")}</h2><span class="small">Bilhetes vendidos em {mes_nome(ref)}</span></div>
{tiles}
<h3>Preço médio nos últimos 13 meses</h3>{graf}
<p class="nota">Tarifa média ponderada pela quantidade de bilhetes vendidos em cada mês. {corr}</p>
{tab_cia}
<h3>Onde o seu preço fica? A curva de {mes_nome(ref)}</h3>
<p class="small">Cada ponto da curva mostra quantos bilhetes foram vendidos a cada valor. Digite o preço que você viu e confira se ele é barato, normal ou caro para esta rota.</p>
{curva}
<p class="nota">Fonte: ANAC, microdados das tarifas aéreas domésticas comercializadas. É a tarifa seca (sem taxa de embarque, bagagem e extras) de passagens vendidas no mês, seja qual for a data do voo;
passagens de ida e volta entram como dois trechos e podem incluir viagens com conexão entre as duas cidades. A curva não separa quem comprou com meses de antecedência de quem comprou na véspera:
compras de última hora tendem a ficar na faixa cara, e promoções com muita antecedência na faixa barata. Use como referência, não como garantia de preço.{amostra}</p></section>"""
    pares = [(f"Quanto custa a passagem de {nome}?",
              f"Em {mes_nome(ref)}, a tarifa média dos bilhetes vendidos para esta rota foi de {rs(media)}. Metade dos passageiros pagou até {rs(med)}, "
              f"e a faixa típica (metade dos bilhetes, do 25º ao 75º percentil) ficou entre {rs(p25)} e {rs(p75)}. "
              "São valores sem taxa de embarque e extras, e não o preço de uma data específica.")]
    val = [(m, v) for m, v in zip(T.meses, todas) if v is not None]
    if len(val) >= 8:
        bar, car = min(val, key=lambda t: t[1]), max(val, key=lambda t: t[1])
        pares.append((f"Qual o mês mais barato para comprar passagem de {nome}?",
                      f"Nos últimos {len(val)} meses, a tarifa média (corrigida pela inflação) foi mais baixa nos bilhetes vendidos em {mes_nome(bar[0])} ({rs(bar[1])}) "
                      f"e mais alta nos vendidos em {mes_nome(car[0])} ({rs(car[1])}). O mês é o da compra, não o da viagem."))
    if var is not None:
        sub = "subiu" if var > 0.005 else "caiu" if var < -0.005 else "ficou estável"
        pares.append((f"A passagem de {nome} está mais cara ou mais barata que um ano atrás?",
                      f"A tarifa média {sub}{'' if sub == 'ficou estável' else f' {nf(abs(var) * 100, 1)}%'} em termos reais, de {mes_nome(m0)} para {mes_nome(ref)}"
                      f"{' (já descontada a inflação do período)' if T.real else ''}."))
    return corpo, pares, {"media": media, "mediana": med, "p25": p25, "p75": p75, "var": var}


def preco_card_voo(B: Base, o: str, d: str) -> str:
    T = getattr(B, "tar", None)
    if not T or (o, d) not in B.pag_rotas:
        return ""
    k = f"{o}-{d}"
    tot = T.soma([k]) if k in T.h else {}
    h = T.hist([k], "") if tot else None
    if not h or sum(h) < MIN_ASS_TOTAL or T.ref not in tot:
        return ""
    a = tot[T.ref][1] / tot[T.ref][0]
    return (f'<section class="card"><div class="card-head"><h2>Quanto custa a rota {esc(B.cod(o))} → {esc(B.cod(d))}</h2><span class="small">Bilhetes vendidos em {mes_nome(T.ref)}</span></div>'
            f'<p>Tarifa média da rota: <b>{rs(a)}</b>; metade dos bilhetes custou entre {rs(hist_pct(h, T.edges, 0.25))} e {rs(hist_pct(h, T.edges, 0.75))}. '
            f'É o preço da rota, não deste voo específico.</p><div class="btns"><a class="btn sec" href="/rotas/{B.rota_slug(o, d)}/#preco">Ver o preço médio, a curva e comparar o seu preço</a></div></section>')


def pg_precos(B: Base, rota_pag) -> str:
    T = B.tar
    ref = T.ref
    tot = {m: v for m, v in T.nac.items()}
    media = tot[ref][1] / tot[ref][0]
    m0 = mes_ant_ano(ref)
    var = media / (tot[m0][1] / tot[m0][0] * T.fator[m0]) - 1 if m0 in tot else None
    serie = [tot[m][1] / tot[m][0] * T.fator[m] for m in T.meses]
    rot = [mes_curto(m) for m in T.meses]
    cfg = {"t": "l", "p": list(T.meses), "l": rot, "s": [{"n": "Tarifa média no Brasil", "v": [round(v) for v in serie], "c": COR_TAR[""]}],
           "d": 0, "pre": "R$ ", "w": 0, "z": 0}
    graf = fam_gr(cfg, svg_linha_preco(rot, serie, "Tarifa média"), "Tarifa média das passagens domésticas nos últimos 13 meses")
    # curva nacional
    T_h = {"__br__": {"": T.nac_h}}
    T.h.update(T_h)
    curva, med, p25, p75 = bloco_curva(T, ["__br__"], "br", "todas as rotas do Brasil")
    del T.h["__br__"]
    var_html = ""
    if var is not None:
        var_html = f'<span class="{"down" if var > 0 else "up"}">{"▲" if var > 0 else "▼"} {nf(abs(var) * 100, 1)}%</span> contra {mes_curto(m0)}'
    tiles = '<div class="tiles">' + "".join([
        tile(f"Tarifa média em {mes_curto(ref)}", rs(media), var_html),
        tile("Metade pagou até", rs(med), "valor mediano"),
        tile("Faixa típica", f"{nf(p25)} a {nf(p75)}", "metade dos bilhetes, em R$"),
        tile("Bilhetes analisados", abrevia(tot[ref][0]), f"vendidos em {mes_nome(ref)}"),
    ]) + "</div>"
    # rotas mais caras, mais baratas e maiores variações
    itens = []
    for k, meses in T.rotas.items():
        if ref not in meses or meses[ref][0] < 2500 or k not in T.h:
            continue
        o, d = k.split("-")
        a = meses[ref][1] / meses[ref][0]
        v = None
        if m0 in meses and meses[m0][0] >= 1500:
            v = a / (meses[m0][1] / meses[m0][0] * T.fator[m0]) - 1
        itens.append((k, o, d, a, v, meses[ref][0]))

    def nome_rota(o, d):
        txt = f"{esc(B.cod(o))} → {esc(B.cod(d))}"
        lk = f'<a href="/rotas/{B.rota_slug(o, d)}/#preco">{txt}</a>' if (o, d) in B.pag_rotas else txt
        return f'<td class="wrap">{lk} <span class="small">{esc(B.cidade(o))} → {esc(B.cidade(d))}</span></td>'

    def tabela(lst, mostra_var=True):
        return "".join(f'<tr>{nome_rota(o, d)}<td class="r num"><b>{rs(a)}</b></td><td class="r num">{(("▲ " if v > 0 else "▼ ") + nf(abs(v) * 100, 1) + "%") if v is not None else "–"}</td></tr>'
                       for _, o, d, a, v, _ in lst)
    cab = '<thead><tr><th scope="col">Rota</th><th scope="col" class="r">Tarifa média</th><th scope="col" class="r">Contra {}</th></tr></thead>'.format(mes_curto(m0))
    caras = sorted(itens, key=lambda t: -t[3])[:15]
    baratas = sorted(itens, key=lambda t: t[3])[:15]
    com_var = [t for t in itens if t[4] is not None]
    altas = sorted(com_var, key=lambda t: -t[4])[:10]
    quedas = sorted(com_var, key=lambda t: t[4])[:10]
    pares = [("Quanto custa, em média, uma passagem aérea doméstica no Brasil?",
              f"Em {mes_nome(ref)}, a tarifa média dos bilhetes vendidos para voos domésticos foi de {rs(media)}, e metade dos passageiros pagou até {rs(med)} (dados da ANAC, tarifa seca sem taxas)."),
             ("As passagens aéreas estão mais caras que um ano atrás?",
              (f"A tarifa média {'subiu' if var > 0 else 'caiu'} {nf(abs(var) * 100, 1)}% em termos reais entre {mes_nome(m0)} e {mes_nome(ref)}, já descontada a inflação (IPCA)." if var is not None and T.real
               else "Veja o gráfico de 13 meses acima para acompanhar a evolução do preço médio."))]
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Preços · {mes_nome(ref)}</span><h1>Preço das passagens aéreas no Brasil</h1>
<p class="lead">A tarifa média dos bilhetes domésticos vendidos em {mes_nome(ref)} foi de <strong>{rs(media)}</strong>. Veja a evolução em 13 meses, a curva de preços e as rotas mais caras e mais baratas, com dados oficiais da ANAC.</p></section>
{tiles}
<section class="card"><h2>Preço médio nos últimos 13 meses</h2>{graf}<p class="nota">Valores corrigidos pela inflação (IPCA) para reais de {mes_nome(ref)}. Média ponderada pela quantidade de bilhetes vendidos em cada mês.</p></section>
<section class="card"><h2>Onde o seu preço fica? A curva do país em {mes_nome(ref)}</h2><p class="small">Digite o preço que você viu. Para uma rota específica, use a página da rota, com a curva só daquele trecho.</p>{curva}</section>
<div class="grid2">
<section class="card"><div class="card-head"><h2>Rotas mais caras</h2><span class="small">{mes_curto(ref)}</span></div><div class="tw"><table>{cab}<tbody>{tabela(caras)}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Rotas mais baratas</h2><span class="small">{mes_curto(ref)}</span></div><div class="tw"><table>{cab}<tbody>{tabela(baratas)}</tbody></table></div></section>
</div>
<div class="grid2">
<section class="card"><div class="card-head"><h2>Maiores altas em 12 meses</h2><span class="small">Variação real</span></div><div class="tw"><table>{cab}<tbody>{tabela(altas)}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Maiores quedas em 12 meses</h2><span class="small">Variação real</span></div><div class="tw"><table>{cab}<tbody>{tabela(quedas)}</tbody></table></div></section>
</div>
<p class="nota">Só entram rotas com pelo menos 2.500 bilhetes vendidos em {mes_nome(ref)}. Fonte: ANAC, microdados das tarifas aéreas domésticas comercializadas: tarifa seca (sem taxas e extras) de passagens vendidas no mês, seja qual for a data do voo. A rota é a origem e o destino do passageiro, mesmo com conexão.</p>
{aviso_direitos()}
{faq}"""
    return pagina(B, "/precos/", f"Preço das passagens aéreas no Brasil: média e curva de {mes_curto(ref)} | Voo em Números",
                  f"Tarifa média das passagens domésticas em {mes_nome(ref)}: {rs(media)}. Evolução em 13 meses, rotas mais caras e mais baratas e uma curva para comparar o seu preço, com dados da ANAC.",
                  corpo, "/precos/", migalhas=[("", "Preços")], jsonld=[ld])


def preco_card_home(B: Base) -> str:
    T = getattr(B, "tar", None)
    if not T:
        return ""
    ref = T.ref
    tot = T.nac[ref]
    media = tot[1] / tot[0]
    m0 = mes_ant_ano(ref)
    var = ""
    if m0 in T.nac:
        v = media / (T.nac[m0][1] / T.nac[m0][0] * T.fator[m0]) - 1
        var = f'<span class="{"down" if v > 0 else "up"}">{"▲" if v > 0 else "▼"} {nf(abs(v) * 100, 1)}%</span> contra {mes_curto(m0)}'
    return (f'<section class="card"><div class="card-head"><h2>Quanto custa voar?</h2><span class="small">Bilhetes vendidos em {mes_nome(ref)}</span></div>'
            f'<div class="tiles">{tile("Tarifa média no Brasil", rs(media), var)}</div>'
            f'<div class="btns"><a class="btn sec" href="/precos/">Ver a curva de preços, as rotas mais caras e as mais baratas</a></div></section>')



def pg_404(B: Base) -> str:
    corpo = ('<section class="hero"><h1>Página não encontrada</h1><p class="lead">Este endereço não existe ou o voo deixou de operar. '
             'Use a busca para achar um voo, uma rota ou um aeroporto.</p>'
             '<div class="busca" role="search"><label for="busca" class="sr">Buscar</label><input id="busca" type="search" autocomplete="off" '
             'placeholder="Voo, rota, cidade ou aeroporto"><div id="busca-res" aria-live="polite"></div></div></section>')
    return pagina(B, "/404.html", "Página não encontrada | Voo em Números", "Página não encontrada.", corpo).replace(
        '<link rel="canonical"', '<meta name="robots" content="noindex"><link rel="canonical"')


# ---------------------------------------------------------------- imagens
def gerar_imagens(B: Base):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow não instalado; imagens não geradas")
        return
    fontes = SITE / "fontes"

    def f(bold, n):
        return ImageFont.truetype(str(fontes / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), n)
    ACC, INK, MUT, BG = (91, 63, 196), (20, 22, 26), (90, 96, 112), (246, 245, 250)
    T = B.tot[B.ref]
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 14], fill=ACC)
    d.text((60, 46), "Voo ", font=f(True, 36), fill=INK)
    d.text((60 + d.textlength("Voo ", font=f(True, 36)), 46), "em Números", font=f(True, 36), fill=ACC)
    d.text((60, 110), f"Pontualidade dos voos · {mes_nome(B.ref)}", font=f(True, 44), fill=INK)
    x = 60
    for rot, val in (("No horário", pc(T.p_pont)), ("Cancelados", pc(T.p_canc)), ("Voos previstos", nf(T.prev))):
        d.text((x, 200), rot, font=f(False, 28), fill=MUT)
        d.text((x, 238), val, font=f(True, 58), fill=INK)
        x += 370
    rot, val, pers = serie_13(B, B.tot, None)
    rot, val = rot[-13:], val[-13:]
    topo, base = 360, H - 70
    vals = [v for v in val if v is not None]
    mn = max(0, min(vals) - 0.1)
    passo = (W - 120) / len(val)
    bw = passo * 0.6
    for i, (r, v) in enumerate(zip(rot, val)):
        x0 = 60 + i * passo + (passo - bw) / 2
        if v is not None:
            h = (v - mn) / (1 - mn) * (base - topo)
            d.rounded_rectangle([x0, base - h, x0 + bw, base], radius=4, fill=ACC if i == len(val) - 1 else (185, 174, 232))
        d.text((x0 + bw / 2, base + 10), r, font=f(i == len(val) - 1, 18), fill=INK if i == len(val) - 1 else MUT, anchor="mt")
    d.text((60, H - 26), "Fonte: ANAC (base VRA) · vooemnumeros.com.br", font=f(False, 20), fill=MUT, anchor="lm")
    (SAIDA / "assets").mkdir(parents=True, exist_ok=True)
    im.save(SAIDA / "assets" / "og.png", optimize=True)

    # ícones
    def icone(n):
        ic = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        di = ImageDraw.Draw(ic)
        s = n / 30
        di.rounded_rectangle([1 * s, 1 * s, 29 * s, 29 * s], radius=7 * s, fill=ACC)
        pts = [(7, 17.5), (23, 9.5), (19.8, 18.8), (15.5, 16.2), (12.6, 20), (12.2, 15.3)]
        di.polygon([(px * s, py * s) for px, py in pts], fill=(255, 255, 255))
        di.rounded_rectangle([7 * s, 22 * s, 23 * s, 23.8 * s], radius=0.9 * s, fill=(255, 255, 255, 180))
        return ic
    icone(180).save(SAIDA / "assets" / "apple-touch-icon.png")
    icone(64).save(SAIDA / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])



# ---------------------------------------------------------------- resumo do mês
# Todo mês, quando a ANAC publica os dados, sai um resumo com manchete, o que mudou e o ranking.
# Como o site guarda todos os meses, os resumos dos meses antigos são refeitos a partir dos mesmos dados.
def mes_anterior(m: str) -> str:
    a, mm = int(m[:4]), int(m[5:]) - 1
    return f"{a - 1}-12" if mm == 0 else f"{a}-{mm:02d}"


def nome_mes(m: str) -> str:
    return MESES[int(m[5:]) - 1]


MIN_EXTREMO = 6      # "melhor/pior em N meses" só aparece quando N chega a isso
MIN_JANELA = 12      # recorde desde o início da série só vale com pelo menos um ano de histórico
LIMITE_X = 280       # caracteres do post no X
PESO_LINK_X = 23     # o X conta qualquer link como 23 caracteres


def _extremo(valores: list, idx: int):
    """Diz se o valor de `idx` é o maior ou o menor em N meses: {'tipo', 'n', 'janela'} ou None.
    N é quantos meses para trás ele se sustenta como o mais alto (ou o mais baixo); se nenhum mês da série o supera,
    N é o tamanho da série ('janela': True)."""
    v = valores[idx]
    if v is None:
        return None
    melhor = None
    for tipo, bate in (("maior", lambda x: x >= v), ("menor", lambda x: x <= v)):
        j = next((k for k in range(idx - 1, -1, -1) if valores[k] is not None and bate(valores[k])), None)
        if j is None:
            n, janela = idx + 1, True
            if n < MIN_JANELA:
                continue
        else:
            n, janela = idx - j, False
            if n < MIN_EXTREMO:
                continue
        if melhor is None or n > melhor["n"]:
            melhor = {"tipo": tipo, "n": n, "janela": janela}
    return melhor


def pp_txt(dif: float, casas: int = 1) -> str:
    """Diferença em pontos percentuais: 1.04 -> '+1,0 p.p.'."""
    return ("+" if dif > 0 else "−" if dif < 0 else "") + nf(abs(dif), casas) + " p.p."


def _comp_pp(dif, ref: str):
    if dif is None:
        return None
    if abs(dif) < 0.05:
        return f"estável sobre {ref}"
    return f"{'alta' if dif > 0 else 'queda'} de {nf(abs(dif), 1)} p.p. sobre {ref}"


def resumo_dados(B: Base, m: str) -> dict:
    T = B.tot[m]
    ant = mes_anterior(m)
    janela = [x for x in B.lista if x <= m][-12:]
    lista = [x for x in B.lista if x <= m]

    def mov(tab, minimo):
        """Quem tem medida nos dois meses (com voos suficientes): (chave, acc, acc do mês anterior, variação em p.p.), da maior alta à maior queda."""
        out = []
        for k, a in tab[m].items():
            a1 = tab.get(ant, {}).get(k)
            if a.prev >= minimo and a.p_pont is not None and a1 and a1.prev >= minimo and a1.p_pont is not None:
                out.append((k, a, a1, 100 * (a.p_pont - a1.p_pont)))
        return sorted(out, key=lambda t: -t[3])

    return {
        "m": m, "ant": ant, "T": T, "T1": B.tot.get(ant), "T12": B.tot.get(mes_ant_ano(m)), "janela": janela,
        "pontos": [B.tot[x].p_pont for x in janela if B.tot[x].p_pont is not None],
        "extremo": _extremo([B.tot[x].p_pont if B.tot[x].med >= 10 else None for x in lista], len(lista) - 1),
        "desde": lista[0],
        "cias": sorted(((c, a) for c, a in B.cia[m].items() if a.prev >= MIN_CIA_RANK and a.p_pont is not None), key=lambda t: -t[1].p_pont),
        "aeros": sorted(((o, a) for o, a in B.aero[m].items() if a.prev >= MIN_AERO_RANK and a.p_pont is not None), key=lambda t: -t[1].p_pont),
        "rotas": sorted(((r, a) for r, a in B.rota[m].items() if a.prev >= MIN_ROTA_RANK and a.p_pont is not None), key=lambda t: t[1].p_pont),
        "cia_mov": mov(B.cia, MIN_CIA_RANK), "aero_mov": mov(B.aero, MIN_AERO_RANK),
    }


def resumo_manchete(d: dict) -> str:
    m, T, T1 = d["m"], d["T"], d["T1"]
    mes, pont, e = nome_mes(m), pc(T.p_pont), d.get("extremo")
    if e and e["tipo"] == "maior":
        return f"Melhor pontualidade em {e['n']} meses: {pont} dos voos chegaram no horário em {mes}"
    if e and e["tipo"] == "menor":
        return f"Pior pontualidade em {e['n']} meses: só {pont} dos voos chegaram no horário em {mes}"
    if T1 and T1.p_pont is not None:
        dif = 100 * (T.p_pont - T1.p_pont)
        if abs(dif) >= 0.1:
            return f"{pont} dos voos chegaram no horário em {mes}, {'alta' if dif > 0 else 'queda'} de {nf(abs(dif), 1)} p.p. sobre {nome_mes(d['ant'])}"
    return f"{pont} dos voos chegaram no horário em {mes}"


def resumo_abertura(d: dict) -> str:
    """Parágrafo de abertura: pontualidade, variação sobre o mês anterior e sobre um ano antes, cancelamentos e recorde."""
    T, T1, T12 = d["T"], d["T1"], d["T12"]
    d1 = 100 * (T.p_pont - T1.p_pont) if T1 and T1.p_pont is not None else None
    d12 = 100 * (T.p_pont - T12.p_pont) if T12 and T12.p_pont is not None else None

    def sentido(x):
        return None if x is None else "estável" if abs(x) < 0.05 else "alta" if x > 0 else "queda"
    if d12 is not None and sentido(d12) == sentido(d1) and sentido(d12) != "estável":
        partes = [_comp_pp(d1, nome_mes(d["ant"])), f"de {nf(abs(d12), 1)} p.p. sobre {mes_nome(mes_ant_ano(d['m']))}"]
    else:
        partes = [_comp_pp(d1, nome_mes(d["ant"])), _comp_pp(d12, mes_nome(mes_ant_ano(d["m"])))]
    partes = [p for p in partes if p]
    txt = f"Em {mes_nome(d['m'])}, {pc(T.p_pont)} dos voos domésticos chegaram no horário"
    txt += f" ({' e '.join(partes)})" if partes else ""
    txt += f" e {pc(T.p_canc)} foram cancelados. Foram {nf(T.prev)} voos previstos."
    e = d.get("extremo")
    if e:
        txt += f" É a {'melhor' if e['tipo'] == 'maior' else 'pior'} pontualidade em {e['n']} meses" + \
               (f", o período que o site cobre (desde {mes_nome(d['desde'])})." if e["janela"] else ".")
    return txt


def resumo_cias(B: Base, d: dict) -> list:
    """2 ou 3 companhias em destaque: a de maior alta, a de maior queda e, para completar, a mais (ou a menos) pontual."""
    mov, cs = d["cia_mov"], d["cias"]
    escolhidas = []

    def pega(c, a, dif, nota):
        if all(c != x[0] for x in escolhidas):
            escolhidas.append((c, a, dif, nota))
    dif_de = {c: dif for c, _, _, dif in mov}
    if mov and mov[0][3] > 0:
        pega(mov[0][0], mov[0][1], mov[0][3], "maior alta entre as companhias")
    if mov and mov[-1][3] < 0:
        pega(mov[-1][0], mov[-1][1], mov[-1][3], "maior queda entre as companhias")
    if cs:
        pega(cs[0][0], cs[0][1], dif_de.get(cs[0][0]), "a mais pontual do mês")
        if len(escolhidas) < 3 and len(cs) > 1:
            pega(cs[-1][0], cs[-1][1], dif_de.get(cs[-1][0]), "a menos pontual do mês")
    out = []
    for c, a, dif, nota in escolhidas[:3]:
        var = f", {pp_txt(dif)} sobre {nome_mes(d['ant'])}" if dif is not None else ""
        resto = f"{pc(a.p_pont)} dos voos no horário{var} e {pc(a.p_canc)} cancelados; {nota}."
        out.append({"nome": B.cia_nome(c), "texto": f"{B.cia_nome(c)}: {resto}", "html": f"{B.link_cia(c)}: {esc(resto)}"})
    return out


def resumo_insight(d: dict) -> str:
    """Uma ou duas frases sobre o que explica o mês, pela primeira regra que se aplica."""
    T, T1, achados = d["T"], d["T1"], []
    mv = d["aero_mov"]
    if len(mv) >= 10:
        sobe, cai = sum(1 for t in mv if t[3] > 0.05), sum(1 for t in mv if t[3] < -0.05)
        if sobe == len(mv):
            achados.append(f"A pontualidade melhorou em todos os {len(mv)} aeroportos acompanhados.")
        elif cai == len(mv):
            achados.append(f"A pontualidade piorou em todos os {len(mv)} aeroportos acompanhados.")
        else:
            achados.append(f"A pontualidade melhorou em {sobe} dos {len(mv)} aeroportos acompanhados e piorou em {cai}.")
    if T1 and T1.p_canc is not None and T.p_canc is not None:
        dif = 100 * (T.p_canc - T1.p_canc)
        if abs(dif) >= 0.3:
            achados.append(f"Os cancelamentos {'subiram' if dif > 0 else 'caíram'} para {pc(T.p_canc)} dos voos previstos ({pp_txt(dif)}).")
    cs = d["cias"]
    if len(cs) >= 2:
        gap = 100 * (cs[0][1].p_pont - cs[-1][1].p_pont)
        achados.append(f"Entre as companhias, a diferença entre a mais e a menos pontual foi de {nf(gap, 1)} p.p.")
    return " ".join(achados[:2])


def _linhas_aero(B: Base, lista: list) -> str:
    return "".join(
        f'<tr><td>{B.link_aero(o, esc(B.cod(o)))} <span class="small">{esc(B.cidade(o))}</span></td>'
        f'<td class="r num">{pc(a.p_pont)}</td><td class="r num">{pp_txt(dif)}</td></tr>' for o, a, a1, dif in lista)


def resumo_post_x(B: Base, d: dict, cias: list) -> str:
    """Post curto para o X: cabe em 280 caracteres (o link conta 23). Tira os extras, do menos para o mais importante, até caber."""
    m, T, url = d["m"], d["T"], f"{BASE}/resumo/{d['m']}/"
    d1 = 100 * (T.p_pont - d["T1"].p_pont) if d["T1"] and d["T1"].p_pont is not None else None
    cabeca = f"Pontualidade dos voos no Brasil em {mes_nome(m)}: {pc(T.p_pont)} chegaram no horário"
    cabeca += f" ({pp_txt(d1)} no mês)" if d1 is not None else ""
    cabeca += f" e {pc(T.p_canc)} foram cancelados."
    e = d.get("extremo")
    extremo = f"A {'melhor' if e['tipo'] == 'maior' else 'pior'} em {e['n']} meses." if e else ""
    cs = d["cias"]
    cia = f"Mais pontual: {B.cia_nome(cs[0][0])} ({pc(cs[0][1].p_pont)})." if cs else ""
    tags = ""   # posts do X sem hashtags
    for usa in ((1, 1, 1), (1, 0, 1), (1, 1, 0), (1, 0, 0), (0, 0, 0)):
        corpo = [cabeca] + ([extremo] if usa[0] and extremo else []) + ([cia] if usa[1] and cia else [])
        texto = " ".join(corpo) + f"\n\n{url}" + (f"\n{tags}" if usa[2] and tags else "")
        if len(texto.replace(url, "x" * PESO_LINK_X)) <= LIMITE_X:
            return texto
    return f"{cabeca}\n\n{url}"


def resumo_post(B: Base, d: dict, manchete: str, cias: list, insight: str) -> str:
    """Versão maior, para o LinkedIn, o WhatsApp ou o e-mail."""
    m, T = d["m"], d["T"]
    l = [f"Pontualidade dos voos no Brasil, {mes_nome(m)}", "", resumo_abertura(d), ""]
    up, down = [t for t in d["aero_mov"] if t[3] > 0][:3], [t for t in d["aero_mov"][::-1] if t[3] < 0][:3]
    if up or down:
        l.append("Entre os aeroportos:")
        if up:
            l.append("• Mais melhoraram: " + "; ".join(f"{B.cod(o)} ({pc(a.p_pont)}, {pp_txt(dif)})" for o, a, _, dif in up))
        if down:
            l.append("• Mais pioraram: " + "; ".join(f"{B.cod(o)} ({pc(a.p_pont)}, {pp_txt(dif)})" for o, a, _, dif in down))
        l.append("")
    if cias:
        l.append("Companhias em destaque:")
        l += [f"• {c['texto']}" for c in cias]
        l.append("")
    if insight:
        l += [insight, ""]
    l += ["Ranking completo de companhias, aeroportos e rotas:", f"{BASE}/resumo/{m}/", "",
          "#aviacao #voos #pontualidade #ANAC", "Fonte: ANAC, Voo Regular Ativo, organizada pelo Voo em Números."]
    return "\n".join(l)


def card_resumo(B: Base, d: dict) -> bool:
    """Imagem do resumo (resumo/AAAA-MM/card.png): pontualidade, cancelamentos e voos, com as barras dos últimos 13 meses."""
    m, T = d["m"], d["T"]
    T0 = d["T12"] if d["T12"] and d["T12"].med else None
    ref = mes_curto(mes_ant_ano(m))
    def pp(v, v0, sobe_e_bom):
        if v is None or v0 is None:
            return "", None
        dif = 100 * (v - v0)
        return f"{seta(round(dif, 1))} {nf(abs(dif), 1)} p.p. sobre {ref}", (None if round(dif, 1) == 0 else (dif > 0) == sobe_e_bom)
    v1, b1 = pp(T.p_pont, T0.p_pont if T0 else None, True)
    v2, b2 = pp(T.p_canc, T0.p_canc if T0 else None, False)
    v3 = ""
    if T0 and T0.prev:
        r = 100 * (T.prev / T0.prev - 1)
        v3 = f"{seta(round(r, 1))} {nf(abs(r), 1)}% sobre {ref}"
    meses = [x for x in B.lista if x <= m][-13:]
    barras = [(MES_CURTO[int(x[5:]) - 1], [100 * B.tot[x].p_pont if B.tot[x].med >= 10 and B.tot[x].p_pont is not None else None])
              for x in meses]
    return gera_card(SAIDA / "resumo" / m / "card.png", "Voo em Números", PORTAIS["voo"][2], f"Pontualidade dos voos · {mes_nome(m)}",
                     [("No horário", pc(T.p_pont), v1, b1), ("Cancelados", pc(T.p_canc), v2, b2), ("Voos previstos", nf(T.prev), v3, None)],
                     barras, None, f"% dos voos no horário, mês a mês · Fonte: ANAC · vooemnumeros.com.br/resumo/{m}/",
                     [nf(v[0], 1) if v[0] is not None else "" for _, v in barras])


def pg_resumo(B: Base, m: str) -> str:
    d = resumo_dados(B, m)
    tem_img = card_resumo(B, d)
    T, T12, mes = d["T"], d["T12"], mes_nome(m)
    manchete = resumo_manchete(d)
    cias, insight = resumo_cias(B, d), resumo_insight(d)
    post, post_x = resumo_post(B, d, manchete, cias, insight), resumo_post_x(B, d, cias)
    linhas = "".join(
        f'<tr><td><a href="/companhias/{B.cia_slug(c)}/">{esc(B.cia_nome(c))}</a></td><td style="min-width:200px">{meter(a.p_pont)}</td>'
        f'<td class="r num">{pc(a.p_canc)}</td><td class="r num">{min_txt(a.media_atr)}</td><td class="r num">{nf(a.prev)}</td></tr>'
        if c in B.pag_cias else
        f'<tr><td>{esc(B.cia_nome(c))}</td><td style="min-width:200px">{meter(a.p_pont)}</td>'
        f'<td class="r num">{pc(a.p_canc)}</td><td class="r num">{min_txt(a.media_atr)}</td><td class="r num">{nf(a.prev)}</td></tr>'
        for c, a in d["cias"])
    tab = ('<div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th>'
           f'<th scope="col" class="r">Atraso médio dos atrasados</th><th scope="col" class="r">Voos previstos</th></tr></thead><tbody>{linhas}</tbody></table></div>')
    meses13 = [x for x in B.lista if x <= m]
    graf = svg_barras([mes_curto(x) for x in meses13], [B.tot[x].p_pont if B.tot[x].med >= 10 else None for x in meses13],
                      periodos=meses13, aria=f"Percentual de voos domésticos no horário mês a mês até {mes}")
    up, down = [t for t in d["aero_mov"] if t[3] > 0][:5], [t for t in d["aero_mov"][::-1] if t[3] < 0][:5]
    cab_aero = ('<thead><tr><th scope="col">Aeroporto</th><th scope="col" class="r">No horário</th>'
                f'<th scope="col" class="r">Variação sobre {nome_mes(d["ant"])}</th></tr></thead>')
    aeros = ""
    if up or down:
        blocos = []
        for tit, lista, vazio in (("Aeroportos que mais melhoraram", up, "Nenhum aeroporto melhorou neste mês."),
                                  ("Aeroportos que mais pioraram", down, "Nenhum aeroporto piorou neste mês.")):
            corpo_t = (f'<div class="tw"><table>{cab_aero}<tbody>{_linhas_aero(B, lista)}</tbody></table></div>' if lista else f'<p class="small">{vazio}</p>')
            blocos.append(f'<div class="card"><h2>{tit}</h2><p class="small">Pontualidade na partida, em pontos percentuais; aeroportos com mais de {nf(MIN_AERO_RANK)} partidas no mês</p>{corpo_t}</div>')
        aeros = f'<div class="grid2">{"".join(blocos)}</div>'
    dest = ""
    if cias:
        dest = ('<section class="card"><h2>Companhias em destaque</h2><ul class="destaques">'
                + "".join(f"<li>{c['html']}</li>" for c in cias) + "</ul></section>")
    ins = f'<section class="card"><h2>Em resumo</h2><p>{esc(insight)}</p></section>' if insight else ""
    liks = [("/companhias/", "Ranking de companhias"), ("/aeroportos/", "Ranking de aeroportos"), ("/rotas/", "Rotas"), ("/", "Visão geral da pontualidade")]
    liks += [(f"/aeroportos/{B.aero_slug(o)}/", f"Aeroporto {B.cod(o)}") for o, a, a1, dif in (up[:1] + down[:1]) if o in B.pag_aero]
    links_html = "".join(f'<li><a href="{h}">{esc(t)}</a></li>' for h, t in liks)
    corpo = f"""
<section class="hero">
<span class="kicker">Resumo do mês · {mes}</span>
<h1>{esc(manchete)}</h1>
<p class="lead">{esc(resumo_abertura(d))}</p>
</section>
{tiles_acc(T, T12)}
{aeros}
{dest}
{ins}
<section class="card"><div class="card-head"><h2>Ranking das companhias</h2><span class="small">Companhias com mais de {nf(MIN_CIA_RANK)} voos no mês</span></div>{tab}
<p class="nota">No horário = chegada até 30 minutos depois do previsto, mesmo critério da ANAC. Fonte: ANAC, Voo Regular Ativo.</p></section>
<section class="card"><h2>Pontualidade mês a mês</h2>{graf}</section>
<section class="card"><h2>Para ir além</h2><ul class="links-resumo">{links_html}</ul></section>
<section class="card"><details class="compartilhe"><summary><h2>Compartilhe este resumo</h2></summary>
<p class="small">{TEXTO_COMPARTILHE}</p>
{bloco_imagem(f"voo-em-numeros-resumo-{m}.png", f"Pontualidade dos voos domésticos em {mes}: {pc(T.p_pont)} no horário, {pc(T.p_canc)} cancelados")}
<h3>Para o X</h3>
<textarea id="post-x" class="fam-post" readonly rows="6">{esc(post_x)}</textarea>
<div><button type="button" class="fam-btn" data-copiar="post-x"><span>Copiar texto do X</span></button> <span class="small" data-copiar-msg aria-live="polite"></span></div>
<h3>Para o LinkedIn</h3>
<textarea id="post" class="fam-post" readonly rows="14">{esc(post)}</textarea>
<div><button type="button" class="fam-btn" data-copiar="post"><span>Copiar texto do LinkedIn</span></button> <span class="small" data-copiar-msg aria-live="polite"></span></div></details></section>
"""
    desc = (f"{cap(mes)}: {pc(T.p_pont)} dos voos domésticos no horário, {pc(T.p_canc)} cancelados. "
            "O que mudou, companhias, aeroportos e rotas, com dados oficiais da ANAC.")
    ld = {"@context": "https://schema.org", "@type": "Article", "headline": manchete, "inLanguage": "pt-BR",
          "datePublished": B.gerado.strftime("%Y-%m-%d"), "author": {"@type": "Organization", "name": "Voo em Números", "url": BASE + "/"},
          "mainEntityOfPage": f"{BASE}/resumo/{m}/"}
    img = f"{BASE}/resumo/{m}/card.png" if tem_img else None
    if img:
        ld["image"] = img
    return pagina(B, f"/resumo/{m}/", f"{manchete} | Voo em Números", desc, corpo if tem_img else sem_imagem(corpo), "/resumo/",
                  migalhas=[("/resumo/", "Resumos mensais"), (None, cap(mes))], jsonld=[ld], imagem=img)


def pg_resumos(B: Base) -> str:
    itens = "".join(
        f'<li><a href="/resumo/{m}/"><b>{cap(mes_nome(m))}</b><span>{esc(resumo_manchete(resumo_dados(B, m)))}</span></a></li>'
        for m in reversed(B.lista))
    corpo = (f'<section class="hero"><span class="kicker">Resumos mensais</span><h1>A pontualidade dos voos mês a mês</h1>'
             f'<p class="lead">Todo mês, quando a ANAC publica os dados, sai aqui um resumo com a manchete, o que mudou e o ranking de companhias, '
             f'aeroportos e rotas.</p></section><section class="card"><ul class="lista-resumos">{itens}</ul></section>')
    return pagina(B, "/resumo/", "Resumos mensais da pontualidade dos voos | Voo em Números",
                  "Resumo mensal da pontualidade e dos cancelamentos dos voos domésticos no Brasil, com dados da ANAC.", corpo, "/resumo/",
                  migalhas=[(None, "Resumos mensais")])


def resumo_card_home(B: Base) -> str:
    d = resumo_dados(B, B.ref)
    return (f'<section class="card aviso"><div><span class="kicker">Resumo de {nome_mes(B.ref)}</span>'
            f'<h2>{esc(resumo_manchete(d))}</h2></div><a class="btn" href="/resumo/{B.ref}/">Ler o resumo</a></section>')


# ---------------------------------------------------------------- principal
def cias_pag_pre(B: Base):
    return [c for c in {c for m in B.u12 for c in B.cia[m]} if B.soma(B.cia, c, B.u12).prev >= 300]


def escreve(caminho: str, conteudo: str):
    p = SAIDA / caminho.strip("/") / "index.html" if caminho.endswith("/") else SAIDA / caminho.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")


LLMS_TXT = '# Voo em Números\n\n> Pontualidade, atrasos e cancelamentos dos voos domésticos regulares no Brasil, por companhia aérea, aeroporto, rota e número de voo, com base nos dados públicos da ANAC.\n\nConsidera atrasado o voo que chega mais de 30 minutos depois do horário previsto, o mesmo corte da ANAC. Cada página mostra percentual no horário, cancelamentos, atraso médio e ranking. Os números descrevem o passado e não garantem o desempenho de um voo específico.\n\n## Principais páginas\n- [Resumo do mês](__BASE__/resumo/): panorama dos voos domésticos\n- [Companhias aéreas](__BASE__/companhias/): pontualidade e cancelamentos por empresa\n- [Aeroportos](__BASE__/aeroportos/): atrasos e cancelamentos por aeroporto\n- [Cidades e estados](__BASE__/cidades/): voos que saem e chegam em cada cidade, com destinos e companhias\n- [Rankings](__BASE__/rankings/): aeroportos, rotas e voos que mais atrasam, cancelam e cumprem o horário\n- [Rotas](__BASE__/rotas/): desempenho de cada ligação entre aeroportos\n- [Preços](__BASE__/precos/): tarifa média das passagens, evolução em 13 meses, curva de preços e rotas mais caras e mais baratas (tarifas da ANAC)\n- [Demanda](__BASE__/demanda/): passageiros, assentos e ocupação\n- [Quando ir](__BASE__/quando-ir/): melhor época para cada destino, com clima (Inmet), preço da passagem e movimento mês a mês\n- [Mapa](__BASE__/mapa/): visão geográfica da malha\n- [Fim de ano](__BASE__/fim-de-ano/): o que esperar dos voos nas festas\n- [Direitos do passageiro](__BASE__/direitos/): o que fazer em caso de atraso ou cancelamento\n- [Como funciona](__BASE__/sobre/): fonte, método e limitações\n\n## Fonte e atualização\n- Voos: base Voo Regular Ativo (VRA), da ANAC, atualizada todo mês.\n- Passageiros e ocupação: base Dados Estatísticos do Transporte Aéreo, da ANAC, com cerca de dois meses de atraso.\n- Entram voos domésticos regulares de passageiros. Ficam de fora internacionais, só de carga e táxi aéreo.\n- A base não informa o motivo do atraso nem se o cancelamento foi avisado com antecedência.\n\n## Como citar\n- Cite o nome do portal e o link da página usada. Os dados são públicos e os links levam à fonte oficial.\n- Cada página mostra o período dos dados. Informe o período ao usar um número.\n- O portal é independente e não tem ligação com governo, empresas ou instituições financeiras.\n\n## Família em Números\nPortais independentes de dados públicos do Brasil: Óleo em Números (https://oleoemnumeros.com.br), Comex em Números (https://comexemnumeros.com.br), Voo em Números (https://vooemnumeros.com.br) e Economia em Números (https://economiaemnumeros.com.br).\n\n## Contato\n- Erros, sugestões e pedidos de dados: __BASE__/contato/\n'


def main() -> int:
    B = Base(carrega())
    B.dem = Demanda(DEM_ARQ) if DEM_ARQ.exists() else None
    try:
        B.tar = Tarifas(TAR_ARQ) if TAR_ARQ.exists() else None
    except Exception as e:  # preço é um extra: se o arquivo vier ruim, o site sai sem ele
        print(f"Aviso: tarifas ignoradas ({e})")
        B.tar = None
    B.familia = carrega_familia(rede=os.environ.get("VOO_SEM_REDE") != "1")
    B.diario = carrega_diario()
    B.clima = carrega_clima()
    if SAIDA.exists():
        shutil.rmtree(SAIDA)
    SAIDA.mkdir(parents=True)
    (SAIDA / "assets").mkdir()

    # o que ganha página
    aero_pag = {a for m in B.u3 for a in B.aero[m]}
    aero_pag = {a for a in aero_pag if B.soma(B.aero, a, B.u3).prev >= MIN_PAG_AERO}
    rota_pag = {r for m in B.u3 for r in B.rota[m]}
    rota_pag = {r for r in rota_pag if B.soma(B.rota, r, B.u3).prev >= MIN_PAG_ROTA}
    todos_aero = {a for r in rota_pag for a in r} | aero_pag
    B.preparar_nomes(todos_aero)
    voo_pag = {}
    for k, legs in B.voo_legs.items():
        tot = sum(x.med for x in legs.values())
        if tot >= MIN_PAG_VOO:
            principais = sorted(legs.items(), key=lambda t: -t[1].prev)
            (o, d), _ = principais[0]
            trecho = f"{B.cidade(o)} → {B.cidade(d)}"
            if len(principais) > 1:
                trecho += f" e mais {len(principais) - 1} trecho{'s' if len(principais) > 2 else ''}"
            voo_pag[k] = trecho
    # evita dois voos com o mesmo endereço
    vistos = {}
    for k in list(voo_pag):
        s = B.voo_slug(*k)
        if s in vistos:
            del voo_pag[k]
        vistos[s] = k
    B.pag_cias, B.pag_rotas, B.pag_aero = set(cias_pag_pre(B)), set(rota_pag), set(aero_pag)
    B.pag_ca = {k for k in {k for m in B.u3 for k in B.cia_aero[m]}
                if k[0] in B.pag_cias and k[1] in aero_pag and B.soma(B.cia_aero, k, B.u3).prev >= MIN_CIA_AERO_3M}
    monta_cidades(B, todos_aero)
    B.quando_dados = {}
    for s_q in B.cid:
        try:
            dq = quando_dados(B, s_q)
        except Exception as e:  # um destino com dado estranho não derruba o site
            print(f"Aviso: quando ir {s_q}: {e}")
            dq = None
        if dq:
            B.quando_dados[s_q] = dq
    B.quando = set(B.quando_dados)
    if not B.quando:  # sem clima baixado ainda: o menu não aponta para página que não existe
        NAV[:] = [x for x in NAV if x[0] != "/quando-ir/"]
    cias_rank = [c for c, x in B.cia[B.ref].items() if x.prev >= MIN_CIA_RANK]
    cias_rank.sort(key=lambda c: -(B.cia[B.ref][c].p_pont or 0))
    cias_pag = cias_pag_pre(B)
    cias_pag.sort(key=lambda c: -B.soma(B.cia, c, B.u12).prev)
    fim = periodo_fim(B)
    # páginas fixas que existem (o bloco "Continue explorando" só liga a páginas existentes)
    B.fixas = {"/", "/companhias/", "/aeroportos/", "/rotas/", "/direitos/", "/mapa/", "/resumo/", "/cidades/", "/rankings/"}
    if fim:
        B.fixas.add("/fim-de-ano/")
    if B.dem:
        B.fixas.add("/demanda/")
    if B.tar:
        B.fixas.add("/precos/")

    urls = []

    def pub(caminho, conteudo, prio="0.6"):
        escreve(caminho, conteudo)
        urls.append((caminho, prio))

    pub("/", pg_inicio(B, cias_rank, aero_pag, rota_pag, voo_pag, fim), "1.0")
    pub("/companhias/", pg_companhias(B, cias_pag), "0.8")
    for c in cias_pag:
        pub(f"/companhias/{B.cia_slug(c)}/", pg_cia(B, c, aero_pag, rota_pag, voo_pag), "0.8")
    pub("/aeroportos/", pg_aeroportos(B, aero_pag), "0.8")
    for a in sorted(aero_pag):
        pub(f"/aeroportos/{B.aero_slug(a)}/", pg_aero(B, a, rota_pag, voo_pag), "0.7")
    pub("/rotas/", pg_rotas(B, rota_pag), "0.8")
    for o, d in sorted(rota_pag):
        pub(f"/rotas/{B.rota_slug(o, d)}/", pg_rota(B, o, d, rota_pag, voo_pag), "0.6")
    for k in sorted(voo_pag):
        pub(f"/voos/{B.voo_slug(*k)}/", pg_voo(B, k, voo_pag[k], voo_pag), "0.5")
    if fim:
        pub("/fim-de-ano/", pg_fim(B, fim, aero_pag), "0.9")
    pub("/cidades/", pg_cidades(B), "0.8")
    for s_ in sorted(B.cid):
        pub(f"/cidades/{s_}/", pg_cidade(B, s_, aero_pag, rota_pag, voo_pag), "0.7")
    if B.quando:
        pub("/quando-ir/", pg_quando_idx(B), "0.8")
        for s_ in sorted(B.quando):
            pub(f"/quando-ir/{s_}/", pg_quando(B, s_, rota_pag), "0.7")
    for uf_ in sorted(B.pag_est):
        pub(f"/estados/{uf_slug(uf_)}/", pg_estado(B, uf_, rota_pag), "0.7")
    for so_, sd_ in sorted(B.pag_pares):
        pub(f"/trajetos/{so_}-para-{sd_}/", pg_trajeto(B, so_, sd_, rota_pag), "0.6")
    for c_, a_ in sorted(B.pag_ca):
        pub(f"/companhias/{B.cia_slug(c_)}/{B.aero_slug(a_)}/", pg_cia_aero(B, c_, a_, rota_pag, voo_pag), "0.6")
    pub("/rankings/", pg_rankings(B, aero_pag, rota_pag, voo_pag), "0.9")
    for spec_ in RANKINGS:
        pub(f"/rankings/{spec_[0]}/", pg_ranking(B, spec_, aero_pag, rota_pag, voo_pag), "0.8")
    pub("/resumo/", pg_resumos(B), "0.8")
    for m in B.lista:
        pub(f"/resumo/{m}/", pg_resumo(B, m), "0.7" if m != B.ref else "0.9")
    pub("/direitos/", pg_direitos(B), "0.9")
    pub("/mapa/", pg_mapa(B, aero_pag), "0.8")
    if B.dem:
        pub("/demanda/", pg_demanda(B, aero_pag, rota_pag), "0.8")
    if B.tar:
        pub("/precos/", pg_precos(B, rota_pag), "0.9")
    pub("/sobre/", pg_sobre(B), "0.3")
    pub("/sugestoes/", pg_sugestoes(B), "0.2")
    pub("/contato/", pg_contato(B), "0.2")
    pub("/privacidade/", pg_privacidade(B), "0.2")
    escreve("/404.html", pg_404(B))

    # busca
    idx = [["Seus direitos: voo atrasado ou cancelado, overbooking, bagagem", "guia", "/direitos/"],
           ["Mapa da pontualidade dos aeroportos do Brasil por estado", "mapa", "/mapa/"]]
    if B.dem:
        idx.append(["Passageiros e ocupação dos voos: aeroporto lotado atrasa mais", "demanda", "/demanda/"])
    for c in cias_pag:
        idx.append([B.cia_nome(c), "companhia", f"/companhias/{B.cia_slug(c)}/"])
    for s_ in sorted(B.cid, key=lambda s: -B.cid[s]["dep"].prev):
        idx.append([f"{B.cid[s_]['nome']} {B.cid[s_]['uf']} voos cidade", "cidade", f"/cidades/{s_}/"])
    for uf_ in sorted(B.pag_est):
        idx.append([f"{UF_NOME[uf_]} {uf_} voos estado", "estado", f"/estados/{uf_slug(uf_)}/"])
    for so_, sd_ in sorted(B.pag_pares):
        idx.append([f"{B.cid[so_]['nome']} → {B.cid[sd_]['nome']} voos entre cidades", "trajeto", f"/trajetos/{so_}-para-{sd_}/"])
    for c_, a_ in sorted(B.pag_ca):
        idx.append([f"{B.cia_nome(c_)} em {B.cidade(a_)} {B.cod(a_)}", "companhia", f"/companhias/{B.cia_slug(c_)}/{B.aero_slug(a_)}/"])
    if B.tar:
        idx.append(["Preço das passagens aéreas: tarifa média, curva de preços, rotas mais caras e mais baratas", "guia", "/precos/"])
    for spec_ in RANKINGS:
        idx.append([spec_[1] + " " + spec_[4], "ranking", f"/rankings/{spec_[0]}/"])
    for a in sorted(aero_pag, key=lambda a: -B.soma(B.aero, a, B.u3).prev):
        idx.append([f"{B.cod(a)} {B.aero_nome(a)} {B.uf(a)}", "aeroporto", f"/aeroportos/{B.aero_slug(a)}/"])
    for o, d in sorted(rota_pag, key=lambda r: -B.soma(B.rota, r, B.u3).prev):
        idx.append([f"{B.cod(o)} → {B.cod(d)} {B.aero_nome(o)} → {B.aero_nome(d)}", "rota", f"/rotas/{B.rota_slug(o, d)}/"])
    for k in sorted(voo_pag, key=lambda k: -sum(x.prev for x in B.voo_legs[k].values())):
        idx.append([f"{B.cod_voo(*k)} {voo_pag[k]}", B.cia_nome(k[0]), f"/voos/{B.voo_slug(*k)}/"])
    (SAIDA / "busca.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # busca do cabeçalho (familia-busca.js): mesmo conteúdo, na ordem [título, endereço, tipo]
    geral = [["Companhias aéreas: pontualidade e cancelamentos", "/companhias/", "página"], ["Aeroportos do Brasil", "/aeroportos/", "página"], ["Rotas mais voadas", "/rotas/", "página"]]
    geral += [[t, u, k] for t, k, u in idx]
    (SAIDA / "busca-geral.json").write_text(json.dumps(geral, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # índice de cidades com aeroporto, lido pelos outros portais da família para ligar cidade → aeroporto
    por_cidade = {}
    for a in sorted(aero_pag, key=lambda a: -B.soma(B.aero, a, B.u3).prev):
        por_cidade.setdefault(chave_cidade(B.cidade(a), B.uf(a)), [B.cidade(a), B.uf(a), f"/aeroportos/{B.aero_slug(a)}/"])
    (SAIDA / "aeroportos" / "indice.json").write_text(
        json.dumps(sorted(por_cidade.values()), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # arquivos fixos
    shutil.copy(SITE / "estilo.css", SAIDA / "assets" / "estilo.css")
    shutil.copy(SITE / "app.js", SAIDA / "assets" / "app.js")
    shutil.copy(SITE / "familia.js", SAIDA / "assets" / "familia.js")
    shutil.copy(SITE / "familia-graficos.js", SAIDA / "assets" / "familia-graficos.js")
    shutil.copy(SITE / "precos.js", SAIDA / "assets" / "precos.js")
    shutil.copy(SITE / "rota.js", SAIDA / "assets" / "rota.js")
    shutil.copy(SITE / "familia-compartilhar.js", SAIDA / "assets" / "familia-compartilhar.js")
    shutil.copy(SITE / "familia-busca.js", SAIDA / "assets" / "familia-busca.js")
    (SAIDA / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30"><rect x="1" y="1" width="28" height="28" rx="7" fill="#2A9DE0"/>'
        '<path d="M7 17.5 23 9.5l-3.2 9.3-4.3-2.6-2.9 3.8-.4-4.7z" fill="#fff"/><rect x="7" y="22" width="16" height="1.8" rx=".9" fill="#fff" opacity=".7"/></svg>',
        encoding="utf-8")
    gerar_imagens(B)
    hoje = B.gerado.strftime("%Y-%m-%d")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{BASE}{u}</loc><lastmod>{hoje}</lastmod><priority>{p}</priority></url>" for u, p in urls]
    sm.append("</urlset>")
    (SAIDA / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    if ADSENSE_ID:
        (SAIDA / "ads.txt").write_text(f"google.com, {ADSENSE_ID}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    (SAIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (SAIDA / "llms.txt").write_text(LLMS_TXT.replace("__BASE__", BASE), encoding="utf-8")
    (SAIDA / "CNAME").write_text(DOMINIO + "\n", encoding="utf-8")
    print(f"Site gerado: {len(urls)} páginas ({len(aero_pag)} aeroportos, {len(rota_pag)} rotas, {len(voo_pag)} voos, "
          f"{len(cias_pag)} companhias). Dados até {B.ref}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
