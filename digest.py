"""Paso 5: digest diario de máximo 10 noticias, como página web (GitHub Pages).

Uso:
    python digest.py             # escribe docs/index.html y docs/archivo/AAAA-MM-DD.html
    python digest.py --sin-ia    # sin resúmenes (no gasta cuota de la IA)

GitHub Actions lo ejecuta cada mañana (.github/workflows/digest.yml).
"""
import argparse
import html
import os
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from cluster import group_stories
from medios import lean, short
from news import FEEDS, collect, blind_spot
from summarize import choose, summarize

MAX_STORIES = 10
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
TZ = ZoneInfo("Europe/Amsterdam")  # la fecha del digest es la de Maastricht

TOPIC_NAMES = {
    "geopolitica": "Geopolítica", "colombia": "Colombia", "tecnologia": "Tecnología",
    "economia": "Economía", "paises_bajos": "Países Bajos", "limburg": "Limburg",
}
SPECTRUM = ["izquierda", "centro-izq", "centro", "centro-der", "derecha"]

# Temas prioritarios: siempre tienen un lugar y son los primeros en llenar los huecos.
PRIORITY = ["geopolitica", "economia", "colombia"]
# Solo aparecen si ese día hay un evento importante (como máximo uno por tema).
ONLY_IMPORTANT = ["paises_bajos", "limburg"]
# Los demás temas (tecnología) solo entran si sobra espacio y los cubren varios medios.


def outlets(group):
    return {s["source"] for s in group}


def topic_of(group):
    """El tema que más se repite entre las notas del grupo."""
    return Counter(s["topic"] for s in group).most_common(1)[0][0]


def pick(groups, use_ai):
    """Elige hasta MAX_STORIES grupos según las prioridades de arriba.

    1) Cada tema prioritario tiene un lugar: su hecho con más medios o, si solo hay
       notas de un medio, la que la IA juzgue más relevante (sin IA: la más reciente).
    2) Países Bajos y Limburg: la IA mira sus titulares y solo entra uno si es
       realmente importante. Sin IA no entran, para no colar noticias menores.
    3) Los lugares que quedan se llenan solo con hechos cubiertos por varios medios:
       primero de temas prioritarios, luego el resto (tecnología). Puede haber menos de 10.
    """
    def in_topic(topic):
        return [g for g in groups if topic_of(g) == topic]  # ya ordenados: más medios, más reciente

    chosen, candidates = [], {}
    for topic in PRIORITY:
        shared = [g for g in in_topic(topic) if len(outlets(g)) > 1]
        if shared:
            chosen.append(shared[0])
        elif in_topic(topic):
            candidates[topic] = in_topic(topic)[:8]
    for topic in ONLY_IMPORTANT:
        if in_topic(topic):
            candidates[topic] = in_topic(topic)[:8]

    picks = {}
    if candidates and use_ai:
        # Indicar cuántos medios cubren cada hecho le da a la IA una pista de su peso.
        titles = {t: [g[0]["title"] + (f" ({len(outlets(g))} medios)" if len(outlets(g)) > 1 else "")
                      for g in c] for t, c in candidates.items()}
        result, used, errors = choose(titles, only_important=ONLY_IMPORTANT)
        for err in errors:
            print(f"(IA, elegir) {err}", file=sys.stderr)
        picks = result or {}
    for topic, cands in candidates.items():
        if topic in picks:
            if picks[topic] is not None:  # None = la IA dijo que hoy nada es importante
                chosen.append(cands[picks[topic]])
            else:
                print(f"{TOPIC_NAMES[topic]}: hoy nada importante, no entra.")
        elif topic in PRIORITY:
            chosen.append(cands[0])

    def is_chosen(g):
        return any(g is c for c in chosen)

    shared = [g for g in groups if len(outlets(g)) > 1 and topic_of(g) not in ONLY_IMPORTANT]
    fill = [g for g in shared if topic_of(g) in PRIORITY] + [g for g in shared if topic_of(g) not in PRIORITY]
    for g in fill:
        if len(chosen) >= MAX_STORIES:
            break
        if not is_chosen(g):
            chosen.append(g)

    # Orden final: temas prioritarios arriba; dentro de cada bloque, por importancia.
    rank = {id(g): i for i, g in enumerate(groups)}
    return sorted(chosen[:MAX_STORIES], key=lambda g: (topic_of(g) not in PRIORITY, rank[id(g)]))


def spectrum_bar(sources):
    """Cinco casillas de izquierda a derecha; se rellenan las que tienen algún medio."""
    present = {short(m).lstrip("~") for m in sources}
    cells = "".join(f'<span class="cell{" on" if name in present else ""}" title="{name}"></span>'
                    for name in SPECTRUM)
    return f'<div class="bar" aria-label="espectro de medios">{cells}</div>'


def render_story(g, summary):
    e = html.escape
    sources = sorted(outlets(g), key=lambda m: lean(m)[0] or 0)
    title = (summary or {}).get("titular") or g[0]["title"]
    parts = [f'<article><p class="topic">{TOPIC_NAMES[topic_of(g)]} · '
             f'{len(sources)} medio{"s" if len(sources) > 1 else ""}</p>',
             f"<h2>{e(title)}</h2>", spectrum_bar(sources)]
    warning = blind_spot(sources).strip()
    if len(sources) > 1 and warning:
        parts.append(f'<p class="warn">{e(warning)}</p>')
    if summary:
        parts.append(f"<p>{e(summary['resumen'])}</p>")
        if summary["enfoques"]:
            parts.append(f'<p class="angles"><b>Enfoques:</b> {e(summary["enfoques"])}</p>')
    parts.append("<ul>")
    for source in sources:
        note = next(s for s in g if s["source"] == source)
        parts.append(f'<li><span class="who">{e(source)} <i>{e(short(source))}</i></span> '
                     f'<a href="{e(note["link"])}">{e(note["title"])}</a></li>')
    parts.append("</ul></article>")
    return "\n".join(parts)


def render_page(day, stories, summaries, used, archive):
    e = html.escape
    body = "\n".join(render_story(g, s) for g, s in zip(stories, summaries))
    links = " · ".join(f'<a href="archivo/{d}.html">{d}</a>' for d in archive[:14])
    ai_note = f"Resúmenes: {e(used)}." if used else "Hoy sin resúmenes de IA."
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Noticias {day}</title>
<style>
  :root {{ --bg:#fafaf8; --fg:#1c1c1a; --muted:#6b6b66; --line:#e3e3de; --accent:#2d5b8a; --on:#2d5b8a; --warn:#9a5b00; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#161615; --fg:#ececea; --muted:#a3a39d; --line:#2e2e2b; --accent:#8fb6e0; --on:#8fb6e0; --warn:#e0a85a; }}
  }}
  body {{ background:var(--bg); color:var(--fg); font:17px/1.55 -apple-system, system-ui, sans-serif;
         max-width:680px; margin:0 auto; padding:24px 16px 64px; }}
  header p, .topic, footer {{ color:var(--muted); font-size:14px; }}
  h1 {{ font-size:26px; margin:0 0 4px; }}
  article {{ border-top:1px solid var(--line); padding:20px 0; }}
  h2 {{ font-size:20px; line-height:1.3; margin:4px 0 8px; }}
  .topic {{ margin:0; text-transform:uppercase; letter-spacing:.04em; font-size:12px; }}
  .bar {{ display:flex; gap:3px; margin:0 0 10px; }}
  .cell {{ width:28px; height:6px; border-radius:3px; background:var(--line); }}
  .cell.on {{ background:var(--on); }}
  .warn {{ color:var(--warn); font-size:14px; }}
  .angles {{ font-size:15px; }}
  ul {{ padding-left:18px; font-size:15px; }}
  li {{ margin:4px 0; }}
  .who {{ font-weight:600; }} .who i {{ font-weight:400; color:var(--muted); }}
  a {{ color:var(--accent); }}
</style>
</head>
<body>
<header>
  <h1>Noticias del {day}</h1>
  <p>{len(stories)} historias. La barra muestra qué parte del espectro político las cubre
  (izquierda → derecha, según AllSides y Media Bias/Fact Check). {ai_note}</p>
</header>
{body}
<footer><p>Días anteriores: {links or "—"}</p></footer>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-ia", action="store_true", help="no pedir resúmenes a la IA")
    args = ap.parse_args()

    stories, failed = collect(list(FEEDS), n=20, max_age_hours=36)
    for name, url, err in failed:
        print(f"Feed caído: {name} ({err})", file=sys.stderr)
    chosen = pick(group_stories(stories), use_ai=not args.sin_ia)

    summaries, used = [None] * len(chosen), None
    if not args.sin_ia:
        result, used, errors = summarize(chosen, short)
        for err in errors:
            print(f"(IA) {err}", file=sys.stderr)
        if result:
            summaries = result

    day = datetime.now(TZ).strftime("%Y-%m-%d")
    os.makedirs(os.path.join(DOCS, "archivo"), exist_ok=True)
    archive = sorted({f[:-5] for f in os.listdir(os.path.join(DOCS, "archivo")) if f.endswith(".html")}
                     | {day}, reverse=True)
    page = render_page(day, chosen, summaries, used, [d for d in archive if d != day])
    # La copia de archivo vive un nivel más abajo, así que sus enlaces suben con "../".
    archived = page.replace('href="archivo/', 'href="../archivo/')
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    with open(os.path.join(DOCS, "archivo", f"{day}.html"), "w", encoding="utf-8") as f:
        f.write(archived)

    print(f"Digest {day}: {len(chosen)} historias -> docs/index.html")
    for g, s in zip(chosen, summaries):
        n = len(outlets(g))
        print(f"  [{TOPIC_NAMES[topic_of(g)]}, {n} medio{'s' if n > 1 else ''}] "
              f"{(s or {}).get('titular') or g[0]['title']}")


if __name__ == "__main__":
    main()
