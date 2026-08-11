import os
import sys
import re
import time
import json
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()


def analizar_reglas_deterministicas(texto: str) -> dict:
    """Realiza un análisis determinístico mediante expresiones regulares para detectar errores comunes."""
    lineas = texto.splitlines()
    
    hallazgos = {
        "caracteres_corruptos": [],
        "espacios_anomalos": [],
        "saltos_linea_extraños": [],
        "balance_parentesis": [],
        "falta_espacio_puntuacion": []
    }

    # 1. Caracteres corruptos o de reemplazo Unicode (ej: \ufffd)
    for num_linea, linea in enumerate(lineas, start=1):
        if "\ufffd" in linea or "\u00ef\u00bf\u00bd" in linea:
            hallazgos["caracteres_corruptos"].append(
                f"Línea {num_linea}: Contiene caracteres corruptos de codificación ('\ufffd') -> \"{linea[:100].strip()}...\""
            )

    # 2. Espacios anómalos (dobles espacios o espacios antes de punto/coma)
    for num_linea, linea in enumerate(lineas, start=1):
        if re.search(r'\w\s+[\,\.\;\:]', linea):
            hallazgos["espacios_anomalos"].append(
                f"Línea {num_linea}: Espacio innecesario antes de puntuación -> \"{linea.strip()[:100]}\""
            )
        elif re.search(r'\w {2,}\w', linea):
            hallazgos["espacios_anomalos"].append(
                f"Línea {num_linea}: Múltiples espacios consecutivos entre palabras -> \"{linea.strip()[:100]}\""
            )

    # 3. Falta de espacio después de puntuación (ej. "palabra.Otra" o "texto,siguiente")
    for num_linea, linea in enumerate(lineas, start=1):
        linea_sin_urls = re.sub(r'https?://\S+|www\.\S+|\b\d+\.\d+\b', '', linea)
        matches = re.finditer(r'([a-zA-ZáéíóúÁÉÍÓÚñÑ]{2,})([\,\.\;\:])([a-zA-ZáéíóúÁÉÍÓÚñÑ]{2,})', linea_sin_urls)
        for m in matches:
            hallazgos["falta_espacio_puntuacion"].append(
                f"Línea {num_linea}: Falta espacio después de '{m.group(2)}' en \"{m.group(0)}\""
            )

    # 4. Saltos de línea extraños (más de 2 líneas en blanco consecutivas)
    lineas_vacias_consecutivas = 0
    for num_linea, linea in enumerate(lineas, start=1):
        if not linea.strip():
            lineas_vacias_consecutivas += 1
            if lineas_vacias_consecutivas == 3:
                hallazgos["saltos_linea_extraños"].append(
                    f"Línea {num_linea}: Exceso de saltos de línea consecutivos (más de 2 líneas en blanco)."
                )
        else:
            lineas_vacias_consecutivas = 0

    # 5. Balance de paréntesis y corchetes no cerrados en la misma línea
    for num_linea, linea in enumerate(lineas, start=1):
        if linea.count('(') != linea.count(')'):
            hallazgos["balance_parentesis"].append(
                f"Línea {num_linea}: Paréntesis '(' y ')' desbalanceados ({linea.count('(')} vs {linea.count(')')}) -> \"{linea.strip()[:90]}\""
            )
        if linea.count('[') != linea.count(']'):
            hallazgos["balance_parentesis"].append(
                f"Línea {num_linea}: Corchetes '[' y ']' desbalanceados -> \"{linea.strip()[:90]}\""
            )

    return hallazgos


def auditoria_ortografica_gemini(api_key: str, texto: str) -> str:
    """Utiliza la API REST de Gemini para realizar una revisión ortográfica y gramatical profunda del documento."""
    prompt = """Actúa como un corrector de estilo y auditor ortográfico experto.

TU TAREA:
Analiza el siguiente texto extraído de un documento Markdown y detecta:
1. Errores ortográficos o palabras mal escritas (typos).
2. Errores gramaticales o de concordancia.
3. Palabras en inglés u otro idioma con caracteres corruptos o pegadas.

REGLAS DE SALIDA:
- Presenta el resultado en un formato de lista claro.
- Para cada error encontrado, indica:
  - Error detectado / Palabra original
  - Corrección sugerida
  - Breve contexto o explicación
- Si no encuentras ningún error ortográfico o gramatical, indica expresamente: "No se detectaron errores ortográficos adicionales."

TEXTO A AUDITAR:
\"\"\"
""" + texto[:20000] + """
\"\"\""""

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.1
        }
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key
            }
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"Revisión AI no disponible ({e})."


def main():
    repo_dir = Path(__file__).parent.resolve()
    markdown_file = repo_dir / "texto_final.md"

    if not markdown_file.exists():
        print(f"Error: No se encontró el archivo '{markdown_file.name}' en el repositorio.")
        sys.exit(1)

    print(f"Cargando documento Markdown: {markdown_file.name}...")
    with open(markdown_file, "r", encoding="utf-8") as f:
        texto = f.read()

    total_lineas = len(texto.splitlines())
    total_palabras = len(texto.split())

    print("1/2 Ejecutando análisis sintáctico determinístico (espacios, saltos, caracteres)...")
    hallazgos = analizar_reglas_deterministicas(texto)

    # Revisión ortográfica con Gemini si existe API Key
    print("2/2 Ejecutando auditoría ortográfica y gramatical con Gemini AI...")
    api_key = os.environ.get("GEMINI_API_KEY")
    reporte_ai = ""
    if api_key:
        reporte_ai = auditoria_ortografica_gemini(api_key, texto)
    else:
        reporte_ai = "GEMINI_API_KEY no configurada. Omitiendo revisión ortográfica por IA."

    # Construir informe final en formato TXT
    reporte_txt = []
    reporte_txt.append("=================================================================")
    reporte_txt.append("        REPORTE DE AUDITORÍA DE CALIDAD Y ORTOGRAFÍA (MARKDOWN)  ")
    reporte_txt.append("=================================================================")
    reporte_txt.append(f"Archivo analizado:    {markdown_file.name}")
    reporte_txt.append(f"Fecha de análisis:    {time.strftime('%Y-%m-%d %H:%M:%S')}")
    reporte_txt.append(f"Estadísticas:         {total_lineas:,} líneas | {total_palabras:,} palabras")
    reporte_txt.append("=================================================================\n")

    # 1. Caracteres corruptos
    reporte_txt.append("--- 1. CARACTERES CORRUPTOS Y SÍMBOLOS EXTRAÑOS ---")
    if hallazgos["caracteres_corruptos"]:
        reporte_txt.extend(hallazgos["caracteres_corruptos"])
    else:
        reporte_txt.append("[OK] No se detectaron caracteres corruptos de decodificación.")
    reporte_txt.append("")

    # 2. Espacios anómalos
    reporte_txt.append("--- 2. ERRORES DE ESPACIADO Y PUNTUACIÓN ---")
    if hallazgos["espacios_anomalos"]:
        reporte_txt.extend(hallazgos["espacios_anomalos"][:50])
    else:
        reporte_txt.append("[OK] No se detectaron múltiples espacios ni espacios innecesarios antes de puntuación.")
    reporte_txt.append("")

    # 3. Falta de espacio después de puntuación
    reporte_txt.append("--- 3. FALTA DE ESPACIO DESPUÉS DE PUNTUACIÓN ---")
    if hallazgos["falta_espacio_puntuacion"]:
        reporte_txt.extend(hallazgos["falta_espacio_puntuacion"][:50])
    else:
        reporte_txt.append("[OK] Formato de puntuación y espaciado correcto.")
    reporte_txt.append("")

    # 4. Saltos de línea
    reporte_txt.append("--- 4. ERRORES DE SALTOS DE LÍNEA EXCESIVOS ---")
    if hallazgos["saltos_linea_extraños"]:
        reporte_txt.extend(hallazgos["saltos_linea_extraños"])
    else:
        reporte_txt.append("[OK] Distribución de saltos de línea e interlineado correcto.")
    reporte_txt.append("")

    # 5. BALANCE DE PARÉNTESIS Y CORCHETES
    reporte_txt.append("--- 5. BALANCE DE PARÉNTESIS Y CORCHETES ---")
    if hallazgos["balance_parentesis"]:
        reporte_txt.extend(hallazgos["balance_parentesis"][:50])
    else:
        reporte_txt.append("[OK] Paréntesis y corchetes balanceados correctamente.")
    reporte_txt.append("")

    # 6. Auditoría Ortográfica y Gramatical AI
    reporte_txt.append("--- 6. REVISIÓN ORTOGRÁFICA Y GRAMATICAL (GEMINI AI) ---")
    reporte_txt.append(reporte_ai)
    reporte_txt.append("\n=================================================================")
    reporte_txt.append("                        FIN DEL REPORTE                          ")
    reporte_txt.append("=================================================================")

    contenido_final = "\n".join(reporte_txt)

    # Guardar en reporte_calidad.txt
    output_report = repo_dir / "reporte_calidad.txt"
    with open(output_report, "w", encoding="utf-8") as f:
        f.write(contenido_final)

    print(f"\n¡Éxito! Reporte de auditoría generado correctamente en: {output_report.name}")
    print("\n" + "=" * 55)
    print(" PREVIEW DEL REPORTE DE AUDITORÍA GENERADO")
    print("=" * 55)
    print("\n".join(contenido_final.splitlines()[:35]))
    print("=" * 55)


if __name__ == "__main__":
    main()
