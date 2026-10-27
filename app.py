"""Public MCP server for Argentine Spanish text-to-speech."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
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

mcp = FastMCP("Voces Argentinas TTS")

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
