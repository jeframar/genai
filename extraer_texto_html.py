import os
import sys
import re
import urllib.request
import argparse
from html.parser import HTMLParser
from pathlib import Path


class HTMLToMarkdownParser(HTMLParser):
    """
    Parser basado en la librería estándar `html.parser` que transforma el contenido HTML
    de un artículo académico en un documento Markdown estructurado.
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
        # Omitir texto de scripts, estilos, metadatos y elementos no visibles
        if any(t in self.ignore_tags for t in self.tag_stack):
            return
        
        if data:
            self.md_parts.append(data)

    def get_markdown(self) -> str:
        raw_md = "".join(self.md_parts)
        
        # Normalizar espacios y líneas en blanco excesivas
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


def extraer_texto_desde_url(url: str) -> str:
    """
    Descarga el contenido de la URL indicada. Si detecta un visor OJS (iframe htmlGalleyFrame),
    resuelve y descarga la fuente HTML real del artículo.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    print(f"--> Obteniendo contenido web desde: {url}")
    req = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')

    # Detectar si es una página contenedora OJS que empotra el artículo dentro de un <iframe>
    iframe_match = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if iframe_match:
        iframe_src = iframe_match.group(1)
        print(f"--> Detectado visor HTML OJS (iframe). Obteniendo documento fuente desde: {iframe_src}")
        req2 = urllib.request.Request(iframe_src, headers=headers)
        with urllib.request.urlopen(req2) as resp2:
            html = resp2.read().decode('utf-8', errors='ignore')

    parser = HTMLToMarkdownParser()
    parser.feed(html)
    return parser.get_markdown()


def main():
    parser = argparse.ArgumentParser(
        description="Extrae el texto completo de un artículo en HTML (ej. OJS / Cultural Anthropology) y lo guarda en Markdown."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="https://journal.culanth.org/index.php/ca/article/view/5828/1065",
        help="URL del artículo HTML a extraer (por defecto: el enlace de Cultural Anthropology proporcionado)."
    )
    parser.add_argument(
        "-o", "--output",
        default="articulo_extraido.md",
        help="Nombre del archivo Markdown de salida (por defecto: articulo_extraido.md)."
    )

    args = parser.parse_args()

    repo_dir = Path(__file__).parent.resolve()
    output_file = repo_dir / args.output

    try:
        markdown_text = extraer_texto_desde_url(args.url)
        
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        palabras = len(markdown_text.split())
        lineas = len(markdown_text.splitlines())
        caracteres = len(markdown_text)

        print("\n" + "=" * 60)
        print(" ¡EXTRACCIÓN COMPLETADA CON ÉXITO!")
        print("=" * 60)
        print(f" Archivo guardado:  {output_file.name}")
        print(f" Ruta completa:     {output_file}")
        print(f" Estadísticas:      {caracteres:,} caracteres | {palabras:,} palabras | {lineas:,} líneas")
        print("=" * 60)

    except Exception as e:
        print(f"\n[ERROR] Ocurrió un error al procesar el enlace: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
