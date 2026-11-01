"""Diseño de la página del digest ("Unbiased"): estilo diario de calidad, tema oscuro.

Solo dibuja: recibe historias ya elegidas y resumidas (dicts simples, ver digest.to_story)
y devuelve el HTML. No descarga nada ni llama a la IA, así que se puede rediseñar
sin gastar cuota: python digest.py --desde-json docs/data/AAAA-MM-DD.json
"""
import html
from datetime import date

from medios import MEDIOS

NAME = "Unbiased"
REPO = "https://github.com/manuelpedrazab30/noticias#readme"

TOPIC_NAMES = {
    "geopolitica": "Geopolítica", "economia": "Economía", "colombia": "Colombia",
    "tecnologia": "Tecnología", "paises_bajos": "Países Bajos", "limburg": "Maastricht",
}
SPECTRUM = ["izquierda", "centro-izq", "centro", "centro-der", "derecha"]
# Etiquetas cortas para la línea de medios, en versalitas.
SHORT = {"izquierda": "izq.", "centro-izq": "c.-izq.", "centro": "centro",
         "centro-der": "c.-der.", "derecha": "der.", "sin dato": "s/d"}
DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre"]

e = html.escape


def long_date(day):
    d = date.fromisoformat(day)
    return f"{DAYS[d.weekday()]} {d.day} de {MONTHS[d.month - 1]} de {d.year}"


def is_colombian(story):
    return all(MEDIOS.get(o["name"], {}).get("pais") == "Colombia" for o in story["outlets"])


def layout(stories):
    """Reparte las historias en las zonas de la página, sin cambiar cuáles entran.

    lead: la cubierta por más medios. mid: las 3 siguientes (incluye la principal de
    Colombia). Tarjetas: el resto de Colombia y, si hubo algo importante, Países Bajos.
    features: lo que queda, primero las que tienen foto.
    """
    lead = max(stories, key=lambda s: len(s["outlets"]))  # max() se queda con la primera si empatan
    rest = [s for s in stories if s is not lead]
    nl = [s for s in rest if s["topic"] in ("paises_bajos", "limburg")]
    rest = [s for s in rest if s not in nl]
    colombian = [s for s in rest if is_colombian(s)]
    co_card = colombian[1:]  # la mejor historia colombiana va al cuerpo de la página
    rest = [s for s in rest if s not in co_card]
    mid = rest[:3]
    if colombian and colombian[0] not in mid:
        mid = rest[:2] + [colombian[0]]
    features = [s for s in rest if s not in mid]
    features.sort(key=lambda s: not s["image"])  # sort es estable: con foto primero, sin perder el orden
    return lead, mid, co_card, nl, features


def meter(story):
    present = {o["label"].lstrip("~") for o in story["outlets"]}
    cells = "".join(f'<i class="on"></i>' if name in present else "<i></i>" for name in SPECTRUM)
    return f'<span class="meter" title="Orientación de los medios, de izquierda a derecha">{cells}</span>'


def sources(story):
    names = " · ".join(f'<a href="{e(o["link"])}">{e(o["name"])}</a>, '
                       f'{"~" if o["label"].startswith("~") else ""}{SHORT[o["label"].lstrip("~")]}'
                       for o in story["outlets"])
    blind = f'<span class="blind">Punto ciego · solo {e(story["blind"])}</span>' if story["blind"] else ""
    return f'<div class="sources">{meter(story)}{names}</div>{blind}'


def eyebrow(story):
    n = len(story["outlets"])
    return (f'<p class="eyebrow">{TOPIC_NAMES[story["topic"]]} '
            f'<small>· {n} medio{"s" if n > 1 else ""}</small></p>')


def photo(story, lazy=True):
    if not story["image"]:
        return ""
    load = 'loading="lazy"' if lazy else 'fetchpriority="high"'
    return (f'<img src="{e(story["image"])}" alt="" referrerpolicy="no-referrer" {load}>'
            f'<p class="credit">Foto: {e(story["image_source"])}</p>')


def text(story, angles=True):
    out = f'<p>{e(story["resumen"])}</p>' if story["resumen"] else ""
    if angles and story["enfoques"]:
        out += f'<p class="angles">{e(story["enfoques"])}</p>'
    return out


class Anchors:
    """Da un id a la primera historia de cada tema, para la fila de secciones."""

    def __init__(self):
        self.seen = []

    def __call__(self, story):
        if story["topic"] in self.seen:
            return ""
        self.seen.append(story["topic"])
        return f' id="t-{story["topic"]}"'


def render(day, stories, archive):
    anchor = Anchors()
    lead, mid, co_card, nl, features = layout(stories)

    parts = [f'<article class="lead"{anchor(lead)}>{eyebrow(lead)}'
             f'<h2 class="h-display">{e(lead["title"])}</h2>{photo(lead, lazy=False)}'
             f'<div class="summary">{text(lead)}</div>{sources(lead)}</article>']

    sizes = ["h-lg", "h-md", "h-sm"]
    mid_html = "".join(
        f'<article class="story"{anchor(s)}>{photo(s) if i < 2 else ""}{eyebrow(s)}'
        f'<h3 class="{sizes[i]}">{e(s["title"])}</h3>{text(s, angles=i == 0)}{sources(s)}</article>'
        for i, s in enumerate(mid))
    if mid_html:
        parts.append(f'<section class="mid">{mid_html}</section>')

    def card(css, title, items):
        body = "".join(
            f'<div class="item"{anchor(s)}>'
            f'{eyebrow(s) if s["topic"] not in ("colombia", "paises_bajos", "limburg") else ""}'
            f'<h4 class="h-sm">{e(s["title"])}</h4>{sources(s)}</div>' for s in items)
        return f'<section class="card {css}"><h3>{title}</h3>{body}</section>'

    cards = (card("co", "Colombia", co_card) if co_card else "") + \
            (card("nl", "Países Bajos y Maastricht", nl) if nl else "")
    if cards:
        parts.append(f"<aside>{cards}</aside>")

    feature_html = "".join(
        f'<article{anchor(s)}>{photo(s)}{eyebrow(s)}<h4 class="h-sm">{e(s["title"])}</h4>{sources(s)}</article>'
        for s in features)
    if feature_html:
        feature_html = f'<p class="eyebrow row-title">También hoy</p><div class="features">{feature_html}</div>'

    nav = '<span>|</span>'.join(f'<a href="#t-{t}">{name}</a>' for t, name in TOPIC_NAMES.items()
                                if t in anchor.seen)
    editions = " · ".join(f'<a href="archivo/{d}.html">{d}</a>' for d in archive[:14]) or "—"
    columns = len(parts)  # 1 a 3 columnas según lo que haya hoy

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{NAME} — {long_date(day)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,700;1,8..60,400;1,8..60,700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="utility"><div class="wrap">
  <span>Edición de la mañana · {long_date(day)}</span>
  <nav><a href="#archivo">Ediciones anteriores</a><a href="{REPO}">Cómo funciona</a></nav>
</div></div>
<div class="wrap">
  <header>
    <div class="masthead"><h1 class="wordmark">{NAME}</h1></div>
    <nav class="sections">{nav}</nav>
  </header>
  <main>
    <div class="grid cols-{columns}">{"".join(parts)}</div>
    {feature_html}
  </main>
  <footer id="archivo">
    <p>Orientación: AllSides y Media Bias/Fact Check · ~ = estimación propia</p>
    <p>Ediciones anteriores: {editions}</p>
  </footer>
</div>
</body>
</html>
"""


# Copiado del boceto aprobado (boceto/primera-plana-v2.html). Es texto normal, no un
# f-string, para no tener que duplicar cada llave { } del CSS.
CSS = """
  /* Tema oscuro: "papel" casi negro y cálido, "tinta" color hueso. */
  :root {
    color-scheme: dark;
    --yellow: #ffc500;   /* único color: solo marca los puntos ciegos */
    --ink: #ece8df;
    --cream: #121110;
    --white: #1b1a18;    /* superficie de la barra superior */
    --panel: #26241f;
    --rule: #3a3833;
    --caption: #a8a399;
    --mute: #77736b;
    --serif: "Source Serif 4", "Source Serif Pro", Georgia, serif;
    --sans: "Helvetica Neue", Helvetica, Arial, sans-serif;
  }
  * { box-sizing: border-box; }
  html, body { background: var(--cream); }
  body { margin: 0; color: var(--ink); font: 16px/1.38 var(--serif); letter-spacing: .01em; }
  a { color: inherit; text-decoration: none; }
  a:hover { text-decoration: underline; text-underline-offset: 3px; }
  .wrap { max-width: 1200px; margin: 0 auto; padding: 0 24px; }

  .utility { background: var(--white); border-bottom: 1px solid var(--rule); }
  .utility .wrap { display: flex; justify-content: space-between; gap: 12px; padding-top: 8px; padding-bottom: 8px;
                   font: 700 13px/1.25 var(--sans); letter-spacing: .01em; text-transform: uppercase; }
  .utility nav { display: flex; gap: 16px; }

  .masthead { padding: 22px 0 16px; }
  .wordmark { margin: 0; font-weight: 700; font-style: italic; font-size: 52px; line-height: 1; letter-spacing: -.02em; text-align: center; }
  .sections { border-top: 1px solid var(--ink); border-bottom: 1px solid var(--ink); padding: 8px 0;
              text-align: center; font-size: 13px; letter-spacing: .075em; text-transform: uppercase; }
  .sections span { color: var(--mute); padding: 0 10px; }

  .eyebrow { margin: 0 0 6px; font-size: 13px; font-weight: 700; letter-spacing: .075em; text-transform: uppercase; }
  .eyebrow small { font-weight: 400; color: var(--caption); letter-spacing: .05em; }
  h2, h3, h4 { margin: 0 0 8px; font-weight: 400; text-wrap: balance; overflow-wrap: break-word; }
  .h-display { font-size: clamp(40px, 5.4vw, 64px); line-height: 1.02; letter-spacing: -.02em; }
  .h-lg { font-size: 28px; line-height: 1.2;  letter-spacing: -.02em; }
  .h-md { font-size: 24px; line-height: 1.2;  letter-spacing: -.02em; }
  .h-sm { font-size: 20px; line-height: 1.25; letter-spacing: -.02em; }
  p { margin: 0 0 8px; }
  .angles { font-style: italic; font-size: 15px; }
  img { display: block; width: 100%; height: auto; object-fit: cover; background: var(--panel); filter: brightness(.9); }
  .credit { font-size: 12px; color: var(--mute); margin: 4px 0 10px; }

  .sources { font-size: 13px; line-height: 1.45; color: var(--caption); font-variant: small-caps; letter-spacing: .05em;
             border-top: 1px solid var(--rule); padding-top: 6px; margin-top: 10px; }
  /* Medidor de sesgo: barra de 5 tramos, de izquierda a derecha; claros los lados que cubren la historia */
  .meter { display: flex; align-items: center; margin: 2px 0 6px;
           font: 700 11px/1 var(--sans); letter-spacing: .06em; text-transform: uppercase; color: var(--caption); }
  .meter::before { content: "Izq"; margin-right: 6px; }
  .meter::after { content: "Der"; margin-left: 6px; }
  .meter i { width: 28px; height: 9px; background: var(--rule); }
  .meter i + i { box-shadow: inset 2px 0 0 var(--cream); }
  .meter i.on { background: var(--ink); }
  .lead .meter i { width: 40px; height: 12px; }
  /* El único amarillo de la página: lo que de verdad importa para leer con criterio. */
  .blind { display: inline-block; margin-top: 6px; padding: 1px 6px; background: var(--yellow);
           font: 700 12px/1.4 var(--sans); letter-spacing: .02em; text-transform: uppercase; color: #000; }

  .grid { display: grid; grid-template-columns: 1.55fr 1fr 300px; padding: 24px 0 8px; }
  .grid.cols-2 { grid-template-columns: 1.55fr 1fr; }
  .grid.cols-1 { grid-template-columns: 1fr; }
  .grid > * { padding: 0 20px; }
  .grid > *:first-child { padding-left: 0; }
  .grid > *:last-child { padding-right: 0; }
  .grid > * + * { border-left: 1px solid var(--rule); }
  .story { padding-bottom: 16px; margin-bottom: 16px; border-bottom: 1px solid var(--rule); }
  .story:last-child { border-bottom: 0; margin-bottom: 0; padding-bottom: 0; }
  .lead img { aspect-ratio: 3 / 2; margin-top: 12px; }
  .lead .summary { font-size: 18px; line-height: 1.44; }
  .mid img { aspect-ratio: 16 / 10; margin-bottom: 4px; }

  .card { margin-bottom: 20px; }
  .card h3 { margin: 0; padding: 8px 12px; font-size: 13px; font-weight: 700; letter-spacing: .075em; text-transform: uppercase; }
  .card .item { padding: 12px; border-bottom: 1px solid var(--rule); }
  .card .item:last-of-type { border-bottom: 0; }
  .card .sources { border-top: 0; padding-top: 0; margin-top: 4px; }
  /* Colombia: amarillo (mitad), azul y rojo */
  .card.co { background: #1f1c10; }
  .card.co h3 { background: #003893; color: #fff; border-top: 10px solid #fcd116; border-bottom: 5px solid #ce1126; }
  /* Países Bajos: rojo, blanco y azul en franjas iguales */
  .card.nl { background: #151923; }
  .card.nl h3 { background: #fff; color: #21468b; border-top: 7px solid #ae1c28; border-bottom: 7px solid #21468b; }

  .row-title { border-top: 1px solid var(--ink); padding-top: 8px; margin-top: 40px; }
  .features { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 12px 0 0; }
  .features img { aspect-ratio: 4 / 3; border-radius: 8px; margin-bottom: 10px; }

  footer { border-top: 1px solid var(--rule); margin-top: 56px; padding: 16px 0 40px;
           font-size: 13px; color: var(--caption); letter-spacing: .05em; }
  footer a { text-decoration: underline; text-underline-offset: 2px; }

  /* Celular: una columna, titulares igual de grandes */
  @media (max-width: 860px) {
    .wrap { padding: 0 16px; }
    .masthead { padding: 16px 0 12px; }
    .wordmark { font-size: 44px; }
    .sections { overflow-x: auto; white-space: nowrap; text-align: left; }
    .grid, .grid.cols-2, .features { grid-template-columns: 1fr; }
    .grid > * { padding: 0; }
    .grid > * + * { border-left: 0; border-top: 1px solid var(--rule); padding-top: 16px; margin-top: 16px; }
    .h-display { font-size: 40px; }
    .utility .wrap { font-size: 12px; }
    .utility nav { display: none; }
  }
"""
