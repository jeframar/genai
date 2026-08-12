import os
import sys
import json
import subprocess
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

STATE_FILE = Path(__file__).parent.resolve() / ".pipeline_state.json"
REPO_DIR = Path(__file__).parent.resolve()


def seleccionar_pdf_gui() -> str | None:
    """Abre el diálogo nativo para seleccionar el archivo PDF fuente."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    print("Abriendo explorador de archivos para seleccionar el PDF...")
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo PDF para el pipeline GenAI",
        filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
    )
    root.destroy()
    return file_path if file_path else None


def cargar_estado() -> dict:
    """Carga el estado del último PDF seleccionado."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def guardar_estado(estado: dict):
    """Guarda el estado del PDF actual."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def ejecutar_script(script_name: str, args_list: list[str] = None) -> bool:
    """Ejecuta un script de Python del pipeline mostrando la salida en tiempo real."""
    cmd = [sys.executable, str(REPO_DIR / script_name)]
    if args_list:
        cmd.extend(args_list)

    print(f"\n>>> Ejecutando: {' '.join(cmd)}\n")
    try:
        resultado = subprocess.run(cmd, check=True)
        return resultado.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n[Error] El script '{script_name}' finalizó con código de error: {e.returncode}")
        return False
    except Exception as e:
        print(f"\n[Error] No se pudo ejecutar el script '{script_name}': {e}")
        return False


def paso_1_generar_schema(pdf_path: str) -> bool:
    """Paso 1: Genera schema.json"""
    print("\n" + "=" * 70)
    print(" PASO 1: GENERAR ESTRUCTURA JERÁRQUICA (schema.json)")
    print("=" * 70)
    exito = ejecutar_script("generar_schema.py", [pdf_path])
    if exito:
        print("\n[OK] Paso 1 completado. Se ha generado 'schema.json'.")
        print("💡 Puedes abrir y revisar 'schema.json' antes de continuar al Paso 2.")
    return exito


def paso_2_completar_schema(pdf_path: str) -> bool:
    """Paso 2: Extrae texto crudo bloque a bloque y genera schema_completado.json"""
    print("\n" + "=" * 70)
    print(" PASO 2: EXTRAER TEXTO BLOQUE A BLOQUE (schema_completado.json)")
    print("=" * 70)
    exito = ejecutar_script("completar_schema.py", [pdf_path])
    if exito:
        print("\n[OK] Paso 2 completado. Se ha generado exclusivamente 'schema_completado.json'.")
    return exito


def paso_3_traducir_texto() -> bool:
    """Paso 3: Depura fragmentos incoherentes y traduce schema_completado.json al español"""
    print("\n" + "=" * 70)
    print(" PASO 3: DEPURACIÓN Y TRADUCCIÓN AL ESPAÑOL (schema_completado_espanol.json)")
    print("=" * 70)
    input_file = REPO_DIR / "schema_completado.json"
    if not input_file.exists():
        print("Error: No existe 'schema_completado.json'. Por favor ejecuta primero el Paso 2.")
        return False

    exito = ejecutar_script("traducir_texto.py", [str(input_file)])
    if exito:
        print("\n[OK] Paso 3 completado. Se ha generado 'schema_completado_espanol.json'.")
    return exito


def paso_4_json_a_markdown_raw(pdf_stem: str) -> bool:
    """Paso 4: Convierte el JSON a Markdown Raw renombrando con el nombre base del PDF"""
    print("\n" + "=" * 70)
    print(f" PASO 4: EXPORTAR A MARKDOWN RAW ({pdf_stem}.md)")
    print("=" * 70)

    # Determinar si existe versión traducida o versión completada en inglés
    json_traducido = REPO_DIR / "schema_completado_espanol.json"
    json_completado = REPO_DIR / "schema_completado.json"

    if json_traducido.exists():
        input_json = json_traducido
        output_md = REPO_DIR / f"{pdf_stem}_espanol.md"
    elif json_completado.exists():
        input_json = json_completado
        output_md = REPO_DIR / f"{pdf_stem}.md"
    else:
        print("Error: No se encontró 'schema_completado_espanol.json' ni 'schema_completado.json'.")
        print("Ejecuta primero los pasos anteriores.")
        return False

    exito = ejecutar_script("json_a_markdown_raw.py", [str(input_json), "-o", str(output_md)])
    if exito:
        print(f"\n[OK] Paso 4 completado. Se ha generado el documento Markdown final: '{output_md.name}'.")
    return exito


def main():
    estado = cargar_estado()
    pdf_path = estado.get("pdf_path")

    # Si no hay PDF registrado o el archivo no existe, solicitar selección
    if not pdf_path or not Path(pdf_path).exists():
        print("\nNo hay un PDF seleccionado actualmente.")
        pdf_path = seleccionar_pdf_gui()
        if not pdf_path:
            print("Operación cancelada: No se seleccionó ningún PDF.")
            sys.exit(0)

    pdf_obj = Path(pdf_path)
    pdf_stem = pdf_obj.stem  # Nombre base del archivo sin extensión

    estado["pdf_path"] = str(pdf_obj.resolve())
    estado["pdf_stem"] = pdf_stem
    guardar_estado(estado)

    while True:
        print("\n" + "=" * 75)
        print("         ORQUESTADOR DEL PIPELINE DE DOCUMENTOS (GENAI APP)")
        print("=" * 75)
        print(f" PDF Seleccionado:  {pdf_obj.name}")
        print(f" Ruta Completa:     {pdf_path}")
        print(f" Nombre Salida MD:  {pdf_stem}.md")
        print("=" * 75)
        print(" Selecciona una opción:")
        print("   1. [Paso 1] Generar Esquema Jerárquico (generar_schema.py -> schema.json)")
        print("   2. [Paso 2] Extraer Texto Crudo por Bloques (completar_schema.py -> schema_completado.json)")
        print("   3. [Paso 3] Depurar Incoherencias y Traducir al Español (traducir_texto.py -> schema_completado_espanol.json)")
        print("   4. [Paso 4] Exportar a Markdown Raw (json_a_markdown_raw.py -> " + pdf_stem + ".md)")
        print("   5. [Flujo Completo] Ejecutar TODOS los pasos secuencialmente (1 -> 2 -> 3 -> 4)")
        print("   6. Cambiar archivo PDF seleccionado")
        print("   7. Salir")
        print("=" * 75)

        opcion = input("Ingresa el número de tu opción (1-7): ").strip()

        if opcion == "1":
            paso_1_generar_schema(pdf_path)
            input("\nPresiona ENTER para volver al menú...")

        elif opcion == "2":
            paso_2_completar_schema(pdf_path)
            input("\nPresiona ENTER para volver al menú...")

        elif opcion == "3":
            paso_3_traducir_texto()
            input("\nPresiona ENTER para volver al menú...")

        elif opcion == "4":
            paso_4_json_a_markdown_raw(pdf_stem)
            input("\nPresiona ENTER para volver al menú...")

        elif opcion == "5":
            print("\n>>> INICIANDO FLUJO COMPLETO DEL PIPELINE...\n")
            if paso_1_generar_schema(pdf_path):
                if paso_2_completar_schema(pdf_path):
                    if paso_3_traducir_texto():
                        paso_4_json_a_markdown_raw(pdf_stem)
            input("\nPresiona ENTER para volver al menú...")

        elif opcion == "6":
            nuevo_pdf = seleccionar_pdf_gui()
            if nuevo_pdf and Path(nuevo_pdf).exists():
                pdf_path = nuevo_pdf
                pdf_obj = Path(pdf_path)
                pdf_stem = pdf_obj.stem
                estado["pdf_path"] = str(pdf_obj.resolve())
                estado["pdf_stem"] = pdf_stem
                guardar_estado(estado)
                print(f"\nPDF cambiado a: {pdf_obj.name}")
            else:
                print("\nNo se realizó ningún cambio de PDF.")

        elif opcion == "7":
            print("\n¡Gracias por usar la app GenAI! Hasta luego.\n")
            break
        else:
            print("\nOpción no válida. Por favor ingresa un número del 1 al 7.")


if __name__ == "__main__":
    main()
