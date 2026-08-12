import os
import sys
import re
import zipfile
import urllib.request
import argparse
import tempfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET
from pathlib import Path


class HTMLToMarkdownParser(HTMLParser):
    """
    Parser basado en html.parser que transforma contenido XHTML/HTML
    de archivos EPUB a formato Markdown estructurado.
    """
    def __init__(self):
        super().__init__()
        self.md_parts = []
        self.ignore_tags = {'script', 'style', 'head', 'meta', 'link', 'noscript', 'svg', 'button'}
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        self.tag_stack.append(tag_lower)

        if tag_lower in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag_lower[1])
            self.md_parts.append(f"\n\n{'#' * level} ")
        elif tag_lower == 'p':
            self.md_parts.append("\n\n")
        elif tag_lower == 'li':
            self.md_parts.append("\n- ")
        elif tag_lower == 'blockquote':
            self.md_parts.append("\n\n> ")
        elif tag_lower == 'br':
            self.md_parts.append("\n")
        elif tag_lower in ['strong', 'b']:
            self.md_parts.append("**")
        elif tag_lower in ['em', 'i']:
            self.md_parts.append("*")

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if self.tag_stack and self.tag_stack[-1] == tag_lower:
            self.tag_stack.pop()

        if tag_lower in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'blockquote']:
            self.md_parts.append("\n")
        elif tag_lower in ['strong', 'b']:
            self.md_parts.append("**")
        elif tag_lower in ['em', 'i']:
            self.md_parts.append("*")

    def handle_data(self, data):
        if any(t in self.ignore_tags for t in self.tag_stack):
            return
        if data:
            self.md_parts.append(data)

    def get_markdown(self) -> str:
        raw_md = "".join(self.md_parts)
        lines = raw_md.splitlines()
        cleaned_lines = []
        prev_blank = False

        for line in lines:
            stripped = line.rstrip()
            if stripped:
                cleaned_lines.append(stripped)
                prev_blank = False
            elif not prev_blank:
                cleaned_lines.append("")
                prev_blank = True

        return "\n".join(cleaned_lines).strip()


def extraer_texto_de_epub(epub_path: Path) -> str:
    """
    Lee un archivo .epub local usando la librería estándar zipfile y ElementTree,
    obtiene la secuencia oficial de lectura (spine) del OPF y convierte todo a Markdown.
    """
    if not epub_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo: {epub_path}")

    if not zipfile.is_zipfile(epub_path):
        raise ValueError(f"El archivo '{epub_path.name}' no es un archivo EPUB / ZIP válido.")

    with zipfile.ZipFile(epub_path, "r") as z:
        # 1. Obtener la ruta del archivo de manifiesto .opf desde META-INF/container.xml
        opf_path = None
        if "META-INF/container.xml" in z.namelist():
            try:
                container_xml = z.read("META-INF/container.xml")
                root = ET.fromstring(container_xml)
                for rootfile in root.iter("{urn:oasis:names:tc:opendocument:xmlns:container}rootfile"):
                    opf_path = rootfile.attrib.get("full-path")
                    break
            except Exception:
                pass

        # Fallback para encontrar el archivo .opf si container.xml falla
        if not opf_path:
            for name in z.namelist():
                if name.endswith(".opf"):
                    opf_path = name
                    break

        html_files = []
        if opf_path and opf_path in z.namelist():
            opf_dir = os.path.dirname(opf_path)
            try:
                opf_content = z.read(opf_path)
                root = ET.fromstring(opf_content)
                manifest = {}
                spine = []

                # Mapear los elementos del manifiesto (id -> href)
                for item in root.iter():
                    if item.tag.endswith("item"):
                        item_id = item.attrib.get("id")
                        href = item.attrib.get("href")
                        media_type = item.attrib.get("media-type", "")
                        if item_id and href and ("html" in media_type or href.endswith((".xhtml", ".html", ".htm"))):
                            full_href = (opf_dir + "/" + href) if opf_dir else href
                            full_href = full_href.lstrip("/")
                            manifest[item_id] = full_href

                    elif item.tag.endswith("itemref"):
                        idref = item.attrib.get("idref")
                        if idref:
                            spine.append(idref)

                for idref in spine:
                    if idref in manifest:
                        html_files.append(manifest[idref])

            except Exception as e:
                print(f"[Aviso] Error al parsear el manifiesto OPF ({e}). Usando orden por defecto.")

        # Fallback si el manifiesto no entregó la lista de archivos
        if not html_files:
            html_files = sorted([
                f for f in z.namelist() 
                if f.endswith((".xhtml", ".html", ".htm")) and not f.startswith("__MACOSX")
            ])

        markdown_secciones = []
        for file_name in html_files:
            # Buscar coincidencia exacta o por nombre de archivo
            matched_entry = None
            if file_name in z.namelist():
                matched_entry = file_name
            else:
                for entry in z.namelist():
                    if entry.endswith(file_name) or file_name.endswith(entry):
                        matched_entry = entry
                        break

            if matched_entry:
                try:
                    raw_html = z.read(matched_entry).decode("utf-8", errors="ignore")
                    parser = HTMLToMarkdownParser()
                    parser.feed(raw_html)
                    md_text = parser.get_markdown()
                    if md_text:
                        markdown_secciones.append(md_text)
                except Exception as e:
                    print(f"[Aviso] No se pudo parsear '{file_name}': {e}")

        return "\n\n---\n\n".join(markdown_secciones)


def descargar_epub_desde_url(url: str, output_temp: Path):
    """
    Intenta descargar el archivo .epub desde una URL.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/epub+zip,*/*;q=0.8'
    }
    print(f"--> Intentando descargar archivo EPUB desde: {url}")
    req = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(req) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()
        
        with open(output_temp, "wb") as f:
            f.write(data)
            
    if not zipfile.is_zipfile(output_temp):
        raise ValueError(
            "El servidor no devolvió un archivo EPUB válido (es posible que requiera inicio de sesión o protección Anti-Bot)."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Extrae el texto completo de un archivo EPUB (o URL EPUB) y lo guarda en formato Markdown."
    )
    parser.add_argument(
        "origen",
        nargs="?",
        default="test_mock.epub",
        help="Ruta al archivo .epub local o URL del EPUB a extraer."
    )
    parser.add_argument(
        "-o", "--output",
        default="articulo_extraido_epub.md",
        help="Nombre del archivo Markdown de salida (por defecto: articulo_extraido_epub.md)."
    )

    args = parser.parse_args()
    origen = args.origen
    repo_dir = Path(__file__).parent.resolve()
    output_file = repo_dir / args.output

    temp_epub_created = False
    epub_file_path = None

    if origen.startswith(("http://", "https://")):
        temp_file = repo_dir / "temp_download.epub"
        try:
            descargar_epub_desde_url(origen, temp_file)
            epub_file_path = temp_file
            temp_epub_created = True
        except Exception as e:
            print(f"\n[Aviso de descarga] No se pudo descargar directamente desde la URL: {e}")
            print("\n📌 INSTRUCCIONES:")
            print("Las revistas de SAGE Journals bloquean la descarga directa automatizada (error 403 / Cloudflare).")
            print("1. Abre el enlace en tu navegador web y descarga el archivo .epub directamente.")
            print("2. Ejecuta el script indicando la ruta del archivo descargado:")
            print(f"   python extraer_texto_epub.py <ruta_al_archivo.epub> -o {args.output}\n")
            if temp_file.exists():
                temp_file.unlink()
            sys.exit(1)
    else:
        epub_file_path = Path(origen)
        if not epub_file_path.is_absolute():
            epub_file_path = repo_dir / epub_file_path

    try:
        print(f"--> Extrayendo y convirtiendo EPUB: {epub_file_path.name}")
        markdown_text = extraer_texto_de_epub(epub_file_path)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        palabras = len(markdown_text.split())
        lineas = len(markdown_text.splitlines())
        caracteres = len(markdown_text)

        print("\n" + "=" * 60)
        print(" ¡EXTRACCIÓN DE EPUB COMPLETADA CON ÉXITO!")
        print("=" * 60)
        print(f" Archivo guardado:  {output_file.name}")
        print(f" Ruta completa:     {output_file}")
        print(f" Estadísticas:      {caracteres:,} caracteres | {palabras:,} palabras | {lineas:,} líneas")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] Error al procesar el archivo EPUB: {e}")
        sys.exit(1)
    finally:
        if temp_epub_created and epub_file_path and epub_file_path.exists():
            try:
                epub_file_path.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    main()
