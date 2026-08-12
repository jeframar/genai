import os
import sys
import json
import time
import re
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
import json_repair

# Cargar variables de entorno (.env)
load_dotenv()


def es_seccion_referencias(nombre_seccion: str) -> bool:
    """Verifica si el nombre de la sección corresponde a Referencias o Bibliografía."""
    s = nombre_seccion.lower().strip()
    return "reference" in s or "referencia" in s or "bibliograf" in s


def extraer_nodos_texto(obj, path=None):
    """Encuentra de forma recursiva todos los nodos hoja que contienen texto a traducir."""
    if path is None:
        path = []
    hojas = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "titulo y subtitulo":
                if isinstance(v, str) and v.strip():
                    hojas.append((path + [k], obj, k, v))
            elif es_seccion_referencias(k):
                continue  # Omitir traducción de referencias
            elif isinstance(v, str) and v.strip() and v != "[Sin contenido en documento]":
                hojas.append((path + [k], obj, k, v))
            elif isinstance(v, (dict, list)):
                hojas.extend(extraer_nodos_texto(v, path + [k]))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                hojas.extend(extraer_nodos_texto(item, path + [str(idx)]))

    return hojas


def traducir_y_depurar_bloque(client: genai.Client, texto_original: str, nombre_seccion: str, ruta_contexto: list[str]) -> str:
    """
    Realiza 1 llamada a la API de Gemini por contenido para:
    1. Revisar y retirar fragmentos incoherentes (encabezados, footers, rutas de archivos, números de página).
    2. Traducir el contenido resultante al español académico.
    """
    contexto_str = " > ".join([p for p in ruta_contexto if not p.isdigit()])

    prompt = f"""Analiza el siguiente fragmento de texto correspondiente a la sección "{nombre_seccion}" (Ubicación: {contexto_str}).

TU TAREA CONSTA DE DOS PASOS OBLIGATORIOS:

PASO 1: DEPURACIÓN DE FRAGMENTOS INCOHERENTES (FOOTERS / HEADERS / MARCAS DE AGUA):
Inspecciona minuciosamente el texto en busca de cualquier fragmento fuera de contexto o incoherente que se haya colado del PDF original:
- Encabezados de página, pies de página o títulos corrientes de la revista.
- Números de página aislados (ej. "Page 12 of 30", "Página 5", "12").
- Rutas de archivo o marcas de agua de descarga (ej. "Downloaded from...", "http://...", "suwr\\SW2\\...").
- Fechas/horas de impresión o licencias de derechos de autor.
Si encuentras alguno de estos fragmentos incoherentes, RETÍRALO Y ELIMÍNALO por completo del cuerpo del texto antes de traducir.

PASO 2: TRADUCCIÓN AL ESPAÑOL ACADÉMICO:
Traduce el texto limpio resultante al español con un estilo académico, riguroso, fluido y preciso.
- Mantiene la terminología técnica adecuada del campo de estudio.
- Conserva el significado original sin resumir ni omitir ideas.
- Mantiene la división de párrafos original.

TEXTO ORIGINAL A PROCESAR:
\"\"\"
{texto_original}
\"\"\"

FORMATO DE SALIDA:
Devuelve exclusivamente un objeto JSON válido con la siguiente estructura:
{{
  "texto_traducido": "Texto limpio y traducido al español..."
}}"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
            max_output_tokens=8192
        )
    )

    texto_bruto = response.text.strip()
    try:
        data = json.loads(texto_bruto, strict=False)
        res_texto = data.get("texto_traducido", texto_bruto)
    except Exception:
        data_reparada = json_repair.repair_json(texto_bruto, return_objects=True)
        if isinstance(data_reparada, dict):
            res_texto = data_reparada.get("texto_traducido", str(data_reparada))
        else:
            res_texto = str(data_reparada)

    return res_texto.strip()


def traducir_bloque_con_reintentos(
    client: genai.Client,
    texto_original: str,
    nombre_seccion: str,
    ruta_contexto: list[str],
    max_reintentos: int = 3,
    espera_segundos: float = 3.0
) -> str:
    """Ejecuta la llamada a la API con control de reintentos e interrupción por límite de cuota (429)."""
    intentos_totales = max_reintentos + 1
    ultimo_error = None

    for intento in range(1, intentos_totales + 1):
        try:
            return traducir_y_depurar_bloque(client, texto_original, nombre_seccion, ruta_contexto)
        except Exception as e:
            ultimo_error = e
            err_msg = str(e)
            tiempo_espera = 12.0 if ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg) else espera_segundos

            if intento < intentos_totales:
                print(f"\n   [Aviso] Pausa en intento {intento}/{intentos_totales} (Límite temporal / Servidor). Esperando {tiempo_espera}s...", end="", flush=True)
                time.sleep(tiempo_espera)

    raise RuntimeError(f"Fallo persistente tras {intentos_totales} intentos: {ultimo_error}")


def remover_titulo_duplicado(clave: str, contenido: str) -> str:
    """Elimina títulos repetidos al inicio del párrafo traducido."""
    if not clave or not contenido:
        return contenido
    texto_strip = contenido.lstrip()
    clave_clean = clave.strip()
    if texto_strip.lower().startswith(clave_clean.lower()):
        resto = texto_strip[len(clave_clean):].lstrip()
        resto = re.sub(r'^[:\-\s\n]+', '', resto)
        return resto
    return contenido


def convertir_json_a_markdown(data: dict) -> str:
    """Convierte recursivamente la estructura JSON traducida a un documento Markdown bien formateado y organizado."""
    md_lines = []

    # 1. Título principal del documento (# Level 1)
    titulo_principal = data.get("titulo y subtitulo")
    if titulo_principal:
        md_lines.append(f"# {titulo_principal}\n")

    # 2. Procesar capítulos y secciones jerárquicas
    capitulos = data.get("capitulo o seccion", {})

    def procesar_nodo(nodo, level=2):
        if isinstance(nodo, dict):
            for clave, valor in nodo.items():
                if clave.isdigit() and isinstance(valor, dict):
                    procesar_nodo(valor, level)
                elif isinstance(valor, str):
                    hashes = "#" * min(level, 6)
                    md_lines.append(f"{hashes} {clave}\n")
                    contenido_limpio = remover_titulo_duplicado(clave, valor.strip())
                    if contenido_limpio and contenido_limpio != "[Sin contenido en documento]":
                        md_lines.append(f"{contenido_limpio}\n")
                    else:
                        md_lines.append("*(Sin contenido)*\n")
                elif isinstance(valor, dict):
                    hashes = "#" * min(level, 6)
                    md_lines.append(f"{hashes} {clave}\n")
                    procesar_nodo(valor, level + 1)
        elif isinstance(nodo, str):
            md_lines.append(f"{nodo.strip()}\n")

    procesar_nodo(capitulos, level=2)
    return "\n".join(md_lines)


def guardar_progreso(output_file: Path, data: dict):
    """Guarda inmediatamente la estructura traducida en texto_final_espanol.json."""
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No se encontró GEMINI_API_KEY en el entorno o en el archivo .env.")
        sys.exit(1)

    import argparse
    parser = argparse.ArgumentParser(description="Depura fragmentos incoherentes y traduce schema_completado.json al español.")
    parser.add_argument("input_json", nargs="?", default=None, help="Archivo JSON de entrada (por defecto: 'schema_completado.json').")
    parser.add_argument("-o", "--output", default=None, help="Archivo JSON traducido de salida (por defecto: 'schema_completado_espanol.json').")
    args = parser.parse_args()

    repo_dir = Path(__file__).parent.resolve()
    
    if args.input_json:
        input_file = Path(args.input_json)
    else:
        input_file = repo_dir / "schema_completado.json"
        if not input_file.exists():
            input_file = repo_dir / "texto_final.json"

    if not input_file.exists():
        print("Error: No se encontró 'schema_completado.json' ni 'texto_final.json'.")
        print("Ejecuta primero 'python completar_schema.py'.")
        sys.exit(1)

    if args.output:
        output_json_file = Path(args.output)
    else:
        output_json_file = repo_dir / "schema_completado_espanol.json"

    output_md_file = repo_dir / "schema_completado_espanol.md"

    print(f"Cargando archivo de entrada: {input_file.name}...")
    with open(input_file, "r", encoding="utf-8") as f:
        input_data = json.load(f)

    # 1. Reanudación si texto_final_espanol.json ya existe parcialmente
    if output_json_file.exists():
        print(f"Detectado avance previo en: '{output_json_file.name}'. Cargando estado actual...")
        with open(output_json_file, "r", encoding="utf-8") as f:
            working_data = json.load(f)
    else:
        working_data = json.loads(json.dumps(input_data))  # Copia profunda de la estructura original

    # Identificar bloques de texto a traducir
    nodos_originales = extraer_nodos_texto(input_data)
    nodos_trabajo = extraer_nodos_texto(working_data)

    # Filtrar nodos que aún no han sido traducidos (donde el valor en working_data es igual al inglés original)
    pendientes = []
    for i, (path, parent_dict, clave, orig_val) in enumerate(nodos_originales):
        trabajo_val = nodos_trabajo[i][3]
        if trabajo_val == orig_val:
            pendientes.append((path, nodos_trabajo[i][1], clave, orig_val))

    total_pendientes = len(pendientes)
    total_bloques = len(nodos_originales)

    print(f"Total de bloques de contenido a procesar: {total_bloques}")
    print(f"Bloques pendientes por traducir:         {total_pendientes}\n")

    if total_pendientes > 0:
        client = genai.Client()

        print("=" * 75)
        print(" INICIANDO DEPURACIÓN DE INCOHERENCIAS Y TRADUCCIÓN AL ESPAÑOL POR BLOQUE")
        print("=" * 75)

        start_total_time = time.perf_counter()

        for idx, (ruta, parent_dict, clave, texto_original) in enumerate(pendientes, start=1):
            print(f"[{idx}/{total_pendientes}] Depurando y traduciendo: '{clave}'...", end="", flush=True)

            start_sec_time = time.perf_counter()
            texto_traducido = traducir_bloque_con_reintentos(
                client=client,
                texto_original=texto_original,
                nombre_seccion=clave,
                ruta_contexto=ruta,
                max_reintentos=3,
                espera_segundos=3.0
            )
            sec_elapsed = time.perf_counter() - start_sec_time

            # Asignar texto traducido y depurado
            parent_dict[clave] = texto_traducido

            # GUARDAR PROGRESO INCREMENTALMENTE TRAS CADA LLAMADA DE API
            guardar_progreso(output_json_file, working_data)

            print(f" OK ({sec_elapsed:.2f}s | {len(texto_traducido):,} caracteres)")

        total_elapsed = time.perf_counter() - start_total_time
        print("=" * 75)
        print(f" Traducción completada en {total_elapsed:.2f} segundos en total.")
        print("=" * 75)
    else:
        print("¡Todos los bloques ya han sido traducidos previamente en 'texto_final_espanol.json'!\n")

    # 2. GENERAR EL DOCUMENTO MARKDOWN FINAL ORGANIZADO CON JERARQUÍAS
    print("Generando documento Markdown estructurado al español...")
    markdown_content = convertir_json_a_markdown(working_data)

    with open(output_md_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"\n¡Éxito! Proceso completado:")
    print(f" - Archivo JSON traducido:     {output_json_file.name}")
    print(f" - Archivo Markdown generado:  {output_md_file.name}")

    print("\n" + "=" * 60)
    print(" PREVIEW DEL DOCUMENTO MARKDOWN TRADUCIDO")
    print("=" * 60)
    lineas_preview = markdown_content.splitlines()[:25]
    print("\n".join(lineas_preview))
    if len(markdown_content.splitlines()) > 25:
        print("\n... [contenido adicional guardado en texto_final_espanol.md] ...")
    print("=" * 60)


if __name__ == "__main__":
    main()
