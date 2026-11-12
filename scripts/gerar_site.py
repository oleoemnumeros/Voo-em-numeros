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


NAV = [("/", "Início"), ("/companhias/", "Companhias"), ("/aeroportos/", "Aeroportos"), ("/rotas/", "Rotas"),
       ("/fim-de-ano/", "Fim de ano"), ("/sobre/", "Como funciona")]
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
<span><a href="/companhias/">Companhias</a> · <a href="/aeroportos/">Aeroportos</a> · <a href="/rotas/">Rotas</a> · <a href="/fim-de-ano/">Fim de ano</a> · <a href="/sobre/">Como funciona</a></span>
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
    lin_c = "".join(f'<tr><td><a href="/companhias/{B.cia_slug(c)}/">{esc(B.cia_nome(c))}</a></td><td style="min-width:180px">{meter(x.p_pont)}</td>'
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
    lin_c = "".join(f'<tr><td><a href="/companhias/{B.cia_slug(c)}/">{esc(B.cia_nome(c))}</a></td><td style="min-width:180px">{meter(x.p_pont)}</td>'
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
<div class="btns">{f'<a class="btn sec" href="/rotas/{B.rota_slug(d, o)}/">Ver a volta: {esc(cd)} → {esc(co)}</a>' if volta else ""}<a class="btn sec" href="/aeroportos/{B.aero_slug(o)}/">Aeroporto {esc(co)}</a><a class="btn sec" href="/aeroportos/{B.aero_slug(d)}/">Aeroporto {esc(cd)}</a></div></section>
{tiles_acc(a, a0)}
<section class="card"><div class="card-head"><h2>Por companhia nesta rota</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Companhia</th><th scope="col">Chegaram no horário</th><th scope="col" class="r">Cancelados</th><th scope="col" class="r">Atraso médio dos atrasados</th><th scope="col" class="r">Voos</th></tr></thead><tbody>{lin_c}</tbody></table></div></section>
<section class="card"><div class="card-head"><h2>Os voos desta rota, do mais ao menos pontual</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Companhia</th><th scope="col">Saída prevista</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Atraso médio</th><th scope="col" class="r">Cancelados</th></tr></thead><tbody>{lin_v}</tbody></table></div>
<p class="nota">Atraso médio = média do atraso na chegada, contando todos os voos realizados (os que chegaram adiantados contam como zero).</p></section>
<div class="grid2">
<section class="card"><h2>Melhor horário para voar</h2>{per_html or '<p class="small">Poucos voos para comparar os horários.</p>'}<p class="nota">Pelo horário previsto de saída, últimos 3 meses.</p></section>
<section class="card"><h2>Por dia da semana</h2>{sem_html}</section>
</div>
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, aria=f"Percentual de voos {co}-{cd} no horário nos últimos 13 meses")}</section>
{faq}"""
    return pagina(B, f"/rotas/{B.rota_slug(o, d)}/", f"Voos {B.cidade(o)} ({co}) → {B.cidade(d)} ({cd}): atrasos e cancelamentos | Voo em Números",
                  f"{cap(base_txt)}: {pc(a.p_pont)} dos voos {co}–{cd} chegaram no horário e {pc(a.p_canc)} foram cancelados. Veja o voo e a companhia mais pontuais.",
                  corpo, "/rotas/", migalhas=[("/rotas/", "Rotas"), ("", f"{co} → {cd}")], jsonld=[ld])


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
        lin_l.append(f'<tr><td class="wrap"><a href="/rotas/{B.rota_slug(o, d)}/">{esc(B.cod(o))} → {esc(B.cod(d))}</a> '
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
<p class="lead">Nos últimos 3 meses, o {esc(cod)}{f" (saída prevista às {hora0})" if hora0 else ""} chegou no horário em <strong>{pc(a.p_pont)}</strong> das viagens e foi cancelado em <strong>{pc(a.p_canc)}</strong> dos dias previstos.</p></section>
<div class="tiles">{tile("Chegou no horário", pc(a.p_pont), "até 30 min de atraso")}{tile("Cancelado", pc(a.p_canc), f"{nf(a.canc)} de {nf(a.prev)} previstos")}{tile("Atraso médio quando atrasa", min_txt(a.media_atr), "atrasos acima de 30 min")}{tile("Atrasos acima de 1 hora", pc(a.p_a60), f"{nf(a.b[1] + a.b[2] + a.b[3])} viagens")}</div>
<section class="card"><div class="card-head"><h2>Trechos deste voo</h2><span class="small">Últimos 3 meses</span></div><div class="tw"><table><thead><tr><th scope="col">Trecho</th><th scope="col">Saída prevista</th><th scope="col">Avião</th><th scope="col" class="r">No horário</th><th scope="col" class="r">Cancelado</th><th scope="col" class="r">Previstos</th></tr></thead><tbody>{"".join(lin_l)}</tbody></table></div></section>
<div class="grid2">
<section class="card"><h2>Quanto ele atrasa</h2>{dist_html}<p class="nota">Atraso na chegada das {nf(a.med)} viagens realizadas nos últimos 3 meses.</p></section>
<section class="card"><div class="card-head"><h2>Outros voos {esc(B.cod(o))} → {esc(B.cod(d))}</h2><span class="small">Do mais ao menos pontual</span></div><div class="tw"><table><thead><tr><th scope="col">Voo</th><th scope="col">Companhia</th><th scope="col">Saída</th><th scope="col" class="r">No horário</th></tr></thead><tbody>{lin_o}</tbody></table></div></section>
</div>
<section class="card"><h2>Mês a mês</h2>{svg_barras(rot, val, aria=f"Percentual de viagens do voo {cod} no horário nos últimos 13 meses")}</section>
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
    tab_c = "".join(f'<tr><td><a href="/companhias/{B.cia_slug(c)}/">{esc(B.cia_nome(c))}</a></td><td style="min-width:180px">{meter(s[3] / s[2] if s[2] else None)}</td>'
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
def escreve(caminho: str, conteudo: str):
    p = SAIDA / caminho.strip("/") / "index.html" if caminho.endswith("/") else SAIDA / caminho.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(conteudo, encoding="utf-8")


def main() -> int:
    B = Base(carrega())
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
    cias_rank = [c for c, x in B.cia[B.ref].items() if x.prev >= MIN_CIA_RANK]
    cias_rank.sort(key=lambda c: -(B.cia[B.ref][c].p_pont or 0))
    cias_pag = [c for c in {c for m in B.u12 for c in B.cia[m]} if B.soma(B.cia, c, B.u12).prev >= 300]
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
    pub("/sobre/", pg_sobre(B), "0.3")
    escreve("/404.html", pg_404(B))

    # busca
    idx = []
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
