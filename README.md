# GenAI Paper Processing Pipeline

Este repositorio contiene un pipeline modular de 4 pasos automatizados en Python para extraer, completar, formatear y auditar la calidad de documentos y papers académicos en PDF utilizando la API de Google Gemini (`gemini-2.5-flash`).

---

## 🛠️ Requisitos Previos

- **Python 3.10+** (probado con Python 3.14)
- **uv** (Administrador de paquetes rápido para Python)
- Clave de API de Gemini (`GEMINI_API_KEY`) configurada en un archivo `.env`.

### Configuración del Entorno

1. Clona o abre este repositorio.
2. Crea un archivo `.env` en la raíz del repositorio con tu API Key:
   ```env
   GEMINI_API_KEY="tu_api_key_aqui"
   ```

3. Sincroniza las dependencias con `uv`:
   ```bash
   uv sync
   ```

---

## 📊 Matriz de Scripts, Modelos de IA y Configuración

| Script Python | Modelo de IA Principal | Nivel de Reasoning / Temperatura | Max Output Tokens | Función Principal |
| :--- | :--- | :--- | :--- | :--- |
| [`app.py`](file:///c:/Users/jeanf/Proyectos/genai/app.py) | Orquestador Interact. | N/A | N/A | Menú interactivo para ejecutar secuencialmente o elegir los pasos 1 a 4. |
| [`generar_schema.py`](file:///c:/Users/jeanf/Proyectos/genai/generar_schema.py) | `gemini-3.5-flash` | Estándar (`temp=0.1`) | 8,192 *(por defecto)* | Genera la plantilla de estructura jerárquica `schema.json`. |
| [`completar_texto.py`](file:///c:/Users/jeanf/Proyectos/genai/completar_texto.py) | `gemini-2.5-flash` | Estándar (`temp=0.1`) | 8,192 tokens | Extrae texto sección por sección omitiendo footers. |
| [`completar_schema.py`](file:///c:/Users/jeanf/Proyectos/genai/completar_schema.py) | `gemini-3.5-flash` | Estándar (`temp=0.1`) | 8,192 tokens | Extrae texto crudo/literal bloque a bloque sin corrección ortográfica (salida: `schema_completado.json`). |
| [`traducir_texto.py`](file:///c:/Users/jeanf/Proyectos/genai/traducir_texto.py) | `gemini-2.5-flash` | Estándar (`temp=0.2`) | 8,192 tokens | Depura incoherencias/footers por bloque y traduce al español (`schema_completado_espanol.json`). |
| [`detectar_paginas_irrelevantes.py`](file:///c:/Users/jeanf/Proyectos/genai/detectar_paginas_irrelevantes.py) | `gemini-2.5-flash` *(Fallback: 3.5, 2.0, 1.5)* | Estándar (`temp=0.1`) | 65,536 tokens | Detecta hojas irrelevantes e identifica lista de headers/footers. |
| [`analizar_markdown.py`](file:///c:/Users/jeanf/Proyectos/genai/analizar_markdown.py) | `gemini-2.5-flash` *(REST API)* | Estándar (`temp=0.1`) | 8,192 *(por defecto)* | Audita estilo, sintaxis y ortografía en el Markdown resultante. |
| [`contar_tokens.py`](file:///c:/Users/jeanf/Proyectos/genai/contar_tokens.py) | `gemini-2.5-flash` | N/A *(API count_tokens)* | N/A | Cuenta el número exacto de tokens de un archivo. |
| [`json_a_markdown.py`](file:///c:/Users/jeanf/Proyectos/genai/json_a_markdown.py) | N/A *(Procesamiento Python)* | N/A | N/A | Transforma de forma determinística la jerarquía JSON a `.md` aplicando limpieza de footers. |
| [`json_a_markdown_raw.py`](file:///c:/Users/jeanf/Proyectos/genai/json_a_markdown_raw.py) | N/A *(Procesamiento Python)* | N/A | N/A | Transforma la jerarquía JSON a `.md` directo renombrando con el nombre del PDF. |
| [`extraer_texto_html.py`](file:///c:/Users/jeanf/Proyectos/genai/extraer_texto_html.py) | N/A *(BeautifulSoup Parser)* | N/A | N/A | Extrae el contenido completo de artículos alojados en HTML/OJS. |
| [`extraer_texto_epub.py`](file:///c:/Users/jeanf/Proyectos/genai/extraer_texto_epub.py) | N/A *(Ebooklib Parser)* | N/A | N/A | Extrae contenido estructurado de libros/artículos `.epub`. |

---

## 🚀 Flujo de Trabajo (Pipeline de 4 Pasos)

### Paso 1: Generar la Estructura Jerárquica (`generar_schema.py`)
Selecciona un PDF desde el explorador de archivos nativo y analiza la tabla de contenidos / estructura sin extraer párrafos completos.
```bash
uv run python generar_schema.py
```
* **Resultado:** Crea `schema.json` con la plantilla del documento.

---

### Paso 2: Extraer y Completar el Texto Sección por Sección (`completar_texto.py`)
Carga `schema.json`, sube el PDF a Gemini 1 sola vez y extrae el texto sección por sección con manejo de límites de cuota (reintentos 429), reanudación automática, omitiendo referencias y aplicando una limpieza determinística universal de pies de página (rutas `.doc`/`.pdf`, fechas de impresión, números de página).
```bash
uv run python completar_texto.py
```
* **Resultado:** Crea `texto_final.json` guardando el avance incrementalmente.

---

### Paso 3: Convertir a Documento Markdown (`json_a_markdown.py`)
Transforma `texto_final.json` en un documento `.md` respetando jerarquías (`#`, `##`, `###`), eliminando títulos duplicados al inicio de los párrafos y aplicando filtros Regex universales contra footers.
```bash
uv run python json_a_markdown.py
```
* **Resultado:** Genera `texto_final.md`.

---

### Paso 4: Auditoría de Calidad y Ortografía (`analizar_markdown.py`)
Audita `texto_final.md` en busca de caracteres corruptos (`\ufffd`), dobles espacios, puntuación desalineada, saltos de línea excesivos, paréntesis desbalanceados y realiza una revisión de estilo y ortografía.
```bash
uv run python analizar_markdown.py
```
* **Resultado:** Genera el informe detallado `reporte_calidad.txt`.

---

## 🛠️ Herramientas Adicionales

### Extractor Literal sin Corrección Ortográfica (`completar_schema.py`)
Extrae el texto textual y fiel bloque por bloque directamente del PDF para cada nodo de `schema.json`, sin realizar ninguna corrección ortográfica o gramatical (preservando erratas o typos del original).
```bash
python completar_schema.py
```
* **Resultado:** Rellena los bloques en `schema.json`, `schema_completado.json` y `texto_final.json`.

### Depurador y Traductor por Bloque (`traducir_texto.py`)
Toma `texto_final.json` como entrada, efectúa 1 llamada por bloque a la API para (1) retirar fragmentos incoherentes o footers colados y (2) traducir el texto al español académico. Finalmente, genera un documento Markdown estructurado con jerarquías.
```bash
python traducir_texto.py
```
* **Resultado:** Genera `texto_final_espanol.json` y `texto_final_espanol.md`.

### Contador de Tokens (`contar_tokens.py`)
Cuenta el número exacto de tokens de un archivo PDF seleccionado desde el explorador.
```bash
uv run python contar_tokens.py
```

### Extractor de Texto HTML / Artículos OJS (`extraer_texto_html.py`)
Extrae el contenido textual íntegro y estructurado de un artículo académico alojado en formato HTML o en visores de revistas de Open Journal Systems (OJS) como Cultural Anthropology, convirtiéndolo a formato Markdown (`articulo_extraido.md`).
```bash
python extraer_texto_html.py [URL_OPCIONAL]
```

### Extractor de Libros y Artículos EPUB (`extraer_texto_epub.py`)
Extrae el contenido completo de archivos `.epub` (libros digitales o artículos descargados en formato EPUB), leyendo el orden oficial de la secuencia de lectura (spine) y convirtiéndolo a formato Markdown estructurado (`articulo_extraido_epub.md`).
```bash
python extraer_texto_epub.py <archivo.epub>
```

### Detector de Páginas Irrelevantes y Encabezados/Footers (`detectar_paginas_irrelevantes.py`)
Analiza directamente cualquier PDF usando Gemini Flash para:
1. Detectar páginas físicas irrelevantes (carátulas publicitarias, hojas en blanco, boletines, anuncios) que no contengan partes sustantivas del documento.
2. Identificar la lista de **encabezados y pies de página recurrentes** (headers/footers, títulos de revistas, números de página, marcas de descarga) para su eliminación posterior del texto extraído.
```bash
python detectar_paginas_irrelevantes.py
```
*(Si no especificas un archivo, abre automáticamente el explorador de archivos nativo de Windows).*



