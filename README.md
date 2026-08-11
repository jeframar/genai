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

### Contador de Tokens (`contar_tokens.py`)
Cuenta el número exacto de tokens de un archivo PDF seleccionado desde el explorador.
```bash
uv run python contar_tokens.py
```
