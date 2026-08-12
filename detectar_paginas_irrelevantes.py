import os
import sys
import json
import time
import argparse
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json_repair

# Cargar variables de entorno (.env)
load_dotenv()


def seleccionar_pdf_gui() -> str | None:
    """Abre un diálogo nativo de explorador de archivos para seleccionar un PDF si no se pasó por CLI."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    print("Abriendo explorador de archivos para seleccionar el PDF a analizar...")
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo PDF para detectar páginas irrelevantes",
        filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
    )
    root.destroy()
    return file_path if file_path else None


def extraer_limpiar_json(texto: str) -> dict:
    """Parsea la salida del modelo como JSON, utilizando json_repair como fallback."""
    texto_limpio = texto.strip()
    if texto_limpio.startswith("```"):
        lineas = texto_limpio.splitlines()
        if lineas[0].startswith("```"):
            lineas = lineas[1:]
        if lineas and lineas[-1].startswith("```"):
            lineas = lineas[:-1]
        texto_limpio = "\n".join(lineas).strip()

    try:
        return json.loads(texto_limpio)
    except Exception:
        return json_repair.repair_json(texto_limpio, return_objects=True)


def detectar_paginas_irrelevantes(client: genai.Client, pdf_path: str, modelos: list[str] = None) -> dict:
    """Sube el PDF a Gemini y analiza directamente si hay hojas extra/irrelevantes probando modelos de respaldo si la cuotas se agotan."""
    if modelos is None:
        modelos = ["gemini-2.5-flash", "gemini-3.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

    file_ref = None
    try:
        print("Subiendo PDF a la API de Gemini...")
        file_ref = client.files.upload(file=pdf_path)
        print(f"Archivo subido con éxito (ID: {file_ref.name})")

        prompt = """Analiza exhaustivamente el documento PDF adjunto (considerando la numeración física secuencial de páginas 1, 2, 3... N del archivo PDF).

TU TAREA CONSTA DE DOS PARTES:

PARTE 1: DETECCIÓN DE PÁGINAS IRRELEVANTES O HOJAS EXTRA
Identifica los números de página FÍSICA del archivo PDF (numeración basada puramente en la cantidad total de páginas del archivo PDF: página 1, 2, 3, etc., e IGNORANDO la numeración impresa interna en el pie de página o encabezado) que correspondan a HOJAS EXTRA O IRRELEVANTES al contenido del artículo/documento.

DEFINICIÓN DE CONTENIDO DEL DOCUMENTO / ARTÍCULO (NO CONSIDERAR IRRELEVANTES):
Forman parte del documento las siguientes partes de interés:
- Portada o cabecera del artículo (Título principal, autores, afiliaciones, fechas).
- Resumen / Abstract.
- Introducción / Introduction.
- Cuerpo principal del documento (secciones, capítulos, subsecciones, metodología, resultados, discusión, etc.).
- Conclusiones / Conclusion.
- Referencias / Bibliografía / Notas / Anexos / Apéndices.

DEFINICIÓN DE HOJAS EXTRA O IRRELEVANTES:
Una página física se considera EXTRA / IRRELEVANTE si NO contiene ninguna parte sustantiva del documento. Por ejemplo:
- Carátulas o portadas publicitarias preliminares agregadas por repositorios o editoriales (ej. carátulas añadidas por JSTOR, ResearchGate, etc.).
- Hojas de anuncios publicitarios de la revista o avisos de conferencias.
- Boletines de suscripción, tarifas o índices de anunciantes.
- Páginas totalmente en blanco.
- Avisos de derechos de autor, licencias o páginas legales aisladas que no contengan ningún texto o sección del artículo.

REGLA DE EXCLUSIÓN CRÍTICA:
Si en una página física aparece AUNQUE SEA UN APARTADO, FRAGMENTO DE PÁRRAFO, TÍTULO O SUBTÍTULO perteneciente a las partes del documento (Abstract, Introducción, Secciones, Conclusiones, Referencias, etc.), esa página NO ES IRRELEVANTE. Por lo tanto, DEBES OMITIRLA de la lista de páginas irrelevantes.

PARTE 2: DETECCIÓN DE ENCABEZADOS Y PIES DE PÁGINA (HEADERS Y FOOTERS)
Identifica y extrae en una lista todos los textos recurrentes, títulos corrientes, encabezados (headers) o pies de página (footers) que aparezcan en los márgenes de las páginas del documento. Esto se utilizará para eliminarlos del texto extraído posteriormente.
Incluye:
- Títulos del artículo o nombres de revista impresos en los márgenes superiores o inferiores.
- Marcas de agua, notas de copyright o avisos de descarga (ej. "Downloaded from...", "Accessed from...", "© 20XX...", etc.).
- Rutas de archivo o nombres de archivo impresos en los bordes.
- Marcas de fecha/hora de descarga o impresión.
- Formatos recurrentes de números de página (ej. "Page X of Y", "Página X", etc.).

FORMATO DE SALIDA:
Devuelve exclusivamente un objeto JSON válido con la siguiente estructura estricta:
{
  "total_paginas_pdf": <int>,
  "paginas_irrelevantes": [<int>, <int>, ...],
  "motivos": {
    "<numero_pagina>": "Explicación breve de por qué es una hoja extra/irrelevante"
  },
  "encabezados_y_pies_de_pagina": [
    "Texto exacto o patrón de encabezado/pie de página 1",
    "Texto exacto o patrón de encabezado/pie de página 2",
    ...
  ]
}"""

        ultimo_error = None
        for model_name in modelos:
            print(f"\nAnalizando páginas del PDF con modelo '{model_name}'...")
            for intento in range(1, 3):
                try:
                    start_time = time.perf_counter()
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[file_ref, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1,
                            max_output_tokens=65536
                        )
                    )
                    elapsed_time = time.perf_counter() - start_time
                    print(f"Consulta completada con éxito en {elapsed_time:.2f} segundos ({model_name}).")
                    return extraer_limpiar_json(response.text)
                except Exception as e:
                    ultimo_error = e
                    err_msg = str(e)
                    print(f"   [Aviso] Error con {model_name} (Intento {intento}/2): {err_msg[:80]}...")
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                        print("   --> Cuota saturada en modelo. Cambiando a modelo alternativo o esperando...")
                        time.sleep(10)
                        break  # Pasar al siguiente modelo de la lista si la cuota del modelo actual se agotó
                    else:
                        time.sleep(3)

        raise RuntimeError(f"No se pudo completar la consulta con ninguno de los modelos. Último error: {ultimo_error}")

    finally:
        if file_ref:
            try:
                client.files.delete(name=file_ref.name)
                print("Archivo temporal limpiado de Gemini Storage.")
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(
        description="Detecta páginas irrelevantes/extra en un PDF usando Gemini 2.5/3.5 Flash de forma independiente a schema.json."
    )
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=None,
        help="Ruta al archivo PDF. Si se omite, se abrirá un cuadro de diálogo gráfico."
    )
    parser.add_argument(
        "-m", "--model",
        default="gemini-2.5-flash",
        help="Modelo principal a utilizar (por defecto: gemini-2.5-flash)."
    )

    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No se encontró GEMINI_API_KEY en el entorno o en el archivo .env.")
        sys.exit(1)

    # Seleccionar PDF por CLI o por GUI
    pdf_path = args.pdf_path
    if not pdf_path:
        pdf_path = seleccionar_pdf_gui()
        if not pdf_path:
            print("Operación cancelada: No se seleccionó ningún archivo PDF.")
            sys.exit(0)

    pdf_file_obj = Path(pdf_path)
    if not pdf_file_obj.exists():
        print(f"Error: El archivo PDF especificado no existe: {pdf_path}")
        sys.exit(1)

    print(f"\nPDF seleccionado: {pdf_file_obj.name}")

    client = genai.Client()
    
    # Construir lista de modelos intentando primero el modelo especificado
    modelos_ordenados = [args.model]
    for m in ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        if m not in modelos_ordenados:
            modelos_ordenados.append(m)

    resultado = detectar_paginas_irrelevantes(client, str(pdf_file_obj), modelos=modelos_ordenados)

    repo_dir = Path(__file__).parent.resolve()
    output_file = repo_dir / "paginas_irrelevantes.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    paginas_list = resultado.get("paginas_irrelevantes", [])
    total_paginas = resultado.get("total_paginas_pdf", "Desconocido")
    motivos = resultado.get("motivos", {})
    headers_footers = resultado.get("encabezados_y_pies_de_pagina", [])

    print("\n" + "=" * 60)
    print(" RESULTADO DE DETECCIÓN DE PÁGINAS Y ELEMENTOS REPETITIVOS")
    print("=" * 60)
    print(f" Total de páginas del PDF:     {total_paginas}")
    print(f" Páginas irrelevantes (PDF):   {paginas_list}")
    print(f" Encabezados/Footers a omitir: {len(headers_footers)} detectados")
    print("=" * 60)

    if motivos:
        print("\nDetalle de motivos por página irrelevante:")
        for pag, motivo in motivos.items():
            print(f" - Página {pag}: {motivo}")

    if headers_footers:
        print("\nEncabezados y pies de página detectados (a eliminar):")
        for hf in headers_footers:
            print(f" - {hf}")

    print(f"\n¡Éxito! Resultado guardado correctamente en: {output_file.name}")


if __name__ == "__main__":
    main()
