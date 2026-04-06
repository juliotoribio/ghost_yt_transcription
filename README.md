# 👻 Ghost YT Downloader API

**Ghost YT Downloader** es una herramienta y microservicio escrito en Python diseñado para extraer transcripciones limpias (subtítulos crudos) de videos de YouTube, evadiendo proactivamente los bloques de IPs y pantallas de "Demuestra que no eres un Robot" de YouTube.

A diferencia del web-scraping tradicional, la lógica interna aprovecha el motor de [yt-dlp](https://github.com/yt-dlp/yt-dlp) para interceptar sutilmente la API `json3` interna dirigida a clientes móviles y Smart TVs, garantizando alta disponibilidad sin requerir el uso de Cookies.

## 🚀 Características
* **Extracción Invisible:** Evade completamente los mecanismos anti-bot de las peticiones Web comunes.
* **Calidad de Texto Limpio:** Convierte la ruidosa especificación de subtítulos de YouTube en texto plano directamente consumible para IA.
* **Dos Modos de Operación:** Uso versátil: desde la Terminal de Comandos (CLI) o como un Microservicio REST (FastAPI).
* **Calidad de Grado Empresarial (PEP8):** Código sometido al rigor de [Ruff](https://docs.astral.sh/ruff/) y MyPy siguiendo los más estrictos patrones de la industria (*KISS, SRP*).

## 🧰 Instalación y Configuración

Se recomienda aislar las dependencias utilizando un entorno virtual.

```bash
# 1. Clonar el repositorio
git clone <tu-repositorio>
cd <nombre-repositorio>

# 2. Crear y activar tu entorno virtual (Mac/Linux)
python3 -m venv venv
source venv/bin/activate

# (Windows)
# venv\Scripts\activate

# 3. Instalar las dependencias
pip install -r requirements.txt
```

---

## 💻 Uso como Línea de Comandos (CLI)

Ideal para scripts rápidos o procesos manuales. Puedes invocar `download_transcript.py` y pasar directamente un URL o ID de YouTube.

**(Asegúrate de tener el entorno virtual activado)**

**Uso Básico (Salida de texto en consola):**
```bash
python download_transcript.py "https://www.youtube.com/watch?v=5X26m52lMwU"
```

**Guardar a un archivo:**
```bash
python download_transcript.py "dQw4w9WgXcQ" --output transcripcion.txt
```

**Salida en JSON:**
```bash
python download_transcript.py "dQw4w9WgXcQ" --json
```

**Forzar prioridad de idioma (ej: buscar en inglés primero):**
```bash
python download_transcript.py "dQw4w9WgXcQ" --lang en
```

---

## 🌐 Uso como Servicio REST (FastAPI)

El proyecto está preparado para escalar respondiendo a peticiones HTTP asíncronas para su uso sistémico en integraciones web.

**1. Iniciar el servidor local:**
```bash
uvicorn main:app --reload
```

**2. Documentación Interactiva (Swagger UI):**
Abre tu navegador y visualiza, prueba e interactúa con el API en tiempo real en:
👉 `http://127.0.0.1:8000/docs`

**3. Ejemplo de llamada HTTP (GET):**
Basta con hacer una petición HTTP GET. Puedes probarlo haciendo click en este enlace:
`http://127.0.0.1:8000/api/transcript?video=5X26m52lMwU`

**Respuesta devuelta (Ejemplo Corto):**
```json
{
  "video_id": "5X26m52lMwU",
  "language": "es",
  "source": "yt_dlp_auto",
  "text": "En mi libro, en la primera página, menciono que..."
}
```

---

## 🧪 Testing

Mantenemos un robusto conjunto de pruebas unitarias que blindan la lógica contra cambios futuros en la arquitectura de YouTube, lo cual hace extremadamente seguro el despliegue a producción.

Para ejecutar los tests, desde la raíz del proyecto corre:
```bash
python -m unittest discover tests/
```
