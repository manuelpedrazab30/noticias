"""Paso 5: digest diario de máximo 10 noticias, como página web (GitHub Pages).

Aquí se elige y resume; el diseño de la página está en page.py.

Uso:
    python digest.py             # escribe docs/index.html y docs/archivo/AAAA-MM-DD.html
    python digest.py --sin-ia    # sin resúmenes (no gasta cuota de la IA)
    python digest.py --desde-json docs/data/AAAA-MM-DD.json   # solo redibujar (diseño)

GitHub Actions lo ejecuta cada mañana (.github/workflows/digest.yml).
"""
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from cluster import group_stories
from medios import lean, short
from news import FEEDS, collect, blind_spot
from page import render
from summarize import choose, summarize

MAX_STORIES = 10
HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
TZ = ZoneInfo("Europe/Amsterdam")  # la fecha del digest es la de Maastricht

TOPIC_NAMES = {
    "geopolitica": "Geopolítica", "colombia": "Colombia", "tecnologia": "Tecnología",
    "economia": "Economía", "paises_bajos": "Países Bajos", "limburg": "Limburg",
}
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


def to_story(g, summary):
    """Grupo + resumen de la IA -> dict simple con lo que necesita la página.

    Es lo que se guarda en docs/data/AAAA-MM-DD.json, para poder redibujar la página
    (p. ej. tras un cambio de diseño) sin descargar feeds ni llamar a la IA.
    """
    summary = summary or {}
    sources = sorted(outlets(g), key=lambda m: lean(m)[0] or 0)
    notes = {m: next(s for s in g if s["source"] == m) for m in sources}
    # La foto más grande que traiga alguno de los medios.
    with_photo = [s for s in g if s.get("image")]
    best = max(with_photo, key=lambda s: s.get("image_width", 0), default=None)
    warning = blind_spot(sources) if len(sources) > 1 else ""
    return {
        "topic": topic_of(g),
        "title": summary.get("titular") or g[0]["title"],
        "resumen": summary.get("resumen", ""),
        "enfoques": summary.get("enfoques", ""),
        "blind": "izquierda" if "izquierda" in warning else "derecha" if warning else "",
        "image": best["image"] if best else None,
        "image_source": best["source"] if best else None,
        "outlets": [{"name": m, "label": short(m), "link": notes[m]["link"], "title": notes[m]["title"]}
                    for m in sources],
    }


def write_pages(day, stories):
    """Escribe docs/index.html (si es la edición más reciente) y docs/archivo/<día>.html."""
    os.makedirs(os.path.join(DOCS, "archivo"), exist_ok=True)
    archive = sorted({f[:-5] for f in os.listdir(os.path.join(DOCS, "archivo")) if f.endswith(".html")}
                     | {day}, reverse=True)
    page = render(day, stories, [d for d in archive if d != day])
    # La copia de archivo vive un nivel más abajo, así que sus enlaces suben con "../".
    with open(os.path.join(DOCS, "archivo", f"{day}.html"), "w", encoding="utf-8") as f:
        f.write(page.replace('href="archivo/', 'href="../archivo/'))
    if day == archive[0]:
        with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-ia", action="store_true", help="no pedir resúmenes a la IA")
    ap.add_argument("--desde-json", metavar="ARCHIVO",
                    help="solo redibujar una edición guardada (sin feeds ni IA)")
    args = ap.parse_args()

    if args.desde_json:
        with open(args.desde_json, encoding="utf-8") as f:
            saved = json.load(f)
        write_pages(saved["day"], saved["stories"])
        print(f"Redibujado {saved['day']}: {len(saved['stories'])} historias")
        return

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
    page_stories = [to_story(g, s) for g, s in zip(chosen, summaries)]
    os.makedirs(os.path.join(DOCS, "data"), exist_ok=True)
    with open(os.path.join(DOCS, "data", f"{day}.json"), "w", encoding="utf-8") as f:
        json.dump({"day": day, "ai": used, "stories": page_stories}, f, ensure_ascii=False, indent=1)
    write_pages(day, page_stories)

    print(f"Digest {day}: {len(chosen)} historias -> docs/index.html")
    for s in page_stories:
        n = len(s["outlets"])
        print(f"  [{TOPIC_NAMES[s['topic']]}, {n} medio{'s' if n > 1 else ''}] {s['title']}")


if __name__ == "__main__":
    main()
