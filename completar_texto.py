import os
import sys
import json
import time
import re
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json_repair

# Cargar variables de entorno (.env)
load_dotenv()


def seleccionar_pdf() -> str | None:
    """Abre un diálogo nativo de explorador de archivos para seleccionar el PDF."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    print("Abriendo explorador de archivos para seleccionar el PDF fuente...")
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo PDF correspondiente al schema.json",
        filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
    )
    root.destroy()
    return file_path if file_path else None


def es_seccion_referencias(nombre_seccion: str) -> bool:
    """Verifica si el nombre de la sección corresponde a Referencias o Bibliografía."""
    s = nombre_seccion.lower().strip()
    return "reference" in s or "referencia" in s or "bibliograf" in s


def limpiar_footers_y_headers(texto: str) -> str:
    """
    Limpia determinísticamente y de forma generalizada encabezados y pies de página
    comunes en cualquier paper académico o documento PDF:
    - Rutas de archivos (.doc, .docx, .pdf, .txt) con espacios o caracteres especiales
    - Estampas de fecha/hora de impresión y descarga
    - Números de página y contadores de páginas
    - Marcas de agua de descarga y avisos de Copyright
    """
    if not texto:
        return texto

    # 1. Eliminar cualquier ruta de archivo (incluyendo espacios, signos +, guiones y barras \ o /) terminada en .doc/.docx/.pdf/.txt
    # Ejemplo: suwr\SW2\Audit book\Audit Culture_CA_Shore+Wright_REVISED_2 Clean Copy.doc
    pattern_rutas = r'(?i)\b(?:[a-z0-9_\-\.\+\s\\]+[\\\/])+[a-z0-9_\-\.\+\s]+\.(?:doc|docx|pdf|txt|rtf)\b'
    texto = re.sub(pattern_rutas, '', texto)

    # 2. Eliminar marcas de fecha/hora de impresión universales (ej. 20-07-2014@22.32, 20 07 2014@22.32, 2024-05-18 14:30)
    pattern_fechas = r'\b\d{2}[-\/\s]\d{2}[-\/\s]\d{4}@\d{2}[\.:]\d{2}\b|\b(?:\d{2,4}[-\/\.]\d{2}[-\/\.]\d{2,4})(?:[@\s,T]\d{1,2}[\.:]\d{2}(?:[\.:]\d{2})?)?\b'
    texto = re.sub(pattern_fechas, '', texto)

    # 3. Eliminar líneas aisladas con números de página (ej. "Page 14 of 35", "Página 5", "12")
    pattern_paginas = r'(?im)^\s*(?:page|pág|página)?\s*\d+(?:\s*(?:of|de|\/)\s*\d+)?\s*$'
    texto = re.sub(pattern_paginas, '', texto)

    # 4. Eliminar avisos de descarga o derechos de autor en pie de página ("Downloaded from...", "© 20XX...", etc.)
    pattern_marcas = r'(?im)^\s*(?:downloaded from|accessed from|available online at|copyright|©|all rights reserved).*$'
    texto = re.sub(pattern_marcas, '', texto)

    # 5. Normalizar espacios dobles e integrar líneas
    lineas = [linea.strip() for linea in texto.splitlines()]
    resultado = []
    for l in lineas:
        if l:
            l_clean = re.sub(r' {2,}', ' ', l)
            resultado.append(l_clean)
        elif resultado and resultado[-1] != "":
            resultado.append("")

    return "\n".join(resultado).strip()


def remover_titulo_duplicado(clave: str, contenido: str) -> str:
    """Si el texto extraído comienza con el propio título de la sección, lo remueve para no duplicarlo."""
    if not clave or not contenido:
        return contenido

    texto_strip = contenido.lstrip()
    clave_clean = clave.strip()

    if texto_strip.lower().startswith(clave_clean.lower()):
        resto = texto_strip[len(clave_clean):].lstrip()
        resto = re.sub(r'^[:\-\s\n]+', '', resto)
        return resto

    return contenido


def limpiar_referencias_y_footers_en_data(obj):
    """Limpia recursivamente secciones de referencias y footers en toda la estructura de datos."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if es_seccion_referencias(k):
                obj[k] = ""
            elif isinstance(v, str):
                texto_limpio = limpiar_footers_y_headers(v)
                obj[k] = remover_titulo_duplicado(k, texto_limpio)
            elif isinstance(v, (dict, list)):
                limpiar_referencias_y_footers_en_data(v)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                limpiar_referencias_y_footers_en_data(item)


def extraer_nodos_vacios(obj, path=None):
    """Encuentra de forma recursiva todos los nodos hoja vacíos ('') excluyendo referencias."""
    if path is None:
        path = []
    hojas = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            if es_seccion_referencias(k):
                continue  # Las secciones de referencias nunca hacen llamada a la API
            if isinstance(v, str) and (v == "" or v == "[Sin contenido en documento]"):
                hojas.append((path + [k], obj, k))
            elif isinstance(v, (dict, list)):
                hojas.extend(extraer_nodos_vacios(v, path + [k]))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                hojas.extend(extraer_nodos_vacios(item, path + [str(idx)]))

    return hojas


def extraer_texto_seccion(client: genai.Client, file_ref, nombre_seccion: str, ruta_contexto: list[str]) -> str:
    """Realiza la consulta a Gemini con un prompt optimizado para ignorar pies de página y encabezados."""
    contexto_str = " > ".join([p for p in ruta_contexto if not p.isdigit()])

    prompt = f"""Analiza el documento PDF adjunto. 

TU TAREA:
Extrae el texto textual completo e íntegro correspondiente a la sección: "{nombre_seccion}".
Ubicación jerárquica esperada en el documento: {contexto_str}

REGLAS CRÍTICAS DE EXTRACCIÓN:
1. BÚSQUEDA IMPLÍCITA: Ten en cuenta que secciones como "Introduction", "Introducción" o similares pueden NO tener un título o encabezado explícito impreso en el PDF, sino comenzar justo después del Abstract o del título principal del documento. Debes identificar e incluir dicho texto completo aunque carezca de un título explícito.
2. OMITE PIES Y ENCABEZADOS DE PÁGINA (FOOTERS/HEADERS): Ignora y elimina cualquier pie de página, rutas de archivo local, marcas de agua, fechas de impresión/descarga o números de página repetitivos.
3. NO INCLUYAS EL TÍTULO AL INICIO DEL TEXTO: No repitas el título de la sección ("{nombre_seccion}") dentro del cuerpo del texto extraído. Comienza directamente con el contenido del primer párrafo.
4. NO RESUMIR: Extrae todo el contenido original perteneciente a dicha sección sin resumir, omitir ni parafrasear.
5. FORMATO DE SALIDA: Devuelve exclusivamente un objeto JSON válido con la clave "texto".

EJEMPLO DE SALIDA:
{{
  "texto": "Texto del primer párrafo..."
}}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[file_ref, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
            max_output_tokens=8192
        )
    )

    texto_bruto = response.text.strip()
    try:
        data = json.loads(texto_bruto, strict=False)
        res_texto = data.get("texto", texto_bruto)
    except Exception:
        data_reparada = json_repair.repair_json(texto_bruto, return_objects=True)
        if isinstance(data_reparada, dict):
            res_texto = data_reparada.get("texto", str(data_reparada))
        else:
            res_texto = str(data_reparada)

    # Limpieza determinística generalizada y remoción de título duplicado
    res_texto = limpiar_footers_y_headers(res_texto)
    return remover_titulo_duplicado(nombre_seccion, res_texto)


def extraer_texto_seccion_con_reintentos(
    client: genai.Client, 
    file_ref, 
    nombre_seccion: str, 
    ruta_contexto: list[str], 
    max_reintentos: int = 3, 
    espera_segundos: float = 3.0
) -> str:
    """Intenta extraer la sección. Si ocurre un error 429 de límite de cuota, espera el tiempo necesario de Gemini."""
    intentos_totales = max_reintentos + 1
    ultimo_error = None

    for intento in range(1, intentos_totales + 1):
        try:
            return extraer_texto_seccion(client, file_ref, nombre_seccion, ruta_contexto)
        except Exception as e:
            ultimo_error = e
            err_msg = str(e)
            
            # Si es un error de límite de cuota (429), pausar 12 segundos según la recomendación de la API de Google
            tiempo_espera = 12.0 if ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg) else espera_segundos

            if intento < intentos_totales:
                print(f"\n   [Aviso] Pausa en intento {intento}/{intentos_totales} (Límite temporal / Servidor). Esperando {tiempo_espera}s...", end="", flush=True)
                time.sleep(tiempo_espera)

    raise RuntimeError(f"Fallo persistente tras {intentos_totales} intentos: {ultimo_error}")


def guardar_progreso(output_file: Path, data: dict):
    """Guarda inmediatamente la estructura actual en texto_final.json."""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No se encontró GEMINI_API_KEY en el entorno o archivo .env.")
        sys.exit(1)

    repo_dir = Path(__file__).parent.resolve()
    schema_file = repo_dir / "schema.json"
    output_file = repo_dir / "texto_final.json"

    # 1. Verificar existencia de schema.json
    if not schema_file.exists():
        print(f"Error: No se encontró el archivo '{schema_file.name}' en la raíz del repositorio.")
        print("Por favor ejecuta primero 'uv run python generar_schema.py' para generar la estructura.")
        sys.exit(1)

    # 2. Cargar estado (Reanudación si texto_final.json ya existe)
    if output_file.exists():
        print(f"Detectado archivo de avance previo: '{output_file.name}'. Cargando estado actual...")
        with open(output_file, "r", encoding="utf-8") as f:
            working_data = json.load(f)
    else:
        print(f"Cargando plantilla inicial desde: '{schema_file.name}'...")
        with open(schema_file, "r", encoding="utf-8") as f:
            working_data = json.load(f)

    # Limpiar cualquier footer o referencia previa en working_data
    limpiar_referencias_y_footers_en_data(working_data)
    guardar_progreso(output_file, working_data)

    # 3. Identificar secciones pendientes por extraer (excluyendo referencias)
    secciones_pendientes = extraer_nodos_vacios(working_data)
    total_pendientes = len(secciones_pendientes)

    if total_pendientes == 0:
        print("\n¡Todas las secciones ya están completadas en 'texto_final.json'! (Sección de Referencias excluida por regla).")
        sys.exit(0)

    # 4. Seleccionar el archivo PDF fuente
    pdf_path = seleccionar_pdf()
    if not pdf_path:
        print("Operación cancelada: No se seleccionó ningún archivo PDF.")
        sys.exit(0)

    print(f"\nPDF seleccionado: {pdf_path}")
    print(f"Secciones pendientes por procesar: {total_pendientes}\n")

    # 5. Inicializar cliente Gemini y subir PDF (1 sola vez)
    client = genai.Client()
    file_ref = None

    try:
        print("Subiendo PDF a la API de Gemini...")
        file_ref = client.files.upload(file=pdf_path)
        print(f"Archivo subido con éxito (ID: {file_ref.name})\n")

        print("=" * 70)
        print(" INICIANDO EXTRACCIÓN CON REINTENTOS Y LIMPIEZA DE FOOTERS")
        print("=" * 70)

        start_total_time = time.perf_counter()

        # 6. Procesar secciones pendientes
        for index, (ruta, parent_dict, clave) in enumerate(secciones_pendientes, start=1):
            print(f"[{index}/{total_pendientes}] Extrayendo: '{clave}'...", end="", flush=True)

            start_sec_time = time.perf_counter()
            texto_extraido = extraer_texto_seccion_con_reintentos(
                client=client, 
                file_ref=file_ref, 
                nombre_seccion=clave, 
                ruta_contexto=ruta,
                max_reintentos=3,
                espera_segundos=3.0
            )
            sec_elapsed = time.perf_counter() - start_sec_time

            # Asignar texto
            parent_dict[clave] = texto_extraido if texto_extraido else "[Sin contenido en documento]"

            # GUARDAR PROGRESO INMEDIATAMENTE TRAS CADA SECCIÓN EXITOSA
            guardar_progreso(output_file, working_data)

            print(f" OK ({sec_elapsed:.2f}s | {len(texto_extraido):,} caracteres) [Guardado en {output_file.name}]")

        total_elapsed = time.perf_counter() - start_total_time

        print("=" * 70)
        print(f" Extracción completada en {total_elapsed:.2f} segundos en total.")
        print("=" * 70)
        print(f"\n¡Éxito! Documento 100% completado en: {output_file.name}")

    except Exception as e:
        print(f"\n\nOcurrió un error interrumpiendo el proceso: {e}")
        print(f"¡Atención! El progreso alcanzado fue guardado automáticamente en: '{output_file.name}'.")
        print("Puedes volver a ejecutar 'uv run python completar_texto.py' para reanudar la extracción solo de lo pendiente.")
        sys.exit(1)
    finally:
        if file_ref:
            try:
                client.files.delete(name=file_ref.name)
                print("Archivo temporal limpiado de Gemini storage.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
