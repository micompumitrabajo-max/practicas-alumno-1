"""Public MCP server for six synthetic Argentine Spanish TTS voicepacks."""
from __future__ import annotations

import asyncio
import os
import secrets
import uuid
from pathlib import Path
from typing import Literal

import soundfile as sf
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

ROOT = Path(os.environ.get("TTSLIBRE_ROOT", "/opt/ttslibre"))
EXPERIMENT = ROOT / "experiments" / "014-spanish-8h-openslr61"
OUTPUTS = Path(os.environ.get("AUDIO_OUTPUT_DIR", "/data/audio"))
PUBLIC_AUDIO_BASE_URL = os.environ.get("PUBLIC_AUDIO_BASE_URL", "").rstrip("/")

FEMALE = ("arf_00295", "arf_06136", "arf_08784")
MALE = ("arm_00610", "arm_06136", "arm_08784")
ALL = FEMALE + MALE
_synth = None
_load_lock = asyncio.Lock()
_generate_lock = asyncio.Lock()

def select_voice(genero: str, voz: str | None) -> str:
    pool = FEMALE if genero == "femenina" else MALE if genero == "masculina" else ALL
    if voz:
        if voz not in ALL or voz not in pool:
            raise ValueError("La voz indicada no coincide con el género solicitado.")
        return voz
    return secrets.choice(pool)

async def get_synth():
    global _synth
    if _synth is not None:
        return _synth
    async with _load_lock:
        if _synth is None:
            import sys
            sys.path.insert(0, str(EXPERIMENT))
            from common import load_config
            from synth import Synth
            config = load_config(str(EXPERIMENT / "config.json"))
            _synth = (Synth(config, run=str(EXPERIMENT / "runs" / "es8h" / "ttl.pt")), config)
    return _synth

async def render(texto: str, voice: str) -> tuple[Path, float]:
    synth, config = await get_synth()
    async with _generate_lock:
        zref, rmask = synth.style(str(ROOT / "experiments" / "voices" / f"{voice}.pt"))
        wav, _ = synth(texto, zref, rmask, steps=16, cfg=2.0, duration_scale=1.0)
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        path = OUTPUTS / f"{uuid.uuid4().hex}.wav"
        sf.write(path, wav, config["data"]["sample_rate"])
    return path, len(wav) / float(config["data"]["sample_rate"])

mcp = FastMCP("Voces Argentinas TTS")

@mcp.tool()
async def generar_voz_argentina(
    texto: str,
    genero: Literal["femenina", "masculina", "aleatoria"] = "aleatoria",
    voz: str | None = None,
) -> dict[str, object]:
    """Genera una locución nueva en español argentino y devuelve un WAV."""
    texto = " ".join(texto.split())
    if not texto or len(texto) > 900:
        raise ValueError("El guion debe tener entre 1 y 900 caracteres.")
    if not PUBLIC_AUDIO_BASE_URL:
        raise RuntimeError("El servidor aún no tiene configurada su URL pública.")
    chosen = select_voice(genero, voz)
    path, duration = await render(texto, chosen)
    return {
        "audio_url": f"{PUBLIC_AUDIO_BASE_URL}/{path.name}",
        "formato": "wav",
        "voz_usada": chosen,
        "genero": "femenina" if chosen.startswith("arf_") else "masculina",
        "duracion_segundos": round(duration, 2),
        "atribucion": "TTSLibre es-AR, CC BY-SA 4.0",
    }

@mcp.tool()
def listar_voces_argentinas() -> dict[str, list[str]]:
    """Devuelve las seis voces argentinas disponibles."""
    return {"femeninas": list(FEMALE), "masculinas": list(MALE)}

app = Starlette(routes=[
    Mount("/mcp", app=mcp.http_app(path="/")),
    Mount("/audio", app=StaticFiles(directory=str(OUTPUTS), check_dir=False)),
])
