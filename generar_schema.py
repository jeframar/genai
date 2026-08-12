import os
import sys
import json
import time
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Cargar variables de entorno (.env)
load_dotenv()

# Prompt solicitado
PROMPT_ANALISIS = """Analiza el documento adjunto e identifica su estructura jerárquica (solamente un preview de los títulos y subtítulos, sin incluir el contenido de los párrafos). 

La extracción debe cumplir estrictamente con los siguientes lineamientos:

1. Incluye el Abstract (si lo hubiera) y la Introducción (aunque no tenga un título explícito de introducción, identifícala al inicio).

2. Incluye la sección de referencias o bibliografía al final (sin citar su contenido).

3. EXCLUYE explícitamente secciones administrativas, metadatos de autores y notas institucionales o legales. NO incluyas:
   - "ORCID iDs" (o identificadores ORCID de autores)
   - "Funding" / "Financial Support" / "Financiamiento"
   - "Declaration of conflicting interests" / "Conflict of Interest" / "Declaración de conflictos de interés"
   - "Acknowledgements" / "Agradecimientos"
   - "Data Availability Statement" / "Disponibilidad de datos"

4. No fuerces subniveles o desagregaciones si el texto no las contiene.

5. El formato de salida debe ser exclusivamente un objeto JSON válido que respete la siguiente estructura jerárquica:

{
  "titulo y subtitulo": "Título principal del documento",
  "capitulo o seccion": {
    "1": {
      "Nombre de la Sección o Título 1": ""
    },
    "2": {
      "Nombre de la Sección o Título 2": {
        "Subnivel 2.1 (si lo hubiera)": ""
      }
    }
  }
}"""


def seleccionar_pdf() -> str | None:
    """Abre un diálogo nativo de explorador de archivos para seleccionar un PDF."""
    root = tk.Tk()
    root.withdraw()  # Oculta la ventana principal de Tkinter
    root.attributes('-topmost', True)  # Trae el cuadro de diálogo al frente

    print("Abriendo explorador de archivos para seleccionar PDF...")
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo PDF a analizar",
        filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
    )
    root.destroy()
    return file_path if file_path else None


def extraer_limpiar_json(texto: str) -> dict:
    """Intenta parsear el texto devuelto por el modelo como JSON."""
    texto_limpio = texto.strip()
    # Eliminar bloques de código markdown si los hay
    if texto_limpio.startswith("```"):
        lineas = texto_limpio.splitlines()
        if lineas[0].startswith("```"):
            lineas = lineas[1:]
        if lineas and lineas[-1].startswith("```"):
            lineas = lineas[:-1]
        texto_limpio = "\n".join(lineas).strip()

    return json.loads(texto_limpio)


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No se encontró la variable de entorno GEMINI_API_KEY en el archivo .env o en el sistema.")
        sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser(description="Genera la plantilla jerárquica schema.json a partir de un PDF.")
    parser.add_argument("pdf_path", nargs="?", default=None, help="Ruta al archivo PDF. Si se omite, abre un explorador de archivos.")
    args = parser.parse_args()

    # 1. Seleccionar archivo PDF
    pdf_path = args.pdf_path
    if not pdf_path:
        pdf_path = seleccionar_pdf()
        if not pdf_path:
            print("Operación cancelada: No se seleccionó ningún archivo.")
            sys.exit(0)

    print(f"Archivo seleccionado: {pdf_path}")

    # 2. Inicializar cliente de Gemini
    client = genai.Client()
    file_ref = None

    try:
        print("Subiendo PDF a la API de Gemini...")
        file_ref = client.files.upload(file=pdf_path)
        print(f"Archivo subido con éxito (ID: {file_ref.name})")

        print("Analizando la estructura del PDF con Gemini...")
        start_time = time.perf_counter()
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=[file_ref, PROMPT_ANALISIS],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
        elapsed_time = time.perf_counter() - start_time
        print(f"Consulta a Gemini completada en {elapsed_time:.2f} segundos.")

        # 3. Parsear y validar salida JSON
        data = extraer_limpiar_json(response.text)

        # 4. Guardar resultado en schema.json en la raíz del repositorio
        repo_dir = Path(__file__).parent.resolve()
        output_file = repo_dir / "schema.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n¡Éxito! Estructura JSON guardada correctamente en: {output_file}")
        print("\nContenido extraído:")
        print(json.dumps(data, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"\nOcurrió un error durante el procesamiento: {e}")
        sys.exit(1)
    finally:
        # Eliminar archivo temporal en Gemini storage si se subió
        if file_ref:
            try:
                client.files.delete(name=file_ref.name)
                print("Archivo temporal limpiado de Gemini storage.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
