"""Paso 4: resumir cada hecho con una IA gratuita, con respaldo si una falla.

Orden: Gemini (varios modelos) -> Groq (varios modelos) -> sin resumen.
Si ninguna IA responde, el agregador sigue funcionando; solo faltan los resúmenes.

Claves (gratis):
    Gemini: https://aistudio.google.com/apikey  -> GEMINI_API_KEY
    Groq:   https://console.groq.com/keys       -> GROQ_API_KEY
Se leen de variables de entorno (así las pasa GitHub Actions) o del archivo .env.
"""
import json
import os
import re
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# Si un modelo no existe o está saturado, se prueba el siguiente.
GEMINI_MODELS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]
GROQ_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

SYSTEM = """Eres un editor de noticias neutral. Recibes hechos, cada uno cubierto por
uno o varios medios (con su orientación política). Para cada hecho escribe en español:

- "titular": titular neutral de máximo 12 palabras, sin adjetivos valorativos.
- "resumen": 2 frases con solo lo que los medios reportan en común. Sin adjetivos
  valorativos. Si un dato solo lo da un medio o es una acusación, atribúyelo
  ("según DW..."). No agregues nada que no esté en los textos.
- "enfoques": 1 frase sobre en qué difiere el énfasis o el encuadre entre medios,
  nombrándolos. Si hay un solo medio o no hay una diferencia clara, deja "".
  No inventes diferencias.

Responde solo con JSON:
{"historias": [{"id": 1, "titular": "...", "resumen": "...", "enfoques": "..."}]}"""


class AIError(Exception):
    """Error de una IA. `retry_other_model` indica si vale la pena probar otro modelo."""

    def __init__(self, message, retry_other_model=False):
        super().__init__(message)
        self.retry_other_model = retry_other_model


def config():
    """Primero el archivo .env y encima las variables de entorno, que tienen prioridad."""
    cfg = {}
    try:
        for line in open(os.path.join(HERE, ".env"), encoding="utf-8"):
            m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
            if m and not line.lstrip().startswith("#"):
                cfg[m.group(1)] = m.group(2).strip("\"'")
    except FileNotFoundError:
        pass
    cfg.update({k: v for k, v in os.environ.items() if k.startswith(("GEMINI_", "GROQ_"))})
    return cfg


def build_prompt(groups, lean_label):
    """Convierte los grupos en texto para la IA. Cada grupo lleva un id para emparejar la respuesta."""
    parts = []
    for i, g in enumerate(groups, 1):
        parts.append(f"## Hecho {i}")
        for s in g:
            parts.append(f"- {s['source']} ({lean_label(s['source'])}): {s['title']}. {s['summary'][:300]}")
    return "\n".join(parts)


def post_json(url, body, headers, key):
    """POST con JSON; traduce los errores HTTP a AIError sin mostrar nunca la clave."""
    # User-Agent propio: Groq bloquea (403) el que urllib manda por defecto.
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "news-aggregator/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("error", {})
        except Exception:  # noqa: BLE001
            detail = {}
        msg = str(detail.get("message", "") if isinstance(detail, dict) else detail)[:200]
        msg = msg.replace(key, "***")
        # 404 = el modelo no existe; 429 = límite gratis; 5xx = saturado. Otro modelo puede servir.
        # 400 que menciona el modelo = retirado. Una clave mala (401/403) no mejora cambiando de modelo.
        retry = e.code in (404, 429, 500, 502, 503, 504) or (e.code == 400 and "model" in msg.lower())
        raise AIError(f"HTTP {e.code}: {msg}", retry_other_model=retry) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        # Un modelo lento puede no serlo en otro; sin internet, en cambio, ninguno responderá.
        slow = isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError)
        if slow:
            raise AIError("tardó demasiado", retry_other_model=True) from None
        raise AIError(f"sin conexión ({e})", retry_other_model=False) from None


def try_models(models, call):
    """Prueba cada modelo hasta que uno responda. Devuelve (texto, modelo)."""
    errors = []
    for model in models:
        try:
            return call(model), model
        except AIError as e:
            errors.append(f"{model}: {e}")
            if not e.retry_other_model:
                break
    raise AIError("; ".join(errors))


def gemini(key, system, prompt, models):
    def call(model):
        data = post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                # Temperatura baja = respuestas más sobrias y repetibles.
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
            },
            {"x-goog-api-key": key}, key,
        )
        return "".join(p.get("text", "") for c in data.get("candidates", [])[:1]
                       for p in c.get("content", {}).get("parts", []))
    return try_models(models, call)


def groq(key, system, prompt, models):
    # Groq usa el mismo formato que la API de OpenAI.
    def call(model):
        data = post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0.2,
            },
            {"Authorization": f"Bearer {key}"}, key,
        )
        return data["choices"][0]["message"]["content"]
    return try_models(models, call)


def parse(text, n):
    """Texto JSON de la IA -> lista de n dicts {titular, resumen, enfoques} (None si falta uno)."""
    try:
        items = json.loads(text)["historias"]
    except (ValueError, KeyError, TypeError):
        raise AIError("la respuesta no es el JSON pedido") from None
    out = [None] * n
    for item in items:
        if not isinstance(item, dict):
            continue
        i = item.get("id")
        if isinstance(i, int) and 1 <= i <= n and isinstance(item.get("resumen"), str):
            out[i - 1] = {"titular": str(item.get("titular") or "").strip(),
                          "resumen": item["resumen"].strip(),
                          "enfoques": str(item.get("enfoques") or "").strip()}
    if not any(out):
        raise AIError("la respuesta no trae ningún resumen")
    return out


def ask(system, prompt, parse_answer):
    """Pregunta a Gemini y, si falla, a Groq.

    Devuelve (respuesta ya interpretada | None, "Proveedor/modelo" | None, lista de errores).
    Una respuesta que parse_answer no entiende cuenta como fallo y pasa al siguiente proveedor.
    """
    cfg = config()
    providers = [
        ("Gemini", "GEMINI_API_KEY", gemini, [cfg.get("GEMINI_MODEL"), *GEMINI_MODELS]),
        ("Groq", "GROQ_API_KEY", groq, [cfg.get("GROQ_MODEL"), *GROQ_MODELS]),
    ]
    errors = []
    for name, key_name, call, models in providers:
        key = cfg.get(key_name, "")
        if len(key) < 20:
            errors.append(f"{name}: falta {key_name} en .env")
            continue
        # dict.fromkeys quita repetidos y None conservando el orden.
        models = [m for m in dict.fromkeys(models) if m]
        try:
            text, model = call(key, system, prompt, models)
            return parse_answer(text), f"{name}/{model}", errors
        except AIError as e:
            errors.append(f"{name}: {e}")
    return None, None, errors


def summarize(groups, lean_label):
    """Titular, resumen y enfoques de cada grupo. Misma salida que ask()."""
    return ask(SYSTEM, build_prompt(groups, lean_label), lambda text: parse(text, len(groups)))


CHOOSE_SYSTEM = """Para cada tema recibes titulares numerados y una instrucción:

- "elige": devuelve el número del titular más relevante: política, economía,
  servicios públicos, vivienda, seguridad o decisiones que afectan a mucha gente.
  Evita accidentes menores, agenda cultural, estilo de vida y deportes, salvo que
  no haya nada más.
- "solo si es importante": devuelve un número solo si ese titular es un evento
  realmente importante (decisión política o económica relevante, emergencia grave,
  algo que cambie la vida de mucha gente en la región). Si ninguno lo es, devuelve 0.
  Accidentes, sucesos locales menores, cultura, ocio y deporte no son importantes.

Responde solo con JSON: {"elegidos": {"<tema>": <número>}}"""


def choose(candidates, only_important=()):
    """candidates: {tema: [titular, ...]}.

    Devuelve ({tema: índice desde 0, o None si la IA dijo que nada es importante} | None,
    usado, errores). Un tema que falte en el resultado es porque la IA no dio un número válido.
    """
    prompt = "\n\n".join(
        f"## {topic} ({'solo si es importante' if topic in only_important else 'elige'})\n"
        + "\n".join(f"{i}. {t}" for i, t in enumerate(titles, 1))
        for topic, titles in candidates.items())

    def parse_choice(text):
        try:
            picked = json.loads(text)["elegidos"]
        except (ValueError, KeyError, TypeError):
            raise AIError("la respuesta no es el JSON pedido") from None
        out = {}
        for t, titles in candidates.items():
            n = picked.get(t)
            if isinstance(n, int) and 1 <= n <= len(titles):
                out[t] = n - 1
            elif n == 0 and t in only_important:
                out[t] = None
        return out

    return ask(CHOOSE_SYSTEM, prompt, parse_choice)
