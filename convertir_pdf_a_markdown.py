import os
import sys
import time
import tkinter as tk
from tkinter import filedialog
from pathlib import Path

try:
    import pdf_inspector
except ImportError:
    print("Error: El paquete 'pdf-inspector' de Firecrawl no está instalado.")
    print("Instálalo ejecutando: python -m pip install pdf-inspector")
    sys.exit(1)


def seleccionar_pdf() -> str | None:
    """Abre un cuadro de diálogo nativo para seleccionar un archivo PDF."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    print("Abriendo explorador de archivos para seleccionar el archivo PDF...")
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo PDF a convertir a Markdown",
        filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
    )
    root.destroy()
    return file_path if file_path else None


def convertir_pdf_a_markdown(pdf_path: str, output_path: str | None = None) -> Path:
    """Convierte un PDF a Markdown utilizando la librería nativa pdf-inspector (Firecrawl)."""
    pdf_file = Path(pdf_path).resolve()
    if not pdf_file.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {pdf_file}")

    print(f"\nProcesando archivo: {pdf_file.name}")
    print("Analizando estructura e inspeccionando capas de texto con pdf-inspector (Rust engine)...")

    start_time = time.perf_counter()
    # Usar el motor nativo de Firecrawl (pdf-inspector)
    result = pdf_inspector.process_pdf(str(pdf_file))
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    print("\n" + "=" * 60)
    print(" RESULTADOS DE INSPECCIÓN Y CLASIFICACIÓN (FIRECRALL PDF-INSPECTOR)")
    print("=" * 60)
    print(f" • Título detectado:       {result.title or '[Sin título en metadatos]'}")
    print(f" • Tipo de PDF:            {result.pdf_type}")
    print(f" • Páginas totales:        {result.page_count}")
    print(f" • Tiempo de procesamiento: {elapsed_ms:.2f} ms")
    print(f" • Con problemas de codif: {result.has_encoding_issues}")
    print(f" • Diseño complejo/columnas: {result.is_complex_layout}")
    print(f" • Páginas con tablas:     {len(result.pages_with_tables)}")
    print(f" • Páginas con columnas:   {len(result.pages_with_columns)}")
    print(f" • Páginas que exigen OCR: {len(result.pages_needing_ocr)}")
    print("=" * 60)

    # Determinar ruta de salida
    if not output_path:
        output_file = pdf_file.with_name(f"{pdf_file.stem}_pdfinspector.md")
    else:
        output_file = Path(output_path).resolve()

    # Guardar contenido Markdown extraído
    markdown_content = result.markdown or ""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    print(f"\n¡Éxito! Documento Markdown generado en:")
    print(f" -> {output_file}")
    
    return output_file


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convierte un archivo PDF a Markdown de alta velocidad usando Firecrawl pdf-inspector."
    )
    parser.add_argument(
        "pdf_path",
        nargs="?",
        default=None,
        help="Ruta al archivo PDF. Si se omite, se abre el explorador de archivos para seleccionarlo."
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Ruta de salida para el archivo Markdown (.md)."
    )

    args = parser.parse_args()

    pdf_path = args.pdf_path
    if not pdf_path:
        pdf_path = seleccionar_pdf()
        if not pdf_path:
            print("Operación cancelada: No se seleccionó ningún archivo PDF.")
            sys.exit(0)

    try:
        convertir_pdf_a_markdown(pdf_path, args.output)
    except Exception as e:
        print(f"\nError durante la conversión: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
