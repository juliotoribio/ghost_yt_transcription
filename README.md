# Ghost YT Downloader API

Ghost YT Downloader es una herramienta en Python para obtener transcripciones en texto plano desde videos de YouTube a partir de las pistas de subtítulos que expone `yt-dlp`.

El proyecto tiene tres superficies:

- Una librería pequeña con la lógica de extracción y parseo.
- Un CLI para uso manual o scripts.
- Un servicio REST con FastAPI.

## Características

- Acepta URLs completas, enlaces cortos y video IDs de YouTube.
- Prioriza subtítulos manuales sobre subtítulos automáticos.
- Tolera variantes regionales de idioma como `es-419`, `es-MX` o `en-US`.
- Devuelve errores de entrada inválida como errores de cliente, tanto en CLI como en API.
- Incluye pruebas unitarias para el núcleo, la CLI y el mapeo básico de errores en la API.

## Instalación

Se recomienda usar un entorno virtual.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Si vas a desarrollar o correr chequeos adicionales:

```bash
pip install -r requirements-dev.txt
```

## Uso como CLI

Con el entorno virtual activado:

```bash
python3 download_transcript.py "https://www.youtube.com/watch?v=5X26m52lMwU"
```

Guardar el resultado en un archivo:

```bash
python3 download_transcript.py "dQw4w9WgXcQ" --output transcripcion.txt
```

Devolver metadata y texto como JSON:

```bash
python3 download_transcript.py "dQw4w9WgXcQ" --json
```

Priorizar idiomas específicos:

```bash
python3 download_transcript.py "dQw4w9WgXcQ" --lang en --lang es
```

## Uso como API

Levanta el servicio local:

```bash
uvicorn main:app --reload
```

Documentación interactiva:

`http://127.0.0.1:8000/docs`

Ejemplo de request:

`http://127.0.0.1:8000/api/transcript?video=5X26m52lMwU&lang=es,en`

Ejemplo de respuesta:

```json
{
  "video_id": "5X26m52lMwU",
  "language": "es",
  "source": "yt_dlp_auto",
  "text": "En mi libro, en la primera página, menciono que..."
}
```

Si el video o el identificador son inválidos, la API responde con `400`.

## Tests

Con el entorno virtual activado:

```bash
python3 -m unittest discover tests/
```

Sin activar el entorno virtual:

```bash
venv/bin/python -m unittest discover tests/
```

Las pruebas que dependen de FastAPI se omiten automáticamente si esa dependencia no está instalada en el intérprete usado para correr la suite.

## Calidad de código

Chequeo de estilo:

```bash
ruff check .
```

Chequeo estático:

```bash
mypy
```
