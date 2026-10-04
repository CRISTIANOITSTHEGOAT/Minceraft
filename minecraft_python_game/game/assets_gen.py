"""
Procedural asset generator and safe loader for textures, item icons, sounds, and models.
Ensures zero external proprietary assets are required and handles missing assets gracefully.
"""

import math
import os
import struct
import wave
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from game import pixelart
from game.blocks import (
    ATLAS_COLS,
    ATLAS_ROWS,
    BLOCKS_BY_KEY,
    ITEMS,
    TILE_COORDS,
    TILE_PIXEL_SIZE,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"
TEXTURES_DIR = ASSETS_DIR / "textures"
ICONS_DIR = TEXTURES_DIR / "icons"
SOUNDS_DIR = ASSETS_DIR / "sounds"
MODELS_DIR = ASSETS_DIR / "models"
MOBS_DIR = TEXTURES_DIR / "mobs"
UI_DIR = TEXTURES_DIR / "ui"
ART_VERSION_FILE = TEXTURES_DIR / ".art_version"


def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


def _generate_tile_image(tile_name: str, seed: int = 1337) -> Image.Image:
    """Create a 16x16 RGBA pixel-art tile for the given tile name (see game/pixelart.py)."""
    return pixelart.generate_tile(tile_name)


def generate_atlas_image() -> Image.Image:
    """Create the full 256x256 RGBA block texture atlas."""
    atlas_w = ATLAS_COLS * TILE_PIXEL_SIZE
    atlas_h = ATLAS_ROWS * TILE_PIXEL_SIZE
    atlas = Image.new("RGBA", (atlas_w, atlas_h), (255, 255, 255, 255))

    for tile_name, (col, row) in TILE_COORDS.items():
        tile_img = _generate_tile_image(tile_name)
        atlas.paste(tile_img, (col * TILE_PIXEL_SIZE, row * TILE_PIXEL_SIZE))

    return atlas


def generate_item_icon(item_key: str) -> Image.Image:
    """Create a 32x32 RGBA pixel-art icon (isometric for blocks, sprites for items)."""
    item = ITEMS.get(item_key)
    if item is None:
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(img).rectangle([4, 4, 27, 27], fill=(180, 180, 180, 255))
        return img
    return pixelart.generate_icon(item, BLOCKS_BY_KEY.get(item_key) if item.category == "block" else None)


def _write_wav(filepath: Path, samples: np.ndarray, sample_rate: int = 22050) -> None:
    """Write a float [-1, 1] numpy array as a 16-bit mono WAV file."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    with wave.open(str(filepath), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def generate_sound_files() -> None:
    """Generate procedural WAV sound effects in assets/sounds/."""
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    sr = 22050
    rng = np.random.RandomState(42)

    # 1. dig.wav (crunchy block break)
    t = np.linspace(0, 0.14, int(sr * 0.14), endpoint=False)
    env = np.exp(-t * 22)
    dig = (rng.uniform(-0.7, 0.7, len(t)) + 0.3 * np.sin(2 * np.pi * 140 * t)) * env
    _write_wav(SOUNDS_DIR / "dig.wav", dig * 0.5, sr)

    # 2. place.wav (solid block placement thud)
    t = np.linspace(0, 0.12, int(sr * 0.12), endpoint=False)
    env = np.exp(-t * 28)
    place = (0.6 * np.sin(2 * np.pi * 110 * t) + 0.4 * rng.uniform(-0.5, 0.5, len(t))) * env
    _write_wav(SOUNDS_DIR / "place.wav", place * 0.55, sr)

    # 3. step.wav (soft footstep)
    t = np.linspace(0, 0.08, int(sr * 0.08), endpoint=False)
    env = np.exp(-t * 35)
    step = rng.uniform(-0.4, 0.4, len(t)) * env
    _write_wav(SOUNDS_DIR / "step.wav", step * 0.35, sr)

    # 4. hurt.wav (damage impact)
    t = np.linspace(0, 0.20, int(sr * 0.20), endpoint=False)
    env = np.exp(-t * 14)
    hurt = (0.7 * np.sin(2 * np.pi * (220 - 600 * t) * t) + 0.3 * rng.uniform(-0.5, 0.5, len(t))) * env
    _write_wav(SOUNDS_DIR / "hurt.wav", hurt * 0.6, sr)

    # 5. swing.wav (sword/tool swing whoosh)
    t = np.linspace(0, 0.12, int(sr * 0.12), endpoint=False)
    env = np.sin(np.pi * t / 0.12)
    swing = rng.uniform(-0.5, 0.5, len(t)) * env * 0.4
    _write_wav(SOUNDS_DIR / "swing.wav", swing, sr)

    # 6. eat.wav (food crunch)
    t = np.linspace(0, 0.18, int(sr * 0.18), endpoint=False)
    env = np.abs(np.sin(2 * np.pi * 8 * t)) * np.exp(-t * 8)
    eat = rng.uniform(-0.6, 0.6, len(t)) * env * 0.45
    _write_wav(SOUNDS_DIR / "eat.wav", eat, sr)

    # 7. craft.wav (pleasant craft chime)
    t = np.linspace(0, 0.22, int(sr * 0.22), endpoint=False)
    env = np.exp(-t * 12)
    craft = (0.5 * np.sin(2 * np.pi * 523.25 * t) + 0.5 * np.sin(2 * np.pi * 659.25 * t)) * env * 0.45
    _write_wav(SOUNDS_DIR / "craft.wav", craft, sr)

    # 8. splash.wav (water splash)
    t = np.linspace(0, 0.25, int(sr * 0.25), endpoint=False)
    env = np.exp(-t * 10)
    splash = rng.uniform(-0.6, 0.6, len(t)) * env * 0.4
    _write_wav(SOUNDS_DIR / "splash.wav", splash, sr)


def generate_model_files() -> None:
    """Generate simple Wavefront OBJ models in assets/models/."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    cube_obj = """# Unit voxel cube
v 0.0 0.0 0.0
v 1.0 0.0 0.0
v 1.0 1.0 0.0
v 0.0 1.0 0.0
v 0.0 0.0 1.0
v 1.0 0.0 1.0
v 1.0 1.0 1.0
v 0.0 1.0 1.0
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 5 1 4 8
"""
    (MODELS_DIR / "cube_block.obj").write_text(cube_obj, encoding="utf-8")


def generate_ui_textures() -> None:
    """Write main-menu panorama, logo and button textures."""
    UI_DIR.mkdir(parents=True, exist_ok=True)
    pixelart.generate_panorama().save(UI_DIR / "panorama.png")
    pixelart.generate_logo("PYCRAFT").save(UI_DIR / "logo.png")
    for state in ("normal", "hover", "pressed", "disabled"):
        pixelart.generate_button(200, 20, state).resize((400, 40), Image.NEAREST).save(UI_DIR / f"button_{state}.png")


def generate_mob_textures() -> None:
    MOBS_DIR.mkdir(parents=True, exist_ok=True)
    for mob_type in pixelart.MOB_SKIN_SIZES:
        pixelart.generate_mob_skin(mob_type).save(MOBS_DIR / f"{mob_type}.png")


def _art_is_current() -> bool:
    try:
        return ART_VERSION_FILE.read_text().strip() == str(pixelart.ART_VERSION)
    except Exception:
        return False


def ensure_all_assets() -> None:
    """Ensure all procedural textures, icons, sounds, and models exist and are up to date."""
    try:
        TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
        ICONS_DIR.mkdir(parents=True, exist_ok=True)
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

        stale = not _art_is_current()
        atlas_path = TEXTURES_DIR / "atlas.png"
        if stale or not atlas_path.exists():
            generate_atlas_image().save(atlas_path)

        for item_key in ITEMS:
            icon_path = ICONS_DIR / f"{item_key}.png"
            if stale or not icon_path.exists():
                generate_item_icon(item_key).save(icon_path)

        if stale or not (MOBS_DIR / "pig.png").exists() or not (MOBS_DIR / "skeleton.png").exists():
            generate_mob_textures()
        if stale or not (UI_DIR / "panorama.png").exists():
            generate_ui_textures()
        if stale:
            ART_VERSION_FILE.write_text(str(pixelart.ART_VERSION))

        if not (SOUNDS_DIR / "dig.wav").exists():
            generate_sound_files()

        if not (MODELS_DIR / "cube_block.obj").exists():
            generate_model_files()
    except Exception as exc:
        print(f"[Assets] Warning while writing asset files: {exc}")


def get_mob_texture(mob_type: str):
    """Return the Ursina Texture for a mob skin (nearest filtered), generating it if missing."""
    if mob_type in _CACHED_MOB_TEX:
        return _CACHED_MOB_TEX[mob_type]
    from ursina import Texture
    path = MOBS_DIR / f"{mob_type}.png"
    try:
        img = Image.open(path).convert("RGBA") if path.exists() else pixelart.generate_mob_skin(mob_type)
    except Exception:
        img = pixelart.generate_mob_skin(mob_type)
    tex = Texture(img)
    tex.filtering = None
    _CACHED_MOB_TEX[mob_type] = tex
    return tex


def get_ui_texture(name: str):
    """Return an Ursina Texture from assets/textures/ui (panorama, logo, button_*)."""
    if name in _CACHED_UI_TEX:
        return _CACHED_UI_TEX[name]
    from ursina import Texture
    path = UI_DIR / f"{name}.png"
    try:
        if not path.exists():
            generate_ui_textures()
        img = Image.open(path).convert("RGBA")
    except Exception:
        return None
    tex = Texture(img)
    tex.filtering = None if name != "panorama" else "bilinear"
    _CACHED_UI_TEX[name] = tex
    return tex


_CACHED_MOB_TEX: Dict[str, object] = {}
_CACHED_UI_TEX: Dict[str, object] = {}


# Cached runtime Ursina Texture objects
_CACHED_ATLAS_TEX = None
_CACHED_ICON_TEX: Dict[str, object] = {}


def get_atlas_texture():
    """Return the Ursina Texture for the block atlas, regenerating in memory if file is missing."""
    global _CACHED_ATLAS_TEX
    if _CACHED_ATLAS_TEX is not None:
        return _CACHED_ATLAS_TEX

    from ursina import Texture

    atlas_path = TEXTURES_DIR / "atlas.png"
    try:
        if atlas_path.exists():
            img = Image.open(atlas_path).convert("RGBA")
        else:
            img = generate_atlas_image()
    except Exception:
        img = generate_atlas_image()

    tex = Texture(img)
    tex.filtering = "nearest"
    _CACHED_ATLAS_TEX = tex
    return tex


def get_item_icon_texture(item_key: Optional[str]):
    """Return the Ursina Texture for an item's 32x32 UI icon, with in-memory fallback."""
    if not item_key:
        return None
    if item_key in _CACHED_ICON_TEX:
        return _CACHED_ICON_TEX[item_key]

    from ursina import Texture

    icon_path = ICONS_DIR / f"{item_key}.png"
    try:
        if icon_path.exists():
            img = Image.open(icon_path).convert("RGBA")
        else:
            img = generate_item_icon(item_key)
    except Exception:
        img = generate_item_icon(item_key)

    tex = Texture(img)
    tex.filtering = "nearest"
    _CACHED_ICON_TEX[item_key] = tex
    return tex


def play_game_sound(name: str, settings=None) -> None:
    """Play a game sound effect safely if sound effects are enabled and audio is available."""
    if settings is not None:
        if not getattr(settings, "sound_effects", True):
            return
        vol = float(getattr(settings, "volume", 0.7))
        if vol <= 0.01:
            return
    else:
        vol = 0.7

    try:
        from ursina import Audio, application
        # Skip if running in headless null-audio mode
        if hasattr(application, "base") and application.base is not None:
            am = getattr(application.base, "sfxManagerList", None)
            if not am:
                return
        wav_path = SOUNDS_DIR / f"{name}.wav"
        if wav_path.exists():
            rel_path = f"assets/sounds/{name}.wav"
            Audio(rel_path, volume=vol, autoplay=True)
    except Exception:
        pass
