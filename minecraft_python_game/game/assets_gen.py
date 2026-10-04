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


def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


def _generate_tile_image(tile_name: str, seed: int = 1337) -> Image.Image:
    """Create a 16x16 RGBA pixel-art tile for the given tile name."""
    rng = np.random.RandomState(seed + ( abs(hash(tile_name)) % 10000 ))
    img = Image.new("RGBA", (TILE_PIXEL_SIZE, TILE_PIXEL_SIZE), (128, 128, 128, 255))
    px = img.load()

    def fill_noisy(base_rgb: Tuple[int, int, int], variance: int = 12, alpha: int = 255):
        for y in range(16):
            for x in range(16):
                dv = int(rng.randint(-variance, variance + 1))
                px[x, y] = (
                    _clamp(base_rgb[0] + dv),
                    _clamp(base_rgb[1] + dv),
                    _clamp(base_rgb[2] + dv),
                    alpha,
                )

    if tile_name == "grass_top":
        fill_noisy((92, 168, 58), 14)
        for _ in range(18):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[x, y] = (112, 192, 72, 255)
    elif tile_name == "dirt":
        fill_noisy((134, 94, 64), 14)
        for _ in range(20):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[x, y] = (108, 74, 48, 255)
    elif tile_name == "grass_side":
        fill_noisy((134, 94, 64), 14)
        for x in range(16):
            fringe = 3 + int(rng.randint(0, 3))
            for y in range(fringe):
                dv = int(rng.randint(-10, 11))
                px[x, y] = (_clamp(92 + dv), _clamp(168 + dv), _clamp(58 + dv), 255)
    elif tile_name == "stone":
        fill_noisy((128, 130, 134), 12)
        for y in range(0, 16, 4):
            x_start = rng.randint(0, 10)
            for x in range(x_start, min(16, x_start + 5)):
                px[x, y] = (104, 106, 110, 255)
    elif tile_name == "cobblestone":
        fill_noisy((118, 118, 122), 18)
        for y in range(16):
            for x in range(16):
                if (x + (y // 2) * 3) % 5 == 0 or (y + (x // 3)) % 5 == 0:
                    px[x, y] = (76, 76, 80, 255)
    elif tile_name == "sand":
        fill_noisy((224, 210, 150), 10)
        for y in range(2, 16, 4):
            for x in range(16):
                if (x + y) % 3 == 0:
                    px[x, y] = (236, 224, 168, 255)
    elif tile_name == "gravel":
        fill_noisy((136, 130, 126), 22)
    elif tile_name == "wood_side":
        for y in range(16):
            for x in range(16):
                stripe = int(math.sin(x * 1.3) * 10) + int(rng.randint(-6, 7))
                px[x, y] = (_clamp(108 + stripe), _clamp(78 + stripe), _clamp(46 + stripe), 255)
    elif tile_name == "wood_top":
        fill_noisy((168, 132, 82), 8)
        for y in range(16):
            for x in range(16):
                if x in (0, 15) or y in (0, 15):
                    px[x, y] = (102, 72, 42, 255)
                elif x in (3, 12) or y in (3, 12):
                    px[x, y] = (142, 108, 64, 255)
    elif tile_name == "leaves":
        fill_noisy((54, 134, 42), 18)
        for _ in range(24):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[x, y] = (36, 94, 28, 255)
    elif tile_name == "glass":
        for y in range(16):
            for x in range(16):
                if x in (0, 15) or y in (0, 15):
                    px[x, y] = (205, 242, 250, 255)
                elif (x + y) in (4, 5, 11):
                    px[x, y] = (235, 252, 255, 230)
                else:
                    px[x, y] = (170, 225, 240, 75)
    elif tile_name in ("coal_ore", "iron_ore", "gold_ore", "diamond_ore"):
        fill_noisy((128, 130, 134), 11)
        ore_colors = {
            "coal_ore": (32, 32, 36),
            "iron_ore": (208, 162, 132),
            "gold_ore": (250, 214, 54),
            "diamond_ore": (76, 238, 248),
        }
        oc = ore_colors[tile_name]
        spots = [(3, 3), (4, 3), (3, 4), (10, 4), (11, 5), (5, 10), (6, 10), (5, 11), (11, 11), (12, 11), (11, 12)]
        for sx, sy in spots:
            px[sx, sy] = (oc[0], oc[1], oc[2], 255)
    elif tile_name == "water":
        for y in range(16):
            for x in range(16):
                wave_v = int(math.sin((x + y) * 0.8) * 12)
                px[x, y] = (_clamp(38 + wave_v), _clamp(116 + wave_v), _clamp(218 + wave_v), 195)
    elif tile_name == "bedrock":
        fill_noisy((48, 48, 52), 28)
        for _ in range(30):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[x, y] = (22, 22, 25, 255)
    elif tile_name == "planks":
        fill_noisy((174, 136, 84), 8)
        for y in (0, 4, 8, 12):
            for x in range(16):
                px[x, y] = (132, 98, 56, 255)
        for y in range(16):
            joint_x = ((y // 4) * 7 + 3) % 16
            px[joint_x, y] = (132, 98, 56, 255)
    elif tile_name == "crafting_top":
        fill_noisy((166, 122, 72), 6)
        for i in range(16):
            px[i, 0] = px[i, 15] = px[0, i] = px[15, i] = (96, 64, 34, 255)
        for g in (5, 10):
            for i in range(2, 14):
                px[g, i] = (88, 58, 30, 255)
                px[i, g] = (88, 58, 30, 255)
    elif tile_name == "crafting_side":
        fill_noisy((166, 122, 72), 8)
        for y in range(4):
            for x in range(16):
                px[x, y] = (112, 76, 42, 255)
        for y in range(5, 13):
            for x in (4, 5, 10, 11):
                px[x, y] = (90, 95, 105, 255)
    elif tile_name == "furnace_front":
        fill_noisy((118, 118, 124), 10)
        for y in range(4, 14):
            for x in range(4, 12):
                if y < 9:
                    px[x, y] = (32, 32, 36, 255)
                else:
                    px[x, y] = (242, 132, 38, 255)
    elif tile_name in ("furnace_side", "furnace_top"):
        fill_noisy((118, 118, 124), 10)
        for i in range(16):
            px[i, 0] = px[i, 15] = px[0, i] = px[15, i] = (84, 84, 90, 255)
    elif tile_name == "torch":
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        px = img.load()
        for y in range(6, 16):
            for x in (7, 8):
                px[x, y] = (148, 108, 58, 255)
        for y in range(3, 6):
            for x in (6, 7, 8, 9):
                px[x, y] = (255, 210, 60, 255)
        px[7, 2] = px[8, 2] = (255, 120, 30, 255)
    elif tile_name in ("chest_front", "chest_side", "chest_top"):
        fill_noisy((168, 118, 52), 8)
        for i in range(16):
            px[i, 0] = px[i, 15] = px[0, i] = px[15, i] = (82, 54, 22, 255)
        if tile_name != "chest_top":
            for x in range(16):
                px[x, 6] = (62, 42, 18, 255)
        if tile_name == "chest_front":
            for y in range(5, 9):
                for x in range(7, 9):
                    px[x, y] = (235, 210, 90, 255)

    return img


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
    """Create a 32x32 RGBA pixel-art icon for an inventory item, block, tool, or food."""
    item = ITEMS.get(item_key)
    img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if item is None:
        draw.rectangle([4, 4, 27, 27], fill=(180, 180, 180, 255))
        return img

    # If it's a block item, compose an isometric/framed block preview from its tile
    if item.category == "block" and item_key in BLOCKS_BY_KEY:
        bdef = BLOCKS_BY_KEY[item_key]
        side_tile_name = bdef.faces.get("north", bdef.faces.get("side", "stone"))
        top_tile_name = bdef.faces.get("top", side_tile_name)
        side_tile = _generate_tile_image(side_tile_name).resize((22, 22), Image.Resampling.NEAREST)
        top_tile = _generate_tile_image(top_tile_name).resize((22, 8), Image.Resampling.NEAREST)
        img.paste(top_tile, (5, 3), top_tile)
        img.paste(side_tile, (5, 8), side_tile)
        draw.rectangle([4, 3, 27, 29], outline=(30, 30, 35, 220), width=1)
        return img

    c = item.icon_color
    dark_c = (_clamp(c[0] * 0.65), _clamp(c[1] * 0.65), _clamp(c[2] * 0.65), 255)
    full_c = (c[0], c[1], c[2], 255)
    handle_c = (138, 98, 52, 255)

    if item.tool_type == "pickaxe":
        # Diagonal handle
        draw.line([(6, 26), (22, 10)], fill=handle_c, width=3)
        # Curved pickaxe head
        draw.line([(14, 6), (25, 7), (26, 18)], fill=full_c, width=4)
        draw.line([(14, 6), (25, 7), (26, 18)], fill=dark_c, width=1)
    elif item.tool_type == "axe":
        draw.line([(6, 26), (23, 9)], fill=handle_c, width=3)
        draw.polygon([(15, 6), (26, 8), (23, 18), (16, 13)], fill=full_c, outline=dark_c)
    elif item.tool_type == "sword":
        # Pommel & Handle
        draw.line([(5, 27), (11, 21)], fill=handle_c, width=3)
        # Crossguard
        draw.line([(8, 17), (15, 24)], fill=dark_c, width=3)
        # Blade
        draw.line([(12, 20), (26, 6)], fill=full_c, width=4)
        draw.point((27, 5), fill=full_c)
    elif item.key == "stick":
        draw.line([(7, 25), (25, 7)], fill=handle_c, width=4)
    elif item.category == "food":
        draw.ellipse([6, 8, 25, 25], fill=full_c, outline=dark_c, width=2)
        draw.ellipse([10, 11, 15, 15], fill=(255, 235, 220, 190))
    else:
        # Ingot / gem / coal / bone
        draw.polygon([(8, 18), (14, 8), (24, 10), (22, 22), (12, 24)], fill=full_c, outline=dark_c)
        draw.line([(13, 12), (19, 12)], fill=(255, 255, 255, 200), width=2)

    return img


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


def ensure_all_assets() -> None:
    """Ensure all procedural textures, icons, sounds, and models exist on disk."""
    try:
        TEXTURES_DIR.mkdir(parents=True, exist_ok=True)
        ICONS_DIR.mkdir(parents=True, exist_ok=True)
        SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

        atlas_path = TEXTURES_DIR / "atlas.png"
        if not atlas_path.exists():
            atlas_img = generate_atlas_image()
            atlas_img.save(atlas_path)

        for item_key in ITEMS:
            icon_path = ICONS_DIR / f"{item_key}.png"
            if not icon_path.exists():
                icon_img = generate_item_icon(item_key)
                icon_img.save(icon_path)

        if not (SOUNDS_DIR / "dig.wav").exists():
            generate_sound_files()

        if not (MODELS_DIR / "cube_block.obj").exists():
            generate_model_files()
    except Exception as exc:
        print(f"[Assets] Warning while writing asset files: {exc}")


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
