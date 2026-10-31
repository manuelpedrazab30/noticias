# Noticias

Agregador de noticias personal: gratis, lo más neutral posible y sin sobrecarga.
Cada mañana publica un digest de máximo 10 historias en GitHub Pages.

- Lee feeds RSS por tema (geopolítica, Colombia, economía, tecnología, Países Bajos, Limburg).
- Agrupa la misma noticia publicada por distintos medios (`cluster.py`).
- Muestra la orientación de cada medio según AllSides y Media Bias/Fact Check (`medios.py`)
  y avisa cuando un hecho solo lo cubre un lado del espectro.
- Resume cada historia con Gemini, con Groq como respaldo (`summarize.py`).
- Elige las historias y escribe la página (`digest.py`); GitHub Actions lo ejecuta a diario.

## Uso local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env               # y pon tus claves
.venv/bin/python news.py           # todo agrupado, en la terminal
.venv/bin/python digest.py         # genera docs/index.html
open docs/index.html
```
