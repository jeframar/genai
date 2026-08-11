# Generador y Extractor Estructurado de Documentos PDF con Gemini API

Este repositorio contiene un flujo de trabajo optimizado en Python para procesar documentos PDF largos utilizando la API oficial de **Google Gemini (`google-genai`)**, extraer su jerarquía y rellenar progresivamente su texto completo de forma estructurada.

---

## 🛠️ Requisitos e Instalación

### 1. Configuración de Variables de Entorno
Crea un archivo `.env` en la raíz del repositorio con tu clave de API de Google AI Studio:

```env
GEMINI_API_KEY="tu_clave_aqui"
```

### 2. Instalación de Dependencias
El proyecto utiliza `uv` para la gestión de entornos y dependencias:

```bash
uv sync
```

---

## 🚀 Flujo de Trabajo

### Paso 1: Generación del Schema Jerárquico
Selecciona un archivo PDF mediante el explorador de archivos. El script analizará la estructura del documento y generará un archivo `schema.json` con los títulos y subtítulos del PDF (sin incluir el contenido de los párrafos).

```bash
uv run python generar_schema.py
```
* **Salida generada:** `schema.json`

---

### Paso 2: Extracción Completa Sección por Sección
Carga el `schema.json` generado en el paso anterior y realiza llamadas independientes por cada sección para extraer el texto textual completo e íntegro del PDF.

**Características:**
* **Búsqueda Implícita:** Detecta secciones sin título explícito (como la Introducción).
* **Manejo de Reintentos:** Ante errores temporales (ej. `503 UNAVAILABLE`), realiza hasta 2 reintentos con 2 segundos de espera.
* **Persistencia y Reanudación:** Guarda el avance automáticamente tras cada sección exitosa en `texto_final.json`. Si el proceso se interrumpe, se puede reanudar exactamente desde la sección pendiente.

```bash
uv run python completar_texto.py
```
* **Salida generada:** `texto_final.json`

---

### Paso 3: Conversión a Documento Markdown
Convierte el objeto JSON `texto_final.json` (o `schema.json`) en un documento Markdown bien formateado, traduciendo la jerarquía del JSON a encabezados Markdown (`#`, `##`, `###`, etc.) y conservando los títulos incluso si no contienen texto.

```bash
uv run python json_a_markdown.py
```
* **Salida generada:** `texto_final.md`

---

## 📊 Herramientas Auxiliares

### Contador de Tokens de la API
Permite seleccionar cualquier archivo desde el explorador y calcular la cantidad exacta de tokens procesados por el modelo `gemini-2.5-flash`.

```bash
uv run python contar_tokens.py
```

---

## 📁 Estructura del Repositorio

```text
genai/
├── .env                  # Clave de API de Gemini
├── pyproject.toml        # Configuración de dependencias (google-genai, json-repair, python-dotenv)
├── generar_schema.py     # Paso 1: Generación del schema JSON
├── completar_texto.py    # Paso 2: Poblado sección por sección del texto completo
├── json_a_markdown.py    # Paso 3: Conversión de JSON a documento Markdown (.md)
├── contar_tokens.py      # Contador oficial de tokens de Gemini API
├── schema.json           # Estructura jerárquica del documento
├── texto_final.json      # Documento final poblado con el texto completo
└── texto_final.md        # Documento renderizado en formato Markdown
```
