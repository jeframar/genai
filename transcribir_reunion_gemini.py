import os
import re
import json
import time
import math
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any

from google import genai
from google.genai import types


# =========================
# CONFIGURACIÓN
# =========================

VIDEO_PATH = "reunion.mp4"              # Cambia esto por tu archivo
WORKDIR = "work_reunion"
CHUNK_SECONDS = 10 * 60                 # 10 minutos por segmento
MODEL_TRANSCRIBE = "gemini-2.5-flash"   # Buen balance costo/rendimiento
MODEL_ANALYZE = "gemini-2.5-flash"      # Puedes subir a 2.5-pro si quieres más profundidad

# Si quieres pedir identificación aproximada de hablantes:
TRY_SPEAKERS = True

# Reintentos simples ante errores transitorios
MAX_RETRIES = 4
RETRY_SLEEP_BASE = 4


# =========================
# UTILIDADES
# =========================

def ensure_ffmpeg() -> None:
    """Verifica que ffmpeg y ffprobe existan."""
    for cmd in ("ffmpeg", "ffprobe"):
        if shutil.which(cmd) is None:
            raise RuntimeError(
                f"No se encontró '{cmd}' en el PATH. Instala ffmpeg antes de ejecutar este script."
            )


def run_cmd(cmd: List[str]) -> str:
    """Ejecuta un comando y devuelve stdout; lanza excepción si falla."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Comando falló:\n{' '.join(cmd)}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        )
    return result.stdout.strip()


def get_media_duration_seconds(input_path: str) -> float:
    """Obtiene duración del archivo con ffprobe."""
    out = run_cmd([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path
    ])
    return float(out)


def seconds_to_hhmmss(seconds: float) -> str:
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def make_dirs() -> Dict[str, Path]:
    base = Path(WORKDIR)
    audio_dir = base / "audio"
    chunks_dir = base / "chunks"
    transcript_dir = base / "transcripts"
    analysis_dir = base / "analysis"

    for d in [base, audio_dir, chunks_dir, transcript_dir, analysis_dir]:
        d.mkdir(parents=True, exist_ok=True)

    return {
        "base": base,
        "audio": audio_dir,
        "chunks": chunks_dir,
        "transcripts": transcript_dir,
        "analysis": analysis_dir,
    }


def sanitize_json_text(text: str) -> str:
    """
    Intenta limpiar respuestas que vienen dentro de ```json ... ```
    """
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def chunk_text(text: str, max_chars: int = 18000) -> List[str]:
    """
    Parte texto grande por párrafos, intentando no cortar brutalmente.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current = []

    current_len = 0
    for p in paragraphs:
        p_len = len(p) + 2
        if current and current_len + p_len > max_chars:
            chunks.append("\n\n".join(current))
            current = [p]
            current_len = p_len
        else:
            current.append(p)
            current_len += p_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


# =========================
# AUDIO / SEGMENTACIÓN
# =========================

def extract_audio(video_path: str, output_audio_path: str) -> None:
    """
    Extrae audio a mono 16 kHz WAV.
    Esto suele ser suficiente para voz de reunión y reduce peso.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        output_audio_path,
    ]
    run_cmd(cmd)


def split_audio(audio_path: str, chunks_dir: Path, chunk_seconds: int) -> List[Path]:
    """
    Parte el WAV en segmentos consecutivos.
    """
    duration = get_media_duration_seconds(audio_path)
    total_chunks = math.ceil(duration / chunk_seconds)
    chunk_paths: List[Path] = []

    for i in range(total_chunks):
        start = i * chunk_seconds
        out_path = chunks_dir / f"chunk_{i:03d}.wav"

        cmd = [
            "ffmpeg",
            "-y",
            "-i", audio_path,
            "-ss", str(start),
            "-t", str(chunk_seconds),
            "-ac", "1",
            "-ar", "16000",
            "-c:a", "pcm_s16le",
            str(out_path),
        ]
        run_cmd(cmd)
        chunk_paths.append(out_path)

    return chunk_paths


# =========================
# GEMINI
# =========================

def make_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("No encontré GEMINI_API_KEY en el entorno.")
    return genai.Client(api_key=api_key)


def upload_file_with_retry(client: genai.Client, path: Path, mime_type: str):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            uploaded = client.files.upload(
                file=str(path),
                config={"mime_type": mime_type},
            )
            return uploaded
        except Exception as e:
            last_error = e
            sleep_s = RETRY_SLEEP_BASE * attempt
            print(f"[WARN] Falló upload {path.name}, intento {attempt}/{MAX_RETRIES}: {e}")
            time.sleep(sleep_s)

    raise RuntimeError(f"No pude subir {path} a Gemini Files API: {last_error}")


def generate_with_retry(client: genai.Client, model: str, contents: List[Any], config: types.GenerateContentConfig):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except Exception as e:
            last_error = e
            sleep_s = RETRY_SLEEP_BASE * attempt
            print(f"[WARN] Falló generate_content, intento {attempt}/{MAX_RETRIES}: {e}")
            time.sleep(sleep_s)

    raise RuntimeError(f"No pude completar generate_content: {last_error}")


def transcribe_chunk_to_spanish(
    client: genai.Client,
    chunk_path: Path,
    chunk_index: int,
    chunk_offset_seconds: int,
) -> Dict[str, Any]:
    """
    Sube un chunk y pide transcripción en español con timestamps relativos y absolutos.
    """
    uploaded = upload_file_with_retry(client, chunk_path, "audio/wav")

    speaker_instruction = ""
    if TRY_SPEAKERS:
        speaker_instruction = """
6. Si distingues varios hablantes, etiqueta tentativamente como Hablante 1, Hablante 2, etc.
7. No inventes hablantes si no hay suficiente evidencia.
"""

    prompt = f"""
Transcribe este audio de una reunión al ESPAÑOL.

Instrucciones:
1. Devuelve SOLO JSON válido.
2. Mantén el sentido original. Si hay partes en otro idioma, tradúcelas al español.
3. Conserva muletillas solo si aportan contexto; si no, límpialas ligeramente.
4. Segmenta por bloques cortos con marcas de tiempo.
5. Usa estas claves exactas:
   - "chunk_index": número entero
   - "chunk_offset_seconds": número entero
   - "summary": resumen breve de este segmento
   - "segments": lista de objetos con:
       - "start_mmss": timestamp relativo al chunk en formato MM:SS
       - "end_mmss": timestamp relativo al chunk en formato MM:SS
       - "speaker": string o null
       - "text_es": texto transcrito en español
{speaker_instruction}

Contexto:
- Es una grabación de reunión.
- Este chunk empieza en el segundo absoluto {chunk_offset_seconds}.
- chunk_index = {chunk_index}

No agregues texto fuera del JSON.
"""

    response = generate_with_retry(
        client=client,
        model=MODEL_TRANSCRIBE,
        contents=[
            types.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type),
            prompt,
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    raw = sanitize_json_text(response.text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"No pude parsear JSON de la transcripción del chunk {chunk_index}.\n"
            f"Respuesta original:\n{response.text}\n\nError: {e}"
        )
    return data


def normalize_transcript_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida mínimamente la estructura.
    """
    if "segments" not in data or not isinstance(data["segments"], list):
        raise ValueError("La respuesta no tiene 'segments' como lista.")

    data.setdefault("summary", "")
    data.setdefault("chunk_index", -1)
    data.setdefault("chunk_offset_seconds", 0)

    for seg in data["segments"]:
        seg.setdefault("start_mmss", "00:00")
        seg.setdefault("end_mmss", "00:00")
        seg.setdefault("speaker", None)
        seg.setdefault("text_es", "")

    return data


def build_full_transcript_text(all_chunks: List[Dict[str, Any]]) -> str:
    """
    Convierte la transcripción JSON consolidada a un texto continuo legible.
    """
    lines = []
    for chunk in all_chunks:
        chunk_idx = chunk.get("chunk_index", -1)
        chunk_offset = chunk.get("chunk_offset_seconds", 0)
        lines.append(
            f"\n### CHUNK {chunk_idx} | offset absoluto {seconds_to_hhmmss(chunk_offset)}"
        )
        if chunk.get("summary"):
            lines.append(f"Resumen chunk: {chunk['summary']}\n")

        for seg in chunk.get("segments", []):
            speaker = seg.get("speaker") or "Sin identificar"
            start_rel = seg.get("start_mmss", "00:00")
            end_rel = seg.get("end_mmss", "00:00")
            text_es = seg.get("text_es", "").strip()
            lines.append(f"[{start_rel}-{end_rel}] {speaker}: {text_es}")

    return "\n".join(lines).strip()


def analyze_transcript_block(client: genai.Client, text_block: str, block_index: int) -> Dict[str, Any]:
    """
    Analiza un bloque de la transcripción para luego sintetizar.
    """
    prompt = f"""
Analiza este fragmento de transcripción de una reunión.

Devuelve SOLO JSON válido con esta estructura:
{{
  "block_index": {block_index},
  "summary": "resumen ejecutivo del bloque",
  "topics": ["tema 1", "tema 2"],
  "decisions": ["decisión 1"],
  "action_items": [
    {{
      "task": "qué hay que hacer",
      "owner": "persona o null",
      "deadline": "fecha o null",
      "status": "pendiente/en curso/bloqueado/desconocido"
    }}
  ],
  "risks": ["riesgo 1"],
  "open_questions": ["pregunta 1"],
  "notable_quotes": ["frase relevante 1"]
}}

Reglas:
- No inventes responsables ni fechas.
- Si no aparece claramente, usa null o lista vacía.
- Responde en español.

TRANSCRIPCIÓN:
{text_block}
"""

    response = generate_with_retry(
        client=client,
        model=MODEL_ANALYZE,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )

    raw = sanitize_json_text(response.text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"No pude parsear JSON del análisis del bloque {block_index}.\n"
            f"Respuesta original:\n{response.text}\n\nError: {e}"
        )


def synthesize_final_analysis(client: genai.Client, block_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Toma los análisis por bloque y genera un análisis final consolidado.
    """
    payload = json.dumps(block_analyses, ensure_ascii=False, indent=2)

    prompt = f"""
A partir de estos análisis parciales de una reunión, genera un análisis final consolidado.

Devuelve SOLO JSON válido con esta estructura:
{{
  "executive_summary": "resumen ejecutivo global",
  "main_topics": ["tema 1", "tema 2"],
  "decisions_made": ["decisión 1", "decisión 2"],
  "action_items": [
    {{
      "task": "qué hacer",
      "owner": "persona o null",
      "deadline": "fecha o null",
      "priority": "alta/media/baja/desconocida"
    }}
  ],
  "risks_and_blockers": ["riesgo o bloqueo 1"],
  "open_questions": ["pregunta abierta 1"],
  "sentiment": "tono general de la reunión",
  "next_steps": ["paso siguiente 1", "paso siguiente 2"]
}}

Reglas:
- No inventes datos no presentes.
- Fusiona duplicados.
- Responde en español.

ANÁLISIS PARCIALES:
{payload}
"""

    response = generate_with_retry(
        client=client,
        model=MODEL_ANALYZE,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    raw = sanitize_json_text(response.text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"No pude parsear JSON del análisis final.\n"
            f"Respuesta original:\n{response.text}\n\nError: {e}"
        )


# =========================
# MAIN
# =========================

def main():
    ensure_ffmpeg()

    dirs = make_dirs()
    video_path = Path(VIDEO_PATH)
    if not video_path.exists():
        raise FileNotFoundError(f"No existe el archivo: {video_path}")

    audio_path = dirs["audio"] / "meeting_audio.wav"

    print("1) Extrayendo audio...")
    extract_audio(str(video_path), str(audio_path))

    print("2) Partiendo audio en chunks...")
    chunk_paths = split_audio(str(audio_path), dirs["chunks"], CHUNK_SECONDS)
    print(f"   Total chunks: {len(chunk_paths)}")

    client = make_client()

    all_chunk_transcripts: List[Dict[str, Any]] = []

    print("3) Transcribiendo chunks...")
    for i, chunk_path in enumerate(chunk_paths):
        offset = i * CHUNK_SECONDS
        print(f"   - Chunk {i+1}/{len(chunk_paths)}: {chunk_path.name} (offset {seconds_to_hhmmss(offset)})")

        raw_data = transcribe_chunk_to_spanish(
            client=client,
            chunk_path=chunk_path,
            chunk_index=i,
            chunk_offset_seconds=offset,
        )
        data = normalize_transcript_json(raw_data)
        all_chunk_transcripts.append(data)

        out_json = dirs["transcripts"] / f"chunk_{i:03d}.json"
        out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("4) Consolidando transcripción...")
    full_transcript = build_full_transcript_text(all_chunk_transcripts)
    full_transcript_path = dirs["transcripts"] / "transcripcion_completa.txt"
    full_transcript_path.write_text(full_transcript, encoding="utf-8")

    full_transcript_json_path = dirs["transcripts"] / "transcripcion_completa.json"
    full_transcript_json_path.write_text(
        json.dumps(all_chunk_transcripts, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("5) Analizando transcripción por bloques de texto...")
    transcript_blocks = chunk_text(full_transcript, max_chars=18000)
    block_analyses: List[Dict[str, Any]] = []

    for idx, block in enumerate(transcript_blocks):
        print(f"   - Analizando bloque {idx+1}/{len(transcript_blocks)}")
        analysis = analyze_transcript_block(client, block, idx)
        block_analyses.append(analysis)

        out_json = dirs["analysis"] / f"analysis_block_{idx:03d}.json"
        out_json.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    print("6) Generando análisis final...")
    final_analysis = synthesize_final_analysis(client, block_analyses)

    final_json_path = dirs["analysis"] / "analisis_final.json"
    final_json_path.write_text(
        json.dumps(final_analysis, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # También dejar una versión Markdown legible
    md_lines = []
    md_lines.append("# Análisis final de la reunión\n")
    md_lines.append("## Resumen ejecutivo\n")
    md_lines.append(final_analysis.get("executive_summary", "") + "\n")

    def add_list_section(title: str, items):
        md_lines.append(f"## {title}\n")
        if not items:
            md_lines.append("- Sin elementos claros\n")
            return
        for item in items:
            if isinstance(item, dict):
                md_lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
            else:
                md_lines.append(f"- {item}")
        md_lines.append("")

    add_list_section("Temas principales", final_analysis.get("main_topics", []))
    add_list_section("Decisiones tomadas", final_analysis.get("decisions_made", []))
    add_list_section("Acciones", final_analysis.get("action_items", []))
    add_list_section("Riesgos y bloqueos", final_analysis.get("risks_and_blockers", []))
    add_list_section("Preguntas abiertas", final_analysis.get("open_questions", []))

    md_lines.append("## Sentimiento general\n")
    md_lines.append(final_analysis.get("sentiment", "") + "\n")

    add_list_section("Próximos pasos", final_analysis.get("next_steps", []))

    md_path = dirs["analysis"] / "analisis_final.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print("\nProceso completado.")
    print(f"- Transcripción TXT:  {full_transcript_path}")
    print(f"- Transcripción JSON: {full_transcript_json_path}")
    print(f"- Análisis JSON:      {final_json_path}")
    print(f"- Análisis Markdown:  {md_path}")


if __name__ == "__main__":
    main()