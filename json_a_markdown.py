import json
import sys
import re
from pathlib import Path


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
    """Si el texto extraído comienza con el propio título de la sección, lo remueve para no duplicarlo en Markdown."""
    if not clave or not contenido:
        return contenido

    texto_strip = contenido.lstrip()
    clave_clean = clave.strip()

    # Comparación insensible a mayúsculas/minúsculas del inicio del texto con el título
    if texto_strip.lower().startswith(clave_clean.lower()):
        resto = texto_strip[len(clave_clean):].lstrip()
        # Limpiar dos puntos, guiones o saltos de línea sobrantes al inicio del cuerpo
        resto = re.sub(r'^[:\-\s\n]+', '', resto)
        return resto

    return contenido


def convertir_json_a_markdown(data: dict) -> str:
    """Convierte recursivamente la estructura JSON jerárquica a un documento Markdown bien formateado, limpio y sin títulos duplicados."""
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
                    
                    # 1. Limpieza de footers/fechas coladas
                    contenido_limpio = limpiar_footers_y_headers(valor)
                    # 2. Remoción de título duplicado al inicio del párrafo
                    contenido_limpio = remover_titulo_duplicado(clave, contenido_limpio)

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

    # Convertir a formato Markdown con limpieza generalizada y deduplicación de títulos
    markdown_content = convertir_json_a_markdown(data)

    # Guardar en texto_final.md
    output_file = repo_dir / "texto_final.md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"\n¡Éxito! Documento Markdown generado correctamente en: {output_file.name}")
    print("\n" + "=" * 55)
    print(" PREVIEW DEL DOCUMENTO MARKDOWN GENERADO")
    print("=" * 55)
    
    # Imprimir las primeras 30 líneas como preview
    lineas_preview = markdown_content.splitlines()[:30]
    print("\n".join(lineas_preview))
    if len(markdown_content.splitlines()) > 30:
        print("\n... [contenido adicional guardado en texto_final.md] ...")
    print("=" * 55)


if __name__ == "__main__":
    main()
