import json
import sys
import argparse
from pathlib import Path


def convertir_json_a_markdown_raw(data: dict) -> str:
    """
    Convierte la estructura JSON jerárquica a un documento Markdown respetando los niveles (#, ##, ###)
    SIN REALIZAR NINGUNA LIMPIEZA, filtrado ni modificación en el texto de los bloques.
    """
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
                # Si la clave es un número de capítulo (ej. "1", "2"), procesamos su hijo manteniendo el nivel
                if clave.isdigit() and isinstance(valor, dict):
                    procesar_nodo(valor, level)
                elif isinstance(valor, str):
                    es_presentacion = (clave.strip().lower() == "presentacion")
                    if not es_presentacion:
                        # Título de sección / subsección
                        hashes = "#" * min(level, 6)
                        md_lines.append(f"{hashes} {clave}\n")
                    
                    # Conservar el texto crudo exactamente como está en el JSON (sin limpieza ni modificación)
                    if valor and valor != "[Sin contenido en documento]":
                        md_lines.append(f"{valor}\n")
                    else:
                        if not es_presentacion:
                            md_lines.append("*(Sin contenido)*\n" if valor == "[Sin contenido en documento]" else "\n")
                elif isinstance(valor, dict):
                    hashes = "#" * min(level, 6)
                    md_lines.append(f"{hashes} {clave}\n")
                    procesar_nodo(valor, level + 1)
        elif isinstance(nodo, str):
            if nodo:
                md_lines.append(f"{nodo}\n")

    procesar_nodo(capitulos, level=2)
    return "\n".join(md_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convierte un archivo JSON jerárquico a Markdown directo SIN realizar ninguna limpieza ni filtrado de texto."
    )
    parser.add_argument(
        "input_json",
        nargs="?",
        default=None,
        help="Ruta al archivo JSON de entrada. Si se omite, busca 'texto_final.json', 'schema_completado.json' o 'schema.json'."
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Ruta al archivo Markdown de salida (por defecto: 'texto_final_raw.md')."
    )

    args = parser.parse_args()
    repo_dir = Path(__file__).parent.resolve()

    # 1. Determinar archivo JSON de entrada
    if args.input_json:
        archivo_json = Path(args.input_json)
    else:
        archivo_json = repo_dir / "schema_completado_espanol.json"
        if not archivo_json.exists():
            archivo_json = repo_dir / "schema_completado.json"
        if not archivo_json.exists():
            archivo_json = repo_dir / "texto_final.json"
        if not archivo_json.exists():
            archivo_json = repo_dir / "schema.json"

    if not archivo_json.exists():
        print("Error: No se encontró ningún archivo JSON de entrada ('schema_completado_espanol.json', 'schema_completado.json' o 'schema.json').")
        sys.exit(1)

    # 2. Determinar archivo Markdown de salida
    if args.output:
        output_file = Path(args.output)
    else:
        output_file = repo_dir / "texto_final_raw.md"

    print(f"Cargando datos desde: {archivo_json.name}...")
    with open(archivo_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 3. Convertir directamente a Markdown sin ninguna limpieza
    markdown_content = convertir_json_a_markdown_raw(data)

    # 4. Guardar archivo Markdown
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"\n¡Éxito! Documento Markdown crudo generado en: {output_file.name}")
    print("\n" + "=" * 60)
    print(" PREVIEW DEL MARKDOWN CRUDO GENERADO (SIN LIMPIEZA)")
    print("=" * 60)

    lineas_preview = markdown_content.splitlines()[:30]
    print("\n".join(lineas_preview))
    if len(markdown_content.splitlines()) > 30:
        print(f"\n... [contenido adicional guardado en {output_file.name}] ...")
    print("=" * 60)


if __name__ == "__main__":
    main()
