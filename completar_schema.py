import os
import sys
import json
import time
import re
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json_repair

# Intentar importar pdf_inspector para extraer el texto cuando se usen modelos de OpenRouter o Gemini en modo Markdown
try:
    import pdf_inspector
    HAS_PDF_INSPECTOR = True
except ImportError:
    HAS_PDF_INSPECTOR = False

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


def seleccionar_modelo(model_arg: str | None = None) -> tuple[str, bool]:
    """
    Permite al usuario seleccionar el modelo a utilizar mediante CLI o menú interactivo.
    Retorna una tupla (nombre_modelo, es_openrouter).
    """
    modelos_opciones = {
        "1": ("gemini-3.6-flash", False),
        "2": ("openrouter/free", True),
        "3": ("liquid/lfm-2.5-2.6b:free", True),
        "4": ("nvidia/nemotron-3.5-lightning:free", True),
        "5": ("inclusionai/ling-3.0-tiny:free", True),
        "6": ("poolside/laguna-s-2.1:free", True),
        "7": ("cohere/north-mini-code:free", True),
    }

    if model_arg:
        model_str = model_arg.strip()
        is_or = model_str.startswith("openrouter/") or "/" in model_str or ":free" in model_str
        return model_str, is_or

    print("=" * 70)
    print(" SELECCIÓN DE MODELO DE IA")
    print("=" * 70)
    print(" [Modelos Nativos Gemini API]")
    print("   1. gemini-3.6-flash (Predeterminado / Recomendado)")
    print("\n [Modelos Gratuitos Activos de OpenRouter]")
    print("   2. openrouter/free (Router automático de modelos gratuitos)")
    print("   3. liquid/lfm-2.5-2.6b:free (LiquidAI LFM 2.5)")
    print("   4. nvidia/nemotron-3.5-lightning:free (NVIDIA Nemotron 3.5)")
    print("   5. inclusionai/ling-3.0-tiny:free (Ling 3.0 Tiny)")
    print("   6. poolside/laguna-s-2.1:free (Poolside Laguna S 2.1)")
    print("   7. cohere/north-mini-code:free (Cohere North Mini Code)")
    print("   8. Ingresar otro modelo de OpenRouter manualmente")
    print("=" * 70)

    try:
        opcion = input("Selecciona una opción [1-8] (Presiona Enter para '1'): ").strip()
    except (EOFError, KeyboardInterrupt):
        opcion = "1"

    if not opcion:
        opcion = "1"

    if opcion in modelos_opciones:
        return modelos_opciones[opcion]
    elif opcion == "8":
        custom_model = input("Ingresa el identificador completo del modelo en OpenRouter (ej. liquid/lfm-2.5-2.6b:free): ").strip()
        if not custom_model:
            custom_model = "openrouter/free"
        return custom_model, True
    else:
        print("Opción no válida. Usando 'gemini-3.6-flash' por defecto.\n")
        return "gemini-3.6-flash", False


def seleccionar_modo_entrada(source_arg: str | None = None) -> str:
    """
    Permite al usuario seleccionar el formato de entrada del documento para Gemini:
    'pdf' (Subida de archivo PDF a la Files API de Gemini) o
    'markdown' (Texto plano extraído mediante pdf-inspector).
    """
    if source_arg and source_arg.lower().strip() in ("pdf", "markdown"):
        return source_arg.lower().strip()

    print("=" * 70)
    print(" SELECCIÓN DE FUENTE DE ENTRADA (PARA MODELOS GEMINI)")
    print("=" * 70)
    print("   1. PDF Original (Subida de archivo .pdf multimodal a Gemini Files API)")
    print("   2. Texto Markdown (Extraído previamente con pdf-inspector)")
    print("=" * 70)

    try:
        opcion = input("Selecciona la fuente de entrada [1-2] (Presiona Enter para '1'): ").strip()
    except (EOFError, KeyboardInterrupt):
        opcion = "1"

    if opcion == "2":
        return "markdown"
    return "pdf"


def es_seccion_referencias(nombre_seccion: str) -> bool:
    """Verifica si el nombre de la sección corresponde a Referencias o Bibliografía."""
    s = nombre_seccion.lower().strip()
    return "reference" in s or "referencia" in s or "bibliograf" in s


def limpiar_footers_y_headers(texto: str) -> str:
    """Limpia determinísticamente encabezados y pies de página en cualquier paper académico o PDF."""
    if not texto:
        return texto

    pattern_rutas = r'(?i)\b(?:[a-z0-9_\-\.\+\s\\]+[\\\/])+[a-z0-9_\-\.\+\s]+\.(?:doc|docx|pdf|txt|rtf)\b'
    texto = re.sub(pattern_rutas, '', texto)

    pattern_fechas = r'\b\d{2}[-\/\s]\d{2}[-\/\s]\d{4}@\d{2}[\.:]\d{2}\b|\b(?:\d{2,4}[-\/\.]\d{2}[-\/\.]\d{2,4})(?:[@\s,T]\d{1,2}[\.:]\d{2}(?:[\.:]\d{2})?)?\b'
    texto = re.sub(pattern_fechas, '', texto)

    pattern_paginas = r'(?im)^\s*(?:page|pág|página)?\s*\d+(?:\s*(?:of|de|\/)\s*\d+)?\s*$'
    texto = re.sub(pattern_paginas, '', texto)

    pattern_marcas = r'(?im)^\s*(?:downloaded from|accessed from|available online at|copyright|©|all rights reserved).*$'
    texto = re.sub(pattern_marcas, '', texto)

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
                continue
            if isinstance(v, str) and (v == "" or v == "[Sin contenido en documento]"):
                hojas.append((path + [k], obj, k))
            elif isinstance(v, (dict, list)):
                hojas.extend(extraer_nodos_vacios(v, path + [k]))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                hojas.extend(extraer_nodos_vacios(item, path + [str(idx)]))

    return hojas


def llamar_openrouter(openrouter_key: str, modelo: str, prompt: str, pdf_text: str = "") -> str:
    """Envía una solicitud de chat completions a OpenRouter usando urllib."""
    url = "https://openrouter.ai/api/v1/chat/completions"

    contenido_usuario = prompt
    if pdf_text:
        contenido_usuario += f"\n\n=========================================\nDOCUMENTO EN FORMATO MARKDOWN:\n=========================================\n{pdf_text}"

    payload = {
        "model": modelo,
        "messages": [
            {"role": "user", "content": contenido_usuario}
        ],
        "temperature": 0.1,
        "max_tokens": 32000
    }

    headers = {
        "Authorization": f"Bearer {openrouter_key.strip()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/jeframar/genai",
        "X-Title": "GenAI-Schema-App",
        "User-Agent": "GenAI-App/1.0"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=120) as response:
        res_raw = response.read().decode("utf-8")
        data = json.loads(res_raw)
        choices = data.get("choices", [])
        if choices and len(choices) > 0:
            content = choices[0].get("message", {}).get("content", "")
            return (content or "").strip()
        return ""


def extraer_texto_seccion_raw(
    client: genai.Client | None,
    file_ref,
    pdf_text: str,
    nombre_seccion: str,
    ruta_contexto: list[str],
    modelo: str,
    es_openrouter: bool,
    modo_entrada: str = "pdf",
    openrouter_key: str = ""
) -> str:
    """Extrae el texto crudo y literal de un bloque/sección sin realizar corrección ortográfica o gramatical."""
    contexto_str = " > ".join([p for p in ruta_contexto if not p.isdigit()])

    prompt = f"""Analiza el contenido del documento PDF fuente y la estructura esperada en la plantilla 'schema.json'.

TU TAREA:
Ubicándote en la estructura de 'schema.json', extrae el texto crudo y literal completo que corresponde a la clave/sección: "{nombre_seccion}".
Ruta jerárquica exacta en schema.json: {contexto_str}

REGLAS CRÍTICAS DE EXTRACCIÓN:
1. EXTRACCIÓN LITERAL SIN CORRECCIÓN ORTOGRÁFICA: Extrae el texto EXACTAMENTE como aparece en el documento original. NO realices correcciones ortográficas, gramaticales, sintácticas ni tipográficas. Si el original tiene erratas, errores de tipeo, falta de tildes o palabras mal escritas, consérvalas intactas tal cual están.
2. ALINEACIÓN CON LA ESTRUCTURA DEL SCHEMA: Busca en el texto del documento el fragmento correspondiente a la sección "{nombre_seccion}" guiándote por la jerarquía [{contexto_str}]. Identifica e incluye el texto perteneciente a dicha sección aunque carezca de un encabezado explícito impreso.
3. OMITE PIES Y ENCABEZADOS DE PÁGINA (FOOTERS/HEADERS): Ignora y elimina cualquier pie de página, rutas de archivo local, marcas de agua, fechas de impresión/descarga o números de página repetitivos.
4. NO INCLUYAS EL TÍTULO AL INICIO DEL TEXTO: No repitas el título de la sección ("{nombre_seccion}") dentro del cuerpo del texto extraído. Comienza directamente con el contenido del primer párrafo.
5. NO RESUMIR NI PARAFRASEAR: Extrae todo el contenido original perteneciente a dicha sección sin resumir, omitir ni reescribir.
6. FORMATO DE SALIDA: Devuelve exclusivamente un objeto JSON válido con la clave "texto" para ser insertado en 'schema_completado.json'.

EJEMPLO DE SALIDA:
{{
  "texto": "Texto literal del documento correspondiente a esta clave del schema..."
}}"""

    if es_openrouter:
        texto_bruto = llamar_openrouter(openrouter_key, modelo, prompt, pdf_text)
    elif modo_entrada == "markdown":
        contenido_prompt = prompt + f"\n\n=========================================\nDOCUMENTO EN FORMATO MARKDOWN:\n=========================================\n{pdf_text}"
        response = client.models.generate_content(
            model=modelo,
            contents=[contenido_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=20000
            )
        )
        texto_bruto = (response.text or "").strip()
    else: # modo_entrada == "pdf"
        response = client.models.generate_content(
            model=modelo,
            contents=[file_ref, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=20000
            )
        )
        texto_bruto = (response.text or "").strip()

    if not texto_bruto:
        return "[Sin contenido en documento]"

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
    client: genai.Client | None,
    file_ref,
    pdf_text: str,
    nombre_seccion: str,
    ruta_contexto: list[str],
    modelo: str,
    es_openrouter: bool,
    modo_entrada: str = "pdf",
    openrouter_key: str = "",
    max_reintentos: int = 3,
    espera_segundos: float = 4.0
) -> str:
    """Intenta extraer la sección con reintentos exponenciales ante errores de red, servidor o límite de cuota (429)."""
    intentos_totales = max_reintentos + 1
    ultimo_error = None

    for intento in range(1, intentos_totales + 1):
        try:
            return extraer_texto_seccion_raw(
                client=client,
                file_ref=file_ref,
                pdf_text=pdf_text,
                nombre_seccion=nombre_seccion,
                ruta_contexto=ruta_contexto,
                modelo=modelo,
                es_openrouter=es_openrouter,
                modo_entrada=modo_entrada,
                openrouter_key=openrouter_key
            )
        except Exception as e:
            ultimo_error = e
            err_msg = str(e)
            
            tiempo_espera = 10.0 if ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Rate Limit" in err_msg) else espera_segundos

            if intento < intentos_totales:
                print(f"\n   [Aviso] Pausa en intento {intento}/{intentos_totales} (Límite temporal / Servidor). Esperando {tiempo_espera}s...", end="", flush=True)
                time.sleep(tiempo_espera)

    raise RuntimeError(f"Fallo persistente tras {intentos_totales} intentos: {ultimo_error}")


def subir_pdf_con_reintentos(client: genai.Client, pdf_path: str, max_reintentos: int = 3, espera_segundos: float = 8.0):
    """Sube el archivo PDF a Gemini con manejo de reintentos ante errores de cuota (429)."""
    for intento in range(1, max_reintentos + 2):
        try:
            return client.files.upload(file=pdf_path)
        except Exception as e:
            err_msg = str(e)
            if intento <= max_reintentos and ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "Quota" in err_msg):
                print(f"   [Aviso] Límite de cuota detectado al subir el PDF. Esperando {espera_segundos}s (intento {intento}/{max_reintentos + 1})...", flush=True)
                time.sleep(espera_segundos)
            else:
                raise e


def guardar_progreso(output_files: list[Path], data: dict):
    """Guarda inmediatamente la estructura actual en los archivos de salida especificados."""
    for output_file in output_files:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Extrae el texto de cada bloque y completa schema_completado.json sin corrección ortográfica.")
    parser.add_argument("pdf_path", nargs="?", default=None, help="Ruta al archivo PDF. Si se omite, abre un explorador de archivos.")
    parser.add_argument("-m", "--model", default=None, help="Nombre del modelo (ej. 'gemini-3.6-flash' o 'openrouter/free').")
    parser.add_argument("-s", "--source", choices=["pdf", "markdown"], default=None, help="Fuente de entrada para Gemini: 'pdf' u 'markdown'.")
    args = parser.parse_args()

    # Seleccionar modelo (Interactivo o CLI)
    modelo, es_openrouter = seleccionar_modelo(args.model)
    print(f"\nModelo seleccionado: {modelo} {'(OpenRouter)' if es_openrouter else '(Gemini API)'}")

    # Si es un modelo de Gemini, permitir al usuario seleccionar entre PDF o Markdown
    modo_entrada = "markdown" if es_openrouter else seleccionar_modo_entrada(args.source)
    if not es_openrouter:
        print(f"Modo de entrada seleccionado: {'PDF Original (Files API)' if modo_entrada == 'pdf' else 'Texto Markdown (pdf-inspector)'}")

    # Validar API key según el proveedor seleccionado
    gemini_key = os.environ.get("GEMINI_API_KEY")
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")

    if es_openrouter:
        if not openrouter_key:
            print("Error: No se encontró OPENROUTER_API_KEY en el entorno o archivo .env.")
            sys.exit(1)
    else:
        if not gemini_key:
            print("Error: No se encontró GEMINI_API_KEY en el entorno o archivo .env.")
            sys.exit(1)

    repo_dir = Path(__file__).parent.resolve()
    schema_file = repo_dir / "schema.json"
    output_file_progreso = repo_dir / "schema_completado.json"

    archivos_salida = [output_file_progreso]

    # 1. Verificar existencia de schema.json
    if not schema_file.exists():
        print(f"Error: No se encontró el archivo '{schema_file.name}' en la raíz del repositorio.")
        print("Por favor ejecuta primero 'generar_schema.py' para generar la estructura.")
        sys.exit(1)

    # 2. Cargar estado (Reanudación si schema_completado.json ya existe)
    if output_file_progreso.exists():
        print(f"Detectado archivo de avance previo: '{output_file_progreso.name}'. Cargando estado actual...")
        with open(output_file_progreso, "r", encoding="utf-8") as f:
            working_data = json.load(f)
    else:
        print(f"Cargando plantilla inicial desde: '{schema_file.name}'...")
        with open(schema_file, "r", encoding="utf-8") as f:
            working_data = json.load(f)

    # Limpiar cualquier footer o referencia previa en working_data
    limpiar_referencias_y_footers_en_data(working_data)
    guardar_progreso(archivos_salida, working_data)

    # 3. Identificar secciones pendientes por extraer (excluyendo referencias)
    secciones_pendientes = extraer_nodos_vacios(working_data)
    total_pendientes = len(secciones_pendientes)

    if total_pendientes == 0:
        print(f"\n¡Todas las secciones ya están completadas! (Sección de Referencias excluida por regla).")
        print(f"Resultado guardado en '{output_file_progreso.name}'.")
        sys.exit(0)

    # 4. Seleccionar el archivo PDF fuente (CLI o GUI)
    pdf_path = args.pdf_path
    if not pdf_path:
        pdf_path = seleccionar_pdf()
        if not pdf_path:
            print("Operación cancelada: No se seleccionó ningún archivo PDF.")
            sys.exit(0)

    print(f"\nPDF seleccionado: {pdf_path}")
    print(f"Secciones pendientes por procesar: {total_pendientes}\n")

    # 5. Preparar acceso al documento según el proveedor y modo de entrada
    client = None
    file_ref = None
    pdf_text = ""

    try:
        if es_openrouter or modo_entrada == "markdown":
            print("Extrayendo texto del PDF a Markdown...")
            if HAS_PDF_INSPECTOR:
                pdf_res = pdf_inspector.process_pdf(str(pdf_path))
                pdf_text = pdf_res.markdown or ""
            else:
                with open(pdf_path, "rb") as f:
                    pdf_text = f.read().decode("utf-8", errors="ignore")
            print(f"Texto Markdown preparado ({len(pdf_text):,} caracteres).\n")

        if not es_openrouter:
            client = genai.Client()
            if modo_entrada == "pdf":
                print("Subiendo PDF a la API de Gemini...")
                file_ref = subir_pdf_con_reintentos(client, pdf_path)
                print(f"Archivo subido con éxito (ID: {file_ref.name})\n")

        print("=" * 70)
        print(" INICIANDO EXTRACCIÓN DE TEXTO BLOQUE A BLOQUE (SIN CORRECCIÓN ORTOGRÁFICA)")
        print("=" * 70)

        start_total_time = time.perf_counter()

        # 6. Procesar secciones pendientes
        for index, (ruta, parent_dict, clave) in enumerate(secciones_pendientes, start=1):
            print(f"[{index}/{total_pendientes}] Extrayendo bloque: '{clave}'...", end="", flush=True)

            start_sec_time = time.perf_counter()
            texto_extraido = extraer_texto_seccion_con_reintentos(
                client=client,
                file_ref=file_ref,
                pdf_text=pdf_text,
                nombre_seccion=clave,
                ruta_contexto=ruta,
                modelo=modelo,
                es_openrouter=es_openrouter,
                modo_entrada=modo_entrada,
                openrouter_key=openrouter_key,
                max_reintentos=3,
                espera_segundos=4.0
            )
            sec_elapsed = time.perf_counter() - start_sec_time

            # Asignar texto crudo extraído
            parent_dict[clave] = texto_extraido if texto_extraido else "[Sin contenido en documento]"

            # GUARDAR PROGRESO INMEDIATAMENTE EN schema_completado.json
            guardar_progreso(archivos_salida, working_data)

            print(f" OK ({sec_elapsed:.2f}s | {len(texto_extraido):,} caracteres)")

        total_elapsed = time.perf_counter() - start_total_time

        print("=" * 70)
        print(f" Extracción completada en {total_elapsed:.2f} segundos en total.")
        print("=" * 70)
        print(f"\n¡Éxito! Texto extraído y guardado exclusivamente en:")
        print(f" - {output_file_progreso.name}")

    except Exception as e:
        print(f"\n\nOcurrió un error interrumpiendo el proceso: {e}")
        print(f"¡Atención! El progreso alcanzado fue guardado automáticamente.")
        sys.exit(1)
    finally:
        if file_ref and client:
            try:
                client.files.delete(name=file_ref.name)
                print("Archivo temporal limpiado de Gemini storage.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
