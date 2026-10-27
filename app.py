"""Public MCP server for Argentine Spanish text-to-speech and template videos."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import subprocess
import uuid
from pathlib import Path
from typing import Literal

import edge_tts
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voces_argentinas")

OUTPUTS = Path(os.environ.get("AUDIO_OUTPUT_DIR", "/data/audio"))
PUBLIC_AUDIO_BASE_URL = os.environ.get("PUBLIC_AUDIO_BASE_URL", "").rstrip("/")

# Edge provides the two Microsoft Argentine Spanish neural speakers. Variants tune delivery.
VOICES = {
    "arf_00295": ("es-AR-ElenaNeural", "+0%", "+0Hz", "femenina"),
    "arf_06136": ("es-AR-ElenaNeural", "-10%", "+2Hz", "femenina"),
    "arf_08784": ("es-AR-ElenaNeural", "+12%", "-2Hz", "femenina"),
    "arm_00610": ("es-AR-TomasNeural", "+0%", "+0Hz", "masculina"),
    "arm_06136": ("es-AR-TomasNeural", "-10%", "-2Hz", "masculina"),
    "arm_08784": ("es-AR-TomasNeural", "+12%", "+2Hz", "masculina"),
}
FEMALE = tuple(k for k, v in VOICES.items() if v[3] == "femenina")
MALE = tuple(k for k, v in VOICES.items() if v[3] == "masculina")
ALL = FEMALE + MALE
_generate_lock = asyncio.Lock()

def select_voice(genero: str, voz: str | None) -> str:
    pool = FEMALE if genero == "femenina" else MALE if genero == "masculina" else ALL
    if voz:
        if voz not in ALL or voz not in pool:
            raise ValueError("La voz indicada no coincide con el género solicitado.")
        return voz
    return secrets.choice(pool)

async def render(texto: str, voice_id: str) -> tuple[Path, float]:
    voice, rate, pitch, _ = VOICES[voice_id]
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    path = OUTPUTS / f"{uuid.uuid4().hex}.mp3"
    async with _generate_lock:
        communicate = edge_tts.Communicate(texto, voice, rate=rate, pitch=pitch)
        await communicate.save(str(path))
    # Approximate display duration; clients play the MP3's real duration.
    return path, max(0.5, len(texto.split()) / 2.5)

async def render_template_video(audio: Path, duration: float) -> Path:
    """Create a vertical waveform animation without an external video model."""
    output = OUTPUTS / f"{uuid.uuid4().hex}.mp4"
    seconds = max(1.0, duration + 0.35)
    command = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x17112F:s=720x1280:r=30:d={seconds:.2f}",
        "-i", str(audio),
        "-filter_complex",
        "[1:a]showwaves=s=600x180:mode=line:colors=0xD8C6FF[wave];"
        "[0:v][wave]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p[v]",
        "-map", "[v]", "-map", "1:a:0", "-shortest",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(output),
    ]
    await asyncio.to_thread(
        subprocess.run,
        command,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=90,
    )
    return output

mcp = FastMCP(
    "Voces Argentinas TTS",
    instructions=(
        "Para locución sola usá generar_voz_argentina. Para una animación vertical "
        "sin créditos de voz ni video, usá crear_video_con_voz_argentina: devuelve "
        "un MP4 con una visualización de onda y la voz argentina integrada."
    ),
)

@mcp.tool()
async def generar_voz_argentina(
    texto: str,
    genero: Literal["femenina", "masculina", "aleatoria"] = "aleatoria",
    voz: str | None = None,
) -> dict[str, object]:
    """Genera una locución nueva en español argentino y devuelve un MP3."""
    texto = " ".join(texto.split())
    if not texto or len(texto) > 900:
        raise ValueError("El guion debe tener entre 1 y 900 caracteres.")
    if not PUBLIC_AUDIO_BASE_URL:
        raise RuntimeError("El servidor aún no tiene configurada su URL pública.")
    chosen = select_voice(genero, voz)
    try:
        path, duration = await render(texto, chosen)
    except Exception:
        logger.exception("Falló la síntesis: voz=%s caracteres=%s", chosen, len(texto))
        raise
    return {
        "audio_url": f"{PUBLIC_AUDIO_BASE_URL}/{path.name}",
        "formato": "mp3",
        "voz_usada": chosen,
        "genero": VOICES[chosen][3],
        "duracion_aproximada_segundos": round(duration, 2),
        "motor": "Microsoft Edge TTS es-AR",
    }

@mcp.tool()
async def crear_video_con_voz_argentina(
    texto: str,
    genero: Literal["femenina", "masculina", "aleatoria"] = "aleatoria",
    voz: str | None = None,
) -> dict[str, object]:
    """Crea un MP4 vertical de onda animada con una locución argentina integrada.

    No usa ElevenLabs, Higgsfield ni modelos de video de pago. Es una animación
    de plantilla, no un video generativo; elegí género o dejá aleatoria.
    """
    texto = " ".join(texto.split())
    if not texto or len(texto) > 350:
        raise ValueError("El guion para video debe tener entre 1 y 350 caracteres.")
    if not PUBLIC_AUDIO_BASE_URL:
        raise RuntimeError("El servidor aún no tiene configurada su URL pública.")
    chosen = select_voice(genero, voz)
    try:
        audio, duration = await render(texto, chosen)
        video = await render_template_video(audio, duration)
    except Exception:
        logger.exception("Falló el render de video: voz=%s caracteres=%s", chosen, len(texto))
        raise
    return {
        "video_url": f"{PUBLIC_AUDIO_BASE_URL}/{video.name}",
        "audio_url": f"{PUBLIC_AUDIO_BASE_URL}/{audio.name}",
        "formato": "mp4",
        "relacion_aspecto": "9:16",
        "voz_usada": chosen,
        "genero": VOICES[chosen][3],
        "duracion_aproximada_segundos": round(duration, 2),
        "creditos_consumidos": 0,
        "nota": "Animación de onda creada por el servidor propio; no usa un modelo generativo de video.",
    }

@mcp.tool()
def listar_voces_argentinas() -> dict[str, list[str]]:
    """Devuelve las opciones de voz argentinas disponibles."""
    return {"femeninas": list(FEMALE), "masculinas": list(MALE)}

mcp_app = mcp.http_app(path="/")
app = Starlette(
    routes=[
        Mount("/mcp", app=mcp_app),
        Mount("/audio", app=StaticFiles(directory=str(OUTPUTS), check_dir=False)),
    ],
    lifespan=mcp_app.lifespan,
)
