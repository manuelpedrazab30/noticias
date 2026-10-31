"""Paso 3: tabla propia con la orientación de cada medio.

Fuentes (consultadas el 31 oct 2026):
  - AllSides: https://www.allsides.com/media-bias/ratings  (solo puntúa sesgo)
  - Media Bias/Fact Check (MBFC): https://mediabiasfactcheck.com  (sesgo + rigor factual)

Ambas son evaluaciones subjetivas hechas desde EE. UU.; "centro" para ellas no
significa lo mismo que en Colombia o Países Bajos. Por eso guardamos las dos
calificaciones originales y la puntuación final es solo su promedio.

Escala común, de -2 a +2:
    -2 izquierda   -1 centro-izquierda   0 centro   +1 centro-derecha   +2 derecha

Uso:
    python medios.py        # imprime la tabla
"""

# Traducción de cada etiqueta externa a la escala común.
ALLSIDES = {"Left": -2, "Lean Left": -1, "Center": 0, "Lean Right": 1, "Right": 2}
MBFC = {"Left": -2, "Left-Center": -1, "Least Biased": 0, "Right-Center": 1, "Right": 2}

# None = ese sitio no califica al medio. "propia" solo se usa cuando no hay
# ninguna calificación externa, y se marca como estimación en la salida.
MEDIOS = {
    "BBC": {
        "pais": "Reino Unido", "allsides": "Center", "mbfc": "Least Biased",
        "factual": "Mostly Factual",
    },
    "Al Jazeera": {
        "pais": "Catar", "allsides": "Lean Left", "mbfc": "Left-Center",
        "factual": "Mixed",
        "nota": "Financiado por el Estado de Catar.",
    },
    "DW": {
        "pais": "Alemania", "allsides": "Center", "mbfc": "Left-Center",
        "factual": "High",
        "nota": "Emisora pública internacional alemana.",
    },
    "The Guardian": {
        "pais": "Reino Unido", "allsides": "Left", "mbfc": "Left-Center",
        "factual": "High",
    },
    "Washington Times": {
        "pais": "EE. UU.", "allsides": "Lean Right", "mbfc": "Right-Center",
        "factual": "Mixed",
    },
    "The Telegraph": {
        "pais": "Reino Unido", "allsides": "Center", "mbfc": "Right",
        "factual": "Mixed",
        "nota": "AllSides lo pasó de Lean Right a Center en jun 2026; MBFC no actualiza desde dic 2024.",
    },
    "Ars Technica": {
        "pais": "EE. UU.", "allsides": "Center", "mbfc": "Least Biased",
        "factual": "High",
    },
    "TechCrunch": {
        "pais": "EE. UU.", "allsides": "Center", "mbfc": "Left-Center",
        "factual": "High",
    },
    "NOS": {
        "pais": "Países Bajos", "allsides": None, "mbfc": "Right-Center",
        "factual": "High",
        "nota": "MBFC aclara que con criterios de EE. UU. sería 'Least Biased'.",
    },
    "DutchNews": {
        "pais": "Países Bajos", "allsides": None, "mbfc": "Least Biased",
        "factual": "High",
    },
    "NL Times": {
        "pais": "Países Bajos", "allsides": None, "mbfc": "Least Biased",
        "factual": "Mixed",
    },
    "La Silla Vacía": {
        "pais": "Colombia", "allsides": None, "mbfc": "Left-Center",
        "factual": "High",
        "nota": "Fundación sin ánimo de lucro; unidad de fact-checking certificada (IFCN).",
    },
    "El Tiempo": {
        "pais": "Colombia", "allsides": None, "mbfc": None, "propia": 0.5,
        "nota": "Sin rating externo. Propiedad de Luis Carlos Sarmiento (Grupo Aval); "
                "línea institucional/establecimiento.",
    },
    "Semana": {
        "pais": "Colombia", "allsides": None, "mbfc": None, "propia": 1.5,
        "nota": "Sin rating externo. Giro a la derecha desde la compra de Gilinski "
                "y la dirección de Vicky Dávila (2020), según varios medios.",
    },
    "La República": {
        "pais": "Colombia", "allsides": None, "mbfc": None, "propia": 1,
        "nota": "Sin rating externo. Diario económico del Grupo Ardila Lülle (dueño de RCN); "
                "fundado por el expresidente conservador Mariano Ospina Pérez.",
    },
    "Portafolio": {
        "pais": "Colombia", "allsides": None, "mbfc": None, "propia": 0.5,
        "nota": "Sin rating externo. Diario económico de la Casa Editorial El Tiempo "
                "(mismo dueño que El Tiempo, misma estimación).",
    },
    "De Limburger": {
        "pais": "Países Bajos", "allsides": None, "mbfc": None, "propia": 0,
        "nota": "Sin rating externo. Diario regional (Mediahuis), sobre todo noticias locales.",
    },
}


def lean(medio):
    """Puntuación de -2 a +2 y si es estimación propia: (float | None, bool)."""
    info = MEDIOS.get(medio)
    if not info:
        return None, False
    scores = []
    if info["allsides"]:
        scores.append(ALLSIDES[info["allsides"]])
    if info["mbfc"]:
        scores.append(MBFC[info["mbfc"]])
    if scores:
        return sum(scores) / len(scores), False
    return info.get("propia"), True


def label(score):
    """Puntuación -> etiqueta corta. Los cortes están a mitad de camino entre valores."""
    if score is None:
        return "sin dato"
    if score <= -1.5:
        return "izquierda"
    if score <= -0.5:
        return "centro-izq"
    if score < 0.5:
        return "centro"
    if score < 1.5:
        return "centro-der"
    return "derecha"


def short(medio):
    """Etiqueta para mostrar junto al nombre del medio; '~' indica estimación propia."""
    score, estimated = lean(medio)
    return ("~" if estimated else "") + label(score)


if __name__ == "__main__":
    print(f"{'Medio':15} {'Orientación':13} {'AllSides':10} {'MBFC':13} {'Rigor (MBFC)':15}")
    for medio, info in sorted(MEDIOS.items(), key=lambda kv: lean(kv[0])[0]):
        print(f"{medio:15} {short(medio):13} {info['allsides'] or '-':10} "
              f"{info['mbfc'] or '-':13} {info.get('factual') or '-':15}")
    print("\n~ = estimación propia (ningún sitio lo califica)")
