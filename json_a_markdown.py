import json
import sys
import re
from pathlib import Path


def limpiar_footers_y_headers(texto: str) -> str:
    """Elimina determinísticamente pies de página, rutas de archivos locales y fechas de impresión coladas."""
    if not texto:
        return texto

    # 1. Eliminar rutas de archivos del footer (ej. suwr\SW2\Audit book\... .doc / .pdf)
    texto = re.sub(r'(?i)(?:[a-z0-9_-]+\\)+[^\n]*?\.(?:doc|docx|pdf|txt)', '', texto)

    # 2. Eliminar marcas de fecha/hora de impresión (ej. 20-07-2014@22.32)
    texto = re.sub(r'\b\d{2}-\d{2}-\d{4}@\d{2}[\.:]\d{2}\b', '', texto)

    # 3. Limpiar líneas vacías sobrantes dejadas por los pies de página eliminados
    lineas = [linea.strip() for linea in texto.splitlines()]
    resultado = []
    for l in lineas:
        if l:
            resultado.append(l)
        elif resultado and resultado[-1] != "":
            resultado.append("")

    return "\n".join(resultado).strip()


def convertir_json_a_markdown(data: dict) -> str:
    """Convierte recursivamente la estructura JSON jerárquica a un documento Markdown bien formateado y limpio."""
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
                    # Título de sección / subsección
                    hashes = "#" * min(level, 6)
                    md_lines.append(f"{hashes} {clave}\n")
                    
                    contenido_limpio = limpiar_footers_y_headers(valor)
                    if contenido_limpio and contenido_limpio != "[Sin contenido en documento]":
                        md_lines.append(f"{contenido_limpio}\n")
                    else:
                        # Si el campo está en blanco, se conserva el título y se deja una línea libre
                        md_lines.append("*(Sin contenido)*\n" if contenido_limpio == "[Sin contenido en documento]" else "\n")
                elif isinstance(valor, dict):
                    hashes = "#" * min(level, 6)
                    md_lines.append(f"{hashes} {clave}\n")
                    procesar_nodo(valor, level + 1)
        elif isinstance(nodo, str):
            contenido_limpio = limpiar_footers_y_headers(nodo)
            if contenido_limpio:
                md_lines.append(f"{contenido_limpio}\n")

    procesar_nodo(capitulos, level=2)
    return "\n".join(md_lines)


def main():
    repo_dir = Path(__file__).parent.resolve()
    archivo_json = repo_dir / "texto_final.json"
    
    # Si no existe texto_final.json, intentar usar schema.json como fallback
    if not archivo_json.exists():
        schema_file = repo_dir / "schema.json"
        if schema_file.exists():
            print(f"Aviso: No se encontró '{archivo_json.name}'. Usando '{schema_file.name}' para generar el preview Markdown...")
            archivo_json = schema_file
        else:
            print("Error: No se encontró 'texto_final.json' ni 'schema.json' en el repositorio.")
            sys.exit(1)

    print(f"Cargando datos desde: {archivo_json.name}...")
    with open(archivo_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Convertir a formato Markdown con limpieza de footers
    markdown_content = convertir_json_a_markdown(data)

    # Guardar en texto_final.md
    output_file = repo_dir / "texto_final.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"\n¡Éxito! Documento Markdown generado correctamente en: {output_file.name}")
    print("\n" + "=" * 55)
    print(" PREVIEW DEL DOCUMENTO MARKDOWN GENERADO (SIN FOOTERS)")
    print("=" * 55)
    
    # Imprimir las primeras 30 líneas como preview
    lineas_preview = markdown_content.splitlines()[:30]
    print("\n".join(lineas_preview))
    if len(markdown_content.splitlines()) > 30:
        print("\n... [contenido adicional guardado en texto_final.md] ...")
    print("=" * 55)


if __name__ == "__main__":
    main()
