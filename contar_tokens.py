import os
import sys
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Cargar variables de entorno (.env)
load_dotenv()


def seleccionar_archivo() -> str | None:
    """Abre un diálogo de explorador de archivos para seleccionar cualquier documento (PDF, TXT, JSON, MD, etc.)."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)

    print("Abriendo explorador de archivos...")
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo para contar tokens",
        filetypes=[
            ("Todos los archivos compatibles", "*.pdf;*.txt;*.json;*.md;*.csv;*.docx;*.html"),
            ("Documentos PDF", "*.pdf"),
            ("Archivos de Texto / Código", "*.txt;*.json;*.md;*.csv;*.py;*.html"),
            ("Todos los archivos", "*.*")
        ]
    )
    root.destroy()
    return file_path if file_path else None


def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: No se encontró GEMINI_API_KEY en el entorno o archivo .env.")
        sys.exit(1)

    # 1. Seleccionar archivo desde el explorador
    file_path = seleccionar_archivo()
    if not file_path:
        print("Operación cancelada: No se seleccionó ningún archivo.")
        sys.exit(0)

    path_obj = Path(file_path)
    file_size_kb = path_obj.stat().st_size / 1024

    print(f"\nArchivo seleccionado: {path_obj.name}")
    print(f"Ruta completa: {file_path}")
    print(f"Tamaño del archivo: {file_size_kb:.2f} KB")

    # 2. Inicializar cliente Gemini
    client = genai.Client()
    file_ref = None

    try:
        # Si es un archivo PDF o binario, se sube a Files API para contar los tokens adecuadamente
        print("\nProcesando archivo y contando tokens con Gemini API...")
        file_ref = client.files.upload(file=file_path)

        # 3. Contar tokens usando el método oficial de Gemini SDK
        response = client.models.count_tokens(
            model="gemini-2.5-flash",
            contents=[file_ref]
        )

        total_tokens = response.total_tokens

        print("\n" + "=" * 45)
        print(f" RESULTADO DEL CONTEO DE TOKENS")
        print("=" * 45)
        print(f" Archivo:        {path_obj.name}")
        print(f" Modelo:         gemini-2.5-flash")
        print(f" Total Tokens:   {total_tokens:,} tokens")
        print("=" * 45)

    except Exception as e:
        print(f"\nOcurrió un error al contar los tokens: {e}")
        sys.exit(1)
    finally:
        # Limpiar archivo de Gemini Storage
        if file_ref:
            try:
                client.files.delete(name=file_ref.name)
            except Exception:
                pass


if __name__ == "__main__":
    main()
