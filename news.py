"""Agregador de noticias: lee feeds RSS por tema y agrupa el mismo hecho entre medios.

Uso:
    pip install -r requirements.txt
    python news.py                    # noticias agrupadas de las últimas 36 h
    python news.py --topic colombia
    python news.py --por-medio        # vista anterior: titulares feed por feed
    python news.py --umbral 0.4       # agrupar de forma más estricta
    python news.py --ia               # con resúmenes de IA (claves en .env)
"""
import argparse
import html
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser

from cluster import group_stories
from medios import lean, short
from summarize import summarize

# Máximo de hechos que se mandan a la IA: suficiente para el digest y cuida el plan gratis.
AI_MAX_GROUPS = 10

# La orientación de cada medio está en medios.py (AllSides + Media Bias/Fact Check).
FEEDS = {
    "geopolitica": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("DW", "https://rss.dw.com/rdf/rss-en-all"),
        ("The Guardian World", "https://www.theguardian.com/world/rss"),
        # Contrapeso de centro-derecha. Washington Times bloquea los servidores de
        # GitHub (403) y el feed de noticias del Telegraph está congelado.
        ("Washington Examiner World", "https://www.washingtonexaminer.com/section/world/feed/"),
    ],
    "colombia": [
        ("El Tiempo", "https://www.eltiempo.com/rss/colombia.xml"),
        # El Espectador migró de plataforma (oct 2026) y su RSS ahora sale vacío;
        # La Silla Vacía lo reemplaza como voz independiente.
        ("La Silla Vacía", "https://www.lasillavacia.com/feed/"),
        # Sección "Nación": el feed general mezcla deportes y farándula.
        ("Semana", "https://www.semana.com/arc/outboundfeeds/rss/category/nacion/?outputType=xml"),
    ],
    "tecnologia": [
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ],
    "economia": [
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("The Guardian Business", "https://www.theguardian.com/business/rss"),
        ("Telegraph Business", "https://www.telegraph.co.uk/business/rss.xml"),
        # Economía colombiana; sin ellos la sección era solo británica.
        ("La República", "https://www.larepublica.co/rss/economia"),
        ("Portafolio", "https://www.portafolio.co/rss/economia.xml"),
    ],
    "paises_bajos": [
        # "binnenland" (nacional): el feed general también trae noticias del extranjero.
        ("NOS", "https://feeds.nos.nl/nosnieuwsbinnenland"),
        ("DutchNews", "https://www.dutchnews.nl/feed/"),
        ("NL Times", "https://nltimes.nl/rss"),
    ],
    "limburg": [
        # Diario regional: la mayoría de titulares son de Maastricht y Limburg.
        ("De Limburger", "https://www.limburger.nl/rss"),
    ],
}

# Varios feeds son secciones del mismo medio. Para contar cuántos medios
# cubren un hecho (y luego su orientación) importa el medio, no la sección.
OUTLET = {
    "BBC World": "BBC",
    "BBC Technology": "BBC",
    "BBC Business": "BBC",
    "The Guardian World": "The Guardian",
    "The Guardian Business": "The Guardian",
    "Washington Examiner World": "Washington Examiner",
    "Telegraph Business": "The Telegraph",
}

# Para feeds que mezclan secciones: solo se guardan notas cuya URL contenga una de estas rutas.
KEEP_SECTIONS = {
    "De Limburger": ("/regio/", "/economie/"),  # fuera deporte, opinión e internacional
}


def fetch(url):
    """Devuelve (entries, error). No lanza excepciones: un feed caído no debe tumbar el resto."""
    try:
        parsed = feedparser.parse(url, agent="Mozilla/5.0 (news-aggregator personal project)")
    except Exception as e:  # noqa: BLE001
        return [], f"{type(e).__name__}: {e}"
    if parsed.get("status", 200) >= 400:
        return [], f"HTTP {parsed.status}"
    if not parsed.entries:
        reason = getattr(parsed, "bozo_exception", "sin entradas")
        return [], str(reason)
    return parsed.entries, None


def clean(text):
    """Quita etiquetas HTML y espacios de sobra de un resumen RSS."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return " ".join(text.split())


def published(entry):
    """Fecha de publicación como datetime en UTC, o None si el feed no la trae."""
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*t[:6], tzinfo=timezone.utc) if t else None


def image(entry):
    """(url, ancho) de la foto que trae el feed, o (None, 0).

    Prefiere tamaños medianos: las miniaturas se ven borrosas y los originales
    enormes (algunos de 6.000 px) harían lenta la página.
    """
    found = []
    for m in entry.get("media_content", []) + entry.get("media_thumbnail", []) + entry.get("enclosures", []):
        url = m.get("url") or m.get("href")
        kind = m.get("type") or m.get("medium") or "image"
        if not url or not kind.startswith("image"):
            continue
        width = int(m.get("width") or 0)
        if "/ace/standard/240/" in url:  # la BBC sirve el mismo archivo en tamaños fijos
            url, width = url.replace("/ace/standard/240/", "/ace/standard/976/"), 976
        found.append((width, url))
    good = [f for f in found if 400 <= f[0] <= 2000]
    if good:
        return max(good)[::-1]
    unknown = [f for f in found if f[0] == 0]  # sin ancho declarado: mejor eso que nada
    return (unknown[0][1], 0) if unknown else (None, 0)


def collect(topics, n, max_age_hours):
    """Descarga todos los feeds y devuelve (noticias, feeds_fallidos).

    Cada noticia es un dict plano: así el resto del programa no depende de feedparser.
    """
    jobs = [(topic, name, url) for topic in topics for name, url in FEEDS[topic]]
    # Descargar en paralelo: casi todo el tiempo se va esperando la red,
    # así que 16 feeds a la vez tardan lo mismo que el más lento.
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = pool.map(lambda job: fetch(job[2]), jobs)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stories, failed = [], []
    seen = set()
    for (topic, name, url), (entries, err) in zip(jobs, results):
        if err:
            failed.append((name, url, err))
            continue
        source = OUTLET.get(name, name)
        # Algunos feeds (p. ej. el Telegraph) no vienen ordenados por fecha:
        # primero quitamos lo viejo, luego ordenamos y solo entonces cortamos a n.
        keep = KEEP_SECTIONS.get(name)
        if keep:
            entries = [e for e in entries if any(p in e.get("link", "") for p in keep)]
        dated = [(published(e), e) for e in entries]
        dated = [(d, e) for d, e in dated if not d or d >= cutoff]
        dated.sort(key=lambda de: de[0] or cutoff, reverse=True)
        for date, e in dated[:n]:
            title = clean(e.get("title")) or "(sin título)"
            # La misma nota publicada en dos secciones del mismo medio cuenta una vez.
            if (source, title.lower()) in seen:
                continue
            seen.add((source, title.lower()))
            image_url, image_width = image(e)
            stories.append({
                "topic": topic,
                "source": source,
                "feed": name,
                "title": title,
                "summary": clean(e.get("summary"))[:400],
                "link": e.get("link", ""),
                "published": date,
                "image": image_url,
                "image_width": image_width,
            })
    return stories, failed


def print_by_source(stories):
    current = None
    for s in stories:
        if s["feed"] != current:
            current = s["feed"]
            print(f"\n[{current}] ({s['topic']})")
        print(f"  - {s['title']}\n    {s['link']}")


def blind_spot(sources):
    """Aviso si un hecho solo lo cubren medios de un mismo lado del espectro."""
    scores = [lean(s)[0] for s in sources]
    if None in scores:
        return ""
    if all(x <= -0.5 for x in scores):
        return "  ⚠ punto ciego: solo lo cubren medios de izquierda / centro-izq"
    if all(x >= 0.5 for x in scores):
        return "  ⚠ punto ciego: solo lo cubren medios de derecha / centro-der"
    return ""


def print_groups(groups, use_ai=False):
    shared = [g for g in groups if len({s["source"] for s in g}) > 1]
    summaries = [None] * len(shared)
    if use_ai and shared:
        result, used, errors = summarize(shared[:AI_MAX_GROUPS], short)
        for err in errors:
            print(f"(IA) {err}", file=sys.stderr)
        if result:
            summaries[:len(result)] = result
            print(f"Resúmenes hechos con {used}\n")
    print(f"{len(shared)} hechos cubiertos por más de un medio:\n")
    for g, summary in zip(shared, summaries):
        # Ordenar de izquierda a derecha deja ver de un vistazo el espectro.
        sources = sorted({s["source"] for s in g}, key=lambda m: lean(m)[0] or 0)
        print(f"● {g[0]['title']}")
        print(f"  {len(sources)} medios: " + ", ".join(f"{m} ({short(m)})" for m in sources))
        warning = blind_spot(sources)
        if warning:
            print(warning)
        if summary:
            print(f"  Resumen: {summary['resumen']}")
            if summary["enfoques"]:
                print(f"  Enfoques: {summary['enfoques']}")
        # Un titular por medio basta para comparar enfoques; el resto se cuenta.
        for source in sources:
            notes = [s for s in g if s["source"] == source]
            more = len(notes) - 1
            extra = f"  (+{more} nota{'s' if more > 1 else ''} más)" if more else ""
            print(f"    - [{source}] {notes[0]['title']}{extra}\n      {notes[0]['link']}")
        print()

    singles = [g[0] for g in groups if len({s["source"] for s in g}) == 1]
    print(f"--- {len(singles)} noticias de un solo medio ---")
    for s in singles:
        print(f"  - [{s['source']} · {short(s['source'])}] {s['title']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="noticias a leer por feed")
    ap.add_argument("--topic", choices=FEEDS.keys(), help="solo un tema")
    ap.add_argument("--horas", type=int, default=36, help="ignorar noticias más viejas")
    ap.add_argument("--umbral", type=float, default=0.3,
                    help="similitud mínima (0-1) para considerar dos noticias el mismo hecho")
    ap.add_argument("--por-medio", action="store_true", help="no agrupar; listar por feed")
    ap.add_argument("--ia", action="store_true", help="resumir cada hecho con Gemini/Groq")
    args = ap.parse_args()

    topics = [args.topic] if args.topic else list(FEEDS)
    stories, failed = collect(topics, args.n, args.horas)

    print(f"Noticias — {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC "
          f"({len(stories)} noticias de las últimas {args.horas} h)\n")
    if args.por_medio:
        print_by_source(stories)
    else:
        print_groups(group_stories(stories, args.umbral), use_ai=args.ia)

    if failed:
        print("\n--- Feeds que fallaron (revisar URL) ---", file=sys.stderr)
        for name, url, err in failed:
            print(f"  {name}: {err}\n    {url}", file=sys.stderr)


if __name__ == "__main__":
    main()
