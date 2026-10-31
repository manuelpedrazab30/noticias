"""Paso 2: agrupar noticias del mismo hecho publicadas por distintos medios.

Idea: convertimos cada noticia (título + resumen) en un "vector" de palabras con
pesos TF-IDF y medimos qué tan parecidas son con la similitud coseno (0 = nada
en común, 1 = idénticas). Si dos noticias de medios distintos pasan el umbral,
las juntamos en el mismo grupo.

Limitación: compara palabras, así que no une la misma noticia en idiomas
distintos (NOS en neerlandés vs. NL Times en inglés).
"""
import math
import re
import unicodedata
from collections import Counter

# Palabras tan comunes que no ayudan a distinguir un hecho de otro.
STOPWORDS = set("""
the a an and or but of to in on at for from by with as is are was were be been
has have had it its this that these those after over into about than says said
new will would could can not who what why how more most up out his her their they
el la los las un una unos unas y o de del al en con por para que se su sus es son
fue ser como mas pero sobre tras entre este esta estos estas lo le les ya muy
de het een en of van in op te met voor door naar bij aan om uit is zijn was er
die dat deze dit niet ook als nog wel maar dan zo
""".split())


def tokens(text):
    """Texto -> lista de "raíces" de palabras comparables."""
    # Quitar tildes: "Petró" y "Petro" deben contar como la misma palabra.
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    words = re.findall(r"[a-z0-9]+", text)
    # Cortar a 6 letras es un "stemming" casero: ukraine/ukrainian -> ukrain.
    return [w[:6] for w in words if len(w) > 2 and w not in STOPWORDS]


def tfidf_vectors(docs):
    """Lista de listas de tokens -> lista de dicts {token: peso}.

    TF  = cuántas veces aparece la palabra en esta noticia.
    IDF = log(total de noticias / noticias que la contienen): una palabra que
          sale en todas (p. ej. "gobierno") pesa poco; una rara pesa mucho.
    """
    df = Counter()
    for doc in docs:
        df.update(set(doc))
    n = len(docs)
    vectors = []
    for doc in docs:
        tf = Counter(doc)
        vec = {w: c * math.log(n / df[w]) for w, c in tf.items()}
        # Normalizar a longitud 1 deja el coseno como un simple producto punto.
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({w: v / norm for w, v in vec.items()})
    return vectors


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(w, 0.0) for w, v in a.items())


def group_stories(stories, threshold=0.3):
    """Devuelve una lista de grupos (listas de noticias), los más cubiertos primero.

    Cada noticia es un dict con al menos "source", "title" y "summary".
    """
    # El título se repite para que pese el doble que el resumen.
    docs = [tokens(f"{s['title']} {s['title']} {s['summary']}") for s in stories]
    vecs = tfidf_vectors(docs)

    # Union-find: cada noticia empieza en su propio grupo; al encontrar una
    # pareja parecida, unimos sus grupos.
    parent = list(range(len(stories)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(stories)):
        for j in range(i + 1, len(stories)):
            # Un medio no suele repetir el mismo hecho; comparar solo entre
            # medios distintos evita juntar notas parecidas de una misma sección.
            if stories[i]["source"] == stories[j]["source"]:
                continue
            if cosine(vecs[i], vecs[j]) >= threshold:
                parent[find(i)] = find(j)

    groups = {}
    for i, s in enumerate(stories):
        groups.setdefault(find(i), []).append(s)

    # Más medios distintos = hecho más relevante; desempata la más reciente.
    def key(g):
        newest = max((s["published"] for s in g if s["published"]), default=None)
        return (len({s["source"] for s in g}), newest.timestamp() if newest else 0)

    return sorted(groups.values(), key=key, reverse=True)
