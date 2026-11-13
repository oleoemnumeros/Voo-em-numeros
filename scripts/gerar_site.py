"""Gera o site estático do Voo em Números em docs/ a partir de data/meses/*.json.

Páginas: início, companhias, aeroportos, rotas, voos, fim de ano, como funciona,
mais sitemap.xml, robots.txt, 404.html, busca.json e a imagem de compartilhamento.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SITE = RAIZ / "site"
MESES_DIR = RAIZ / "data" / "meses"
IATA_ARQ = RAIZ / "data" / "aeroportos_iata.json"
SAIDA = RAIZ / "docs"
DOMINIO = "vooemnumeros.com.br"
BASE = f"https://{DOMINIO}"
GOAT = '<script data-goatcounter="https://vooemnumeros.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'

# Família em Números: para incluir um novo portal, acrescente uma linha nesta lista
FAMILIA = [
    ("Óleo em Números", "Petróleo e gás", "https://oleoemnumeros.com.br/", "#F59E0B"),
    ("Comex em Números", "Exportações e importações", "https://comexemnumeros.com.br/", "#37C0A5"),
    ("Voo em Números", "Pontualidade aérea", "https://vooemnumeros.com.br/", "#A58BF0"),
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
        self.voo_legs = defaultdict(lambda: defaultdict(Acc))   # (cia,num) -> (o,d) -> Acc (3 meses)
        self.voo_info = {}                                      # (cia,num) -> dados do mês mais recente
        self.voo_hora = defaultdict(Counter)                    # (cia,num,o,d) -> horário (3 meses)
        for m in self.lista:
            T, C, A, R, V = Acc(), defaultdict(Acc), defaultdict(Acc), defaultdict(Acc), defaultdict(Acc)
            CA, CR = defaultdict(Acc), defaultdict(Acc)
            for r in meses[m]["voos"]:
                cia, num, o, d = r[0], r[1], r[2], r[3]
                T.add(r); C[cia].add(r); A[o].add(r); R[(o, d)].add(r); V[(cia, num)].add(r)
                CA[(cia, o)].add(r); CR[(cia, o, d)].add(r)
                if m in self.u3:
                    self.voo_legs[(cia, num)][(o, d)].add(r)
                    self.voo_hora[(cia, num, o, d)][r[4]] += r[5]
                    self.voo_info[(cia, num, o, d)] = (r[4], r[17], r[18])
            self.tot[m], self.cia[m], self.aero[m], self.rota[m], self.voo[m] = T, C, A, R, V
            self.cia_aero[m], self.cia_rota[m] = CA, CR

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
    return ('<div class="familia"><p><b>Família em Números</b> · portais independentes que organizam dados públicos do Brasil</p>'
            f'<ul>{"".join(itens)}</ul></div>')


NAV = [("/", "Início"), ("/companhias/", "Companhias"), ("/aeroportos/", "Aeroportos"), ("/rotas/", "Rotas"), ("/mapa/", "Mapa"), ("/demanda/", "Passageiros"),
       ("/fim-de-ano/", "Fim de ano"), ("/direitos/", "Seus direitos"), ("/sobre/", "Como funciona")]
LOGO = ('<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><rect x="1" y="1" width="28" height="28" rx="7" fill="#5B3FC4"/>'
        '<path d="M7 17.5 23 9.5l-3.2 9.3-4.3-2.6-2.9 3.8-.4-4.7z" fill="#fff"/><rect x="7" y="22" width="16" height="1.8" rx=".9" fill="#fff" opacity=".7"/></svg>')


def pagina(B: Base, caminho: str, titulo: str, descricao: str, corpo: str, ativo: str = "",
           migalhas=None, jsonld=None) -> str:
    url = BASE + caminho
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
<title>{esc(titulo)}</title>
<meta name="description" content="{esc(descricao)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Voo em Números">
<meta property="og:title" content="{esc(titulo)}">
<meta property="og:description" content="{esc(descricao)}">
<meta property="og:url" content="{url}">
<meta property="og:locale" content="pt_BR">
<meta property="og:image" content="{BASE}/assets/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#5B3FC4">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/estilo.css?v={v}">
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
</main>
<footer><div>
<span><strong>Voo em Números</strong> · versão beta</span>
<span>Voos domésticos regulares de passageiros. No horário = chegada até 30 minutos depois do previsto, mesmo critério da ANAC. Cancelados contam sobre os voos previstos.</span>
<span><a href="/companhias/">Companhias</a> · <a href="/aeroportos/">Aeroportos</a> · <a href="/rotas/">Rotas</a> · <a href="/mapa/">Mapa</a> · <a href="/demanda/">Passageiros</a> · <a href="/fim-de-ano/">Fim de ano</a> · <a href="/direitos/">Seus direitos</a> · <a href="/sobre/">Como funciona</a></span>
</div>{familia_html()}</footer>
<script src="/assets/app.js?v={v}" defer></script>
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


def svg_barras(rotulos, valores, destaque_ultimo=True, altura=190, fmt=lambda v: pc(v, 0), cores=None, aria="", largura=720) -> str:
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
    out.append(f'<line x1="10" y1="{base}" x2="{W - 10}" y2="{base}" stroke="#C9C6D6"/>')
    for i, (r, v) in enumerate(zip(rotulos, valores)):
        x = 10 + i * passo + (passo - bw) / 2
        ult = destaque_ultimo and i == n - 1
        if v is not None:
            h = max(2, (v - mn) / (1 - mn) * (base - top)) if 1 - mn else 2
            cor = (cores[i] if cores else ("#5B3FC4" if ult else "#B9AEE8"))
            out.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{cor}"/>')
            out.append(f'<text x="{x + bw / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle" font-size="12" '
                       f'fill="#3D424A" font-weight="{700 if ult else 400}">{esc(fmt(v))}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle" font-size="12" fill="#5A6070">{esc(r)}</text>')
    out.append("</svg>")
    nota = f'<p class="nota">Eixo começa em {pc(mn, 0)} para mostrar melhor as diferenças.</p>' if mn > 0 else ""
    return f'<div class="{cls}">' + "".join(out) + "</div>" + nota


def serie_13(B: Base, tabela: dict, chave) -> tuple[list, list]:
    rot, val = [], []
    for m in B.u13:
        a = tabela[m].get(chave) if chave is not None else tabela[m]
        rot.append(mes_curto(m))
        val.append(a.p_pont if a and a.med >= 10 else None)
    return rot, val


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
    rot, val = serie_13(B, B.tot, None)
    corpo = f"""
<section class="hero">
<span class="kicker">Voos domésticos · {mes}</span>
<h1>Pontualidade dos voos no Brasil</h1>
<p class="lead">{lead}</p>
<div class="busca" role="search"><label for="busca" class="sr">Buscar voo, rota, aeroporto ou companhia</label>
<input id="busca" type="search" autocomplete="off" placeholder="Voo (LA 3300), rota (GRU SSA), cidade ou aeroporto"><div id="busca-res" aria-live="polite"></div></div>
</section>
{tiles_acc(T, T0)}
{mapa_card_home(B, aero_pag)}
{dem_card_home(B)}
<section class="card"><div class="card-head"><h2>Ranking das companhias em {mes}</h2><span class="small">Companhias com mais de {nf(MIN_CIA_RANK)} voos no mês</span></div>
{tab_cias}
<p class="nota">No horário = chegada até 30 minutos depois do previsto, mesmo critério da ANAC.</p></section>
<section class="card"><h2>Pontualidade mês a mês</h2>{svg_barras(rot, val, aria="Percentual de voos domésticos no horário nos últimos 13 meses")}</section>
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
{fim_card(fim)}
"""
    desc = (f"{cap(mes)}: {pc(T.p_pont)} dos voos domésticos chegaram no horário e {pc(T.p_canc)} foram cancelados. "
            "Ranking de companhias, aeroportos, rotas e voos com dados oficiais da ANAC.")
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": "Voo em Números", "url": BASE + "/",
               "inLanguage": "pt-BR"}
    return pagina(B, "/", f"Pontualidade dos voos no Brasil: {mes} | Voo em Números", desc, corpo, "/", jsonld=[site_ld])


def fim_card(fim) -> str:
    if not fim:
        return ""
    return (f'<section class="card dark"><h2>Vai viajar no fim do ano?</h2><p>Veja como foram a pontualidade e os cancelamentos, '
            f'dia a dia, no Natal e Ano-Novo de {fim["ano"]}, por companhia e por aeroporto.</p>'
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
    rot, val = serie_13(B, B.cia, c)
    # aeroportos da companhia
    aer = [(o, x) for (cc, o), x in B.cia_aero[B.ref].items() if cc == c and x.prev >= 100 and o in aero_pag]
    aer.sort(key=lambda t: t[1].p_pont or 0)
    linhas_aer = "".join(f'<tr><td><a href="/aeroportos/{B.aero_slug(o)}/">{esc(B.cod(o))}</a> <span class="small">{esc(B.aero_nome(o))}</span></td>'
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
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, aria=f"Percentual de voos da {nome} no horário nos últimos 13 meses")}</section>
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
    rot, val = serie_13(B, B.aero, o)
    # companhias
    cs = [(c, x) for (c, oo), x in B.cia_aero[B.ref].items() if oo == o and x.prev >= 10]
    cs.sort(key=lambda t: -t[1].prev)
    lin_c = "".join(f'<tr><td>{B.link_cia(c)}</td><td style="min-width:180px">{meter(x.p_pont)}</td>'
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
<p class="lead">Partidas de voos domésticos regulares. Em {base_txt}, <strong>{pc(a.p_pont)}</strong> chegaram no horário e <strong>{pc(a.p_canc)}</strong> foram cancelados.</p></section>
{tiles_acc(a, a0, "Partidas previstas")}
{dem_aero(B, o)}
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, aria=f"Percentual de partidas de {cod} no horário nos últimos 13 meses")}</section>
<section class="card"><div class="card-head"><h2>Por companhia em {mes}</h2></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Partidas</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Destinos a partir de {esc(cod)}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Destino</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_d}</tbody></table></div></section>
{f'<section class="card"><div class="card-head"><h2>Voos que mais atrasam saindo de {esc(cod)}</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Trecho</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio dos atrasados</th></tr></thead><tbody>{lin_v}</tbody></table></div></section>' if lin_v else ""}
{faq}"""
    return pagina(B, f"/aeroportos/{B.aero_slug(o)}/", f"Aeroporto {B.nome_cod(o)}: atrasos e cancelamentos | Voo em Números",
                  f"{cap(base_txt)}: {pc(a.p_pont)} das partidas de {cod} chegaram no horário e {pc(a.p_canc)} foram canceladas. Companhias, destinos e voos que mais atrasam.",
                  corpo, "/aeroportos/", migalhas=[("/aeroportos/", "Aeroportos"), ("", B.nome_cod(o))], jsonld=[ld])


def pg_rotas(B: Base, rota_pag) -> str:
    rs = sorted(rota_pag, key=lambda r: -B.soma(B.rota, r, B.u3).prev)
    lin = "".join(f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(o, d)}/">{esc(B.cod(o))} → {esc(B.cod(d))}</a> '
                  f'<span class="small">{esc(B.aero_nome(o))} → {esc(B.aero_nome(d))}</span></td>'
                  f'<td class="r num"><b>{pc(x.p_pont)}</b></td><td class="r num">{pc(x.p_canc)}</td><td class="r num">{nf(x.prev)}</td></tr>'
                  for (o, d), x in ((r, B.soma(B.rota, r, B.u3)) for r in rs[:200]))
    corpo = f"""<section class="hero"><h1>Rotas</h1>
<p class="lead">As 200 rotas domésticas com mais voos nos últimos 3 meses. Use a busca para achar qualquer uma das {nf(len(rota_pag))} rotas, ou entre pela página do aeroporto de origem.</p>
<div class="busca" role="search"><label for="busca" class="sr">Buscar rota</label><input id="busca" type="search" autocomplete="off" placeholder="Ex.: GRU SSA, Recife, Congonhas"><div id="busca-res" aria-live="polite"></div></div></section>
<section class="card"><div class="tw"><table><thead><tr><th scope="col">Rota</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Voos (3 meses)</th></tr></thead><tbody>{lin}</tbody></table></div></section>"""
    return pagina(B, "/rotas/", "Rotas aéreas no Brasil: atrasos e cancelamentos | Voo em Números",
                  "Pontualidade e cancelamentos das rotas domésticas com mais voos no Brasil, com dados oficiais da ANAC.",
                  corpo, "/rotas/", migalhas=[("", "Rotas")])


PERIODOS = [("Madrugada (0h–6h)", 0, 6), ("Manhã (6h–12h)", 6, 12), ("Tarde (12h–18h)", 12, 18), ("Noite (18h–24h)", 18, 24)]


def pg_rota(B: Base, o: str, d: str, rota_pag, voo_pag) -> str:
    co, cd = B.cod(o), B.cod(d)
    no, nd = B.aero_nome(o), B.aero_nome(d)
    a3 = B.soma(B.rota, (o, d), B.u3)
    am, am0 = B.rota[B.ref].get((o, d)), B.rota.get(B.ant, {}).get((o, d))
    mes = mes_nome(B.ref)
    usa_mes = am is not None and am.prev >= 30
    a, a0, base_txt = (am, am0, mes) if usa_mes else (a3, None, "últimos 3 meses")
    rot, val = serie_13(B, B.rota, (o, d))
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
    cores = ["#C2410C" if (v is not None and validos and v == min(validos)) else "#5B3FC4" for v in sem_val]
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
    faq, ld = faq_html(pares)
    volta = (d, o) in rota_pag
    corpo = f"""<section class="hero"><span class="kicker">Rota · voos diretos</span><h1>{esc(B.nome_cod(o))} → {esc(B.nome_cod(d))}</h1>
<p class="lead">Em {base_txt}, <strong>{pc(a.p_pont)}</strong> dos voos chegaram no horário e <strong>{pc(a.p_canc)}</strong> foram cancelados. {dur}</p>
<div class="btns">{f'<a class="btn sec" href="/rotas/{B.rota_slug(d, o)}/">Ver a volta: {esc(cd)} → {esc(co)}</a>' if volta else ""}{f'<a class="btn sec" href="/aeroportos/{B.aero_slug(o)}/">Aeroporto {esc(co)}</a>' if o in B.pag_aero else ""}{f'<a class="btn sec" href="/aeroportos/{B.aero_slug(d)}/">Aeroporto {esc(cd)}</a>' if d in B.pag_aero else ""}</div></section>
{tiles_acc(a, a0)}
{dem_rota(B, o, d)}
<section class="card"><div class="card-head"><h2>Por companhia nesta rota</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Atraso médio dos atrasados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Os voos desta rota, do mais ao menos pontual</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Companhia</th><th scope="col">Saída prevista</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio</th><th scope="col" class="r">Cancelados</th></tr></thead><tbody>{lin_v}</tbody></table></div>
<p class="nota">Atraso médio = média do atraso na chegada, contando todos os voos realizados (os que chegaram adiantados contam como zero).</p></section>
<div class="grid2">
<section class="card"><h2>Melhor horário para voar</h2>{per_html or '<p class="small">Poucos voos para comparar os horários.</p>'}<p class="nota">Pelo horário previsto de saída, últimos 3 meses.</p></section>
<section class="card"><h2>Por dia da semana</h2>{sem_html}</section>
</div>
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, aria=f"Percentual de voos {co}-{cd} no horário nos últimos 13 meses")}</section>
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/rotas/{B.rota_slug(o, d)}/", f"Voos {B.cidade(o)} ({co}) → {B.cidade(d)} ({cd}): atrasos e cancelamentos | Voo em Números",
                  f"{cap(base_txt)}: {pc(a.p_pont)} dos voos {co}–{cd} chegaram no horário e {pc(a.p_canc)} foram cancelados. Veja o voo e a companhia mais pontuais.",
                  corpo, "/rotas/", migalhas=[("/rotas/", "Rotas"), ("", f"{co} → {cd}")], jsonld=[ld])


def botao_ao_vivo(c: str, n: str) -> str:
    """Abre o voo em tempo real no Flightradar24 (só para companhias com código IATA conhecido)."""
    iata = CIAS.get(c, ("", "", ""))[1]
    if not iata or not n.isdigit():
        return ""
    return (f'<a class="btn" href="https://www.flightradar24.com/data/flights/{iata.lower()}{n}" target="_blank" '
            f'rel="noopener nofollow">Acompanhar o {iata} {n} agora ↗</a>')


def pg_voo(B: Base, k, trecho: str, voo_pag) -> str:
    c, n = k
    cod, cia = B.cod_voo(c, n), B.cia_nome(c)
    legs = sorted(B.voo_legs[k].items(), key=lambda t: -t[1].prev)
    a = Acc()
    for _, x in legs:
        a.soma(x)
    rot, val = serie_13(B, B.voo, k)
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
    pares = [(f"O voo {cod} costuma atrasar?",
              f"Nos últimos 3 meses, o {cod} da {cia} ({trecho}) chegou no horário em {pc(a.p_pont)} das vezes e foi cancelado em {pc(a.p_canc)} dos dias previstos."),
             (f"Quanto tempo atrasa o voo {cod}?",
              f"Quando atrasou mais de 30 minutos, o atraso médio na chegada foi de {min_txt(a.media_atr)}. "
              f"{pc(a.p_a60)} das viagens chegaram com mais de 1 hora de atraso.")]
    if pos and len(outros) > 1:
        lugar = ("o mais pontual" if pos == 1 else "o menos pontual" if pos == len(outros) else f"o {pos}º mais pontual")
        pares.append((f"O {cod} é um dos voos mais pontuais de {B.cod(o)} para {B.cod(d)}?",
                      f"Ele é {lugar} entre {len(outros)} voos diretos {B.cod(o)}–{B.cod(d)} com pelo menos 10 viagens nos últimos 3 meses."))
    faq, ld = faq_html(pares)
    corpo = f"""<section class="hero"><span class="kicker">Voo · {esc(cia)}</span><h1>Voo {esc(cod)}: {esc(trecho)}</h1>
<p class="lead">Nos últimos 3 meses, o {esc(cod)}{f" (saída prevista às {hora0})" if hora0 else ""} chegou no horário em <strong>{pc(a.p_pont)}</strong> das viagens e foi cancelado em <strong>{pc(a.p_canc)}</strong> dos dias previstos.</p>
<div class="btns">{botao_ao_vivo(c, n)}{B.link_rota(o, d, "Ver a rota " + esc(B.cod(o)) + " → " + esc(B.cod(d))).replace("<a ", '<a class="btn sec" ', 1) if (o, d) in B.pag_rotas else ""}</div></section>
<div class="tiles">{tile("Chegou no horário", pc(a.p_pont), "até 30 min de atraso")}{tile("Cancelado", pc(a.p_canc), f"{nf(a.canc)} de {nf(a.prev)} previstos")}{tile("Atraso médio quando atrasa", min_txt(a.media_atr), "atrasos acima de 30 min")}{tile("Atrasos acima de 1 hora", pc(a.p_a60), f"{nf(a.b[1] + a.b[2] + a.b[3])} viagens")}</div>
<section class="card"><div class="card-head"><h2>Trechos deste voo</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Trecho</th><th scope="col">Saída prevista</th><th scope="col">Avião</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelado</th><th scope="col" class="r">Previstos</th></tr></thead><tbody>{"".join(lin_l)}</tbody></table></div></section>
<div class="grid2">
<section class="card"><h2>Quanto ele atrasa</h2>{dist_html}<p class="nota">Atraso na chegada das {nf(a.med)} viagens realizadas nos últimos 3 meses.</p></section>
<section class="card"><div class="card-head"><h2>Outros voos {esc(B.cod(o))} → {esc(B.cod(d))}</h2><span class="small">Do mais ao menos pontual</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Companhia</th><th scope="col">Saída</th><th scope="col" class="r">No horário</th></tr></thead><tbody>{lin_o}</tbody></table></div></section>
</div>
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, aria=f"Percentual de viagens do voo {cod} no horário nos últimos 13 meses")}</section>
{aviso_direitos()}
{faq}"""
    return pagina(B, f"/voos/{B.voo_slug(c, n)}/", f"Voo {cod} ({cia}) {trecho}: atrasos e cancelamentos | Voo em Números",
                  f"Nos últimos 3 meses, o voo {cod} da {cia} ({trecho}) chegou no horário em {pc(a.p_pont)} das vezes e foi cancelado em {pc(a.p_canc)}.",
                  corpo, "/rotas/", migalhas=[("/companhias/" + B.cia_slug(c) + "/", cia), ("", f"Voo {cod}")], jsonld=[ld])


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
    cores = ["#C2410C" if v is not None and v <= corte else "#5B3FC4" for v in vals]
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
<p>O Voo em Números faz parte da Família em Números, um grupo de portais independentes que organizam dados públicos do Brasil. Não tem ligação com a ANAC nem com companhias aéreas. Encontrou um erro? Escreva para <a href="mailto:oleoemnumeros@gmail.com">oleoemnumeros@gmail.com</a>.</p>
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


def svg_barras_valor(rotulos, valores, fmt, aria="", altura=190, largura=720) -> str:
    n = len(valores)
    W, H, top, base = largura, altura, 22, altura - 26
    mx = max(valores) if valores else 1
    passo = (W - 20) / n
    bw = min(46, passo * 0.66)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">',
           f'<line x1="10" y1="{base}" x2="{W - 10}" y2="{base}" stroke="#C9C6D6"/>']
    for i, (r, v) in enumerate(zip(rotulos, valores)):
        x = 10 + i * passo + (passo - bw) / 2
        h = max(2, v / mx * (base - top))
        ult = i == n - 1
        out.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{"#5B3FC4" if ult else "#B9AEE8"}"/>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle" font-size="12" fill="#3D424A" font-weight="{700 if ult else 400}">{esc(fmt(v))}</text>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle" font-size="12" fill="#5A6070">{esc(r)}</text>')
    out.append("</svg>")
    return '<div class="chart">' + "".join(out) + "</div>"


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
        out.append(f'<line x1="{ml}" y1="{py(y):.1f}" x2="{W - mr}" y2="{py(y):.1f}" stroke="#EFEEF4"/>'
                   f'<text x="{ml - 8}" y="{py(y) + 4:.1f}" text-anchor="end" font-size="12" fill="#5A6070">{pc(y, 0)}</text>')
        y += 0.05
    for e, rot in ((3, "1 mil"), (4, "10 mil"), (5, "100 mil"), (6, "1 milhão")):
        if x0 <= e <= x1:
            out.append(f'<line x1="{px(e):.1f}" y1="{mt}" x2="{px(e):.1f}" y2="{H - mb}" stroke="#EFEEF4"/>'
                       f'<text x="{px(e):.1f}" y="{H - mb + 18}" text-anchor="middle" font-size="12" fill="#5A6070">{rot}</text>')
    out.append(f'<text x="{(ml + W - mr) / 2:.0f}" y="{H - 6}" text-anchor="middle" font-size="12" fill="#3D424A">Passageiros embarcados no mês (escala logarítmica)</text>')
    n = len(xs); mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx:
        b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
        a = my - b * mx
        out.append(f'<line x1="{px(x0):.1f}" y1="{py(a + b * x0):.1f}" x2="{px(x1):.1f}" y2="{py(a + b * x1):.1f}" stroke="#5B3FC4" stroke-width="1.5" stroke-dasharray="5 4"/>')
    rotulados = {p[0] for p in sorted(pts, key=lambda t: -t[1])[:8]} | {max(pts, key=lambda t: t[2])[0], min(pts, key=lambda t: t[2])[0]}
    for o, pax, pp in pts:
        cx, cy = px(math.log10(pax)), py(pp)
        nome = f"{B.cod(o)} · {B.aero_nome(o)}: {nf(pax)} passageiros, {pc(pp)} no horário"
        circ = f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#5B3FC4" fill-opacity=".72" stroke="#fff" stroke-width="1"><title>{esc(nome)}</title></circle>'
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
    rot = [mes_curto(m) for m in D.u13]
    graf_pax = svg_barras_valor(rot, [D.mensal[m].pax for m in D.u13], lambda v: nf(v / 1e6, 1),
                                aria="Passageiros pagos, em milhões, nos últimos 13 meses")
    graf_oc = svg_barras(rot, [D.mensal[m].ocup for m in D.u13], aria="Ocupação dos voos nos últimos 13 meses")
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
    rot, val = serie_13(B, B.tot, None)
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


# ---------------------------------------------------------------- principal
def cias_pag_pre(B: Base):
    return [c for c in {c for m in B.u12 for c in B.cia[m]} if B.soma(B.cia, c, B.u12).prev >= 300]


def escreve(caminho: str, conteudo: str):
    p = SAIDA / caminho.strip("/") / "index.html" if caminho.endswith("/") else SAIDA / caminho.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")


def main() -> int:
    B = Base(carrega())
    B.dem = Demanda(DEM_ARQ) if DEM_ARQ.exists() else None
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
    cias_rank = [c for c, x in B.cia[B.ref].items() if x.prev >= MIN_CIA_RANK]
    cias_rank.sort(key=lambda c: -(B.cia[B.ref][c].p_pont or 0))
    cias_pag = cias_pag_pre(B)
    cias_pag.sort(key=lambda c: -B.soma(B.cia, c, B.u12).prev)
    fim = periodo_fim(B)

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
    pub("/direitos/", pg_direitos(B), "0.9")
    pub("/mapa/", pg_mapa(B, aero_pag), "0.8")
    if B.dem:
        pub("/demanda/", pg_demanda(B, aero_pag, rota_pag), "0.8")
    pub("/sobre/", pg_sobre(B), "0.3")
    escreve("/404.html", pg_404(B))

    # busca
    idx = [["Seus direitos: voo atrasado ou cancelado, overbooking, bagagem", "guia", "/direitos/"],
           ["Mapa da pontualidade dos aeroportos do Brasil por estado", "mapa", "/mapa/"]]
    if B.dem:
        idx.append(["Passageiros e ocupação dos voos: aeroporto lotado atrasa mais", "demanda", "/demanda/"])
    for c in cias_pag:
        idx.append([B.cia_nome(c), "companhia", f"/companhias/{B.cia_slug(c)}/"])
    for a in sorted(aero_pag, key=lambda a: -B.soma(B.aero, a, B.u3).prev):
        idx.append([f"{B.cod(a)} {B.aero_nome(a)} {B.uf(a)}", "aeroporto", f"/aeroportos/{B.aero_slug(a)}/"])
    for o, d in sorted(rota_pag, key=lambda r: -B.soma(B.rota, r, B.u3).prev):
        idx.append([f"{B.cod(o)} → {B.cod(d)} {B.aero_nome(o)} → {B.aero_nome(d)}", "rota", f"/rotas/{B.rota_slug(o, d)}/"])
    for k in sorted(voo_pag, key=lambda k: -sum(x.prev for x in B.voo_legs[k].values())):
        idx.append([f"{B.cod_voo(*k)} {voo_pag[k]}", B.cia_nome(k[0]), f"/voos/{B.voo_slug(*k)}/"])
    (SAIDA / "busca.json").write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # arquivos fixos
    shutil.copy(SITE / "estilo.css", SAIDA / "assets" / "estilo.css")
    shutil.copy(SITE / "app.js", SAIDA / "assets" / "app.js")
    (SAIDA / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30"><rect x="1" y="1" width="28" height="28" rx="7" fill="#5B3FC4"/>'
        '<path d="M7 17.5 23 9.5l-3.2 9.3-4.3-2.6-2.9 3.8-.4-4.7z" fill="#fff"/><rect x="7" y="22" width="16" height="1.8" rx=".9" fill="#fff" opacity=".7"/></svg>',
        encoding="utf-8")
    gerar_imagens(B)
    hoje = B.gerado.strftime("%Y-%m-%d")
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{BASE}{u}</loc><lastmod>{hoje}</lastmod><priority>{p}</priority></url>" for u, p in urls]
    sm.append("</urlset>")
    (SAIDA / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    (SAIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n", encoding="utf-8")
    (SAIDA / "CNAME").write_text(DOMINIO + "\n", encoding="utf-8")
    print(f"Site gerado: {len(urls)} páginas ({len(aero_pag)} aeroportos, {len(rota_pag)} rotas, {len(voo_pag)} voos, "
          f"{len(cias_pag)} companhias). Dados até {B.ref}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
