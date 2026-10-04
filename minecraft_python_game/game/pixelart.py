"""
Hand-tuned procedural pixel art for PyCraft.

Everything here is generated with NumPy/Pillow only (no external assets):
  * 16x16 block tiles with palette-quantised, clustered noise, bevels and shading
  * 32x32 item icons drawn as 16x16 sprites with automatic outlines
  * isometric block icons rendered straight from the block tiles
  * 64x32-style mob skins (pig, cow, zombie, skeleton) used by textured mob meshes
  * the main-menu background panorama, logo and button textures

All generators are deterministic (seeded with CRC32 of the asset name) so the
committed PNGs are reproducible.
"""

import math
import zlib
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RGB = Tuple[int, int, int]
RGBA = Tuple[int, int, int, int]

# Bump when any generator changes so cached PNGs on disk are rebuilt.
ART_VERSION = 6


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _rng(name: str, salt: int = 0) -> np.random.RandomState:
    return np.random.RandomState((zlib.crc32(name.encode("utf-8")) + salt * 7919) & 0x7FFFFFFF)


def _clamp(v: float) -> int:
    return max(0, min(255, int(round(v))))


def shade(c: Sequence[int], f: float) -> RGB:
    return (_clamp(c[0] * f), _clamp(c[1] * f), _clamp(c[2] * f))


def mix(a: Sequence[int], b: Sequence[int], t: float) -> RGB:
    return (
        _clamp(a[0] + (b[0] - a[0]) * t),
        _clamp(a[1] + (b[1] - a[1]) * t),
        _clamp(a[2] + (b[2] - a[2]) * t),
    )


def _opaque(c: Sequence[int]) -> RGBA:
    return (int(c[0]), int(c[1]), int(c[2]), 255)


def smooth_noise(rng: np.random.RandomState, size: int = 16, mix_white: float = 0.45) -> np.ndarray:
    """Tileable value noise in [0, 1): blurred random field blended with white noise."""
    white = rng.rand(size, size)
    blurred = white.copy()
    for _ in range(2):
        blurred = (
            blurred * 4
            + np.roll(blurred, 1, 0) + np.roll(blurred, -1, 0)
            + np.roll(blurred, 1, 1) + np.roll(blurred, -1, 1)
        ) / 8.0
    blurred = (blurred - blurred.min()) / max(1e-6, blurred.max() - blurred.min())
    out = blurred * (1.0 - mix_white) + white * mix_white
    return (out - out.min()) / max(1e-6, out.max() - out.min())


def quantise(field: np.ndarray, palette: Sequence[RGB]) -> np.ndarray:
    """Map a [0,1] field onto a palette -> (H, W, 4) uint8 array."""
    n = len(palette)
    idx = np.clip((field * n).astype(int), 0, n - 1)
    h, w = field.shape
    out = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            out[y, x] = _opaque(palette[idx[y, x]])
    return out


def to_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def voronoi_cells(rng: np.random.RandomState, count: int, size: int = 16):
    """Tileable Voronoi: returns (cell_id, edge_distance) arrays for a size x size tile."""
    pts = rng.rand(count, 2) * size
    ys, xs = np.mgrid[0:size, 0:size]
    best = np.full((size, size), 1e9)
    second = np.full((size, size), 1e9)
    ids = np.zeros((size, size), dtype=int)
    for i, (px, py) in enumerate(pts):
        for ox in (-size, 0, size):
            for oy in (-size, 0, size):
                d = np.sqrt((xs + 0.5 - (px + ox)) ** 2 + (ys + 0.5 - (py + oy)) ** 2)
                closer = d < best
                second = np.where(closer, best, np.minimum(second, d))
                ids = np.where(closer, i, ids)
                best = np.where(closer, d, best)
    return ids, second - best


def line_points(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return pts


# ---------------------------------------------------------------------------
# Block tiles (16x16)
# ---------------------------------------------------------------------------

GRASS_PAL = [(70, 128, 38), (84, 148, 48), (98, 166, 58), (114, 184, 70)]
DIRT_PAL = [(104, 70, 44), (120, 82, 54), (134, 94, 62), (148, 108, 74)]
STONE_PAL = [(108, 108, 112), (120, 120, 124), (132, 132, 136), (144, 144, 148)]
PLANK_PAL = [(158, 120, 70), (170, 132, 80), (182, 144, 90)]
MORTAR = (66, 66, 70)


def _stone_base(rng, palette=STONE_PAL) -> np.ndarray:
    return quantise(smooth_noise(rng, 16, 0.5), palette)


def _cobble(rng, light: float = 1.0) -> np.ndarray:
    ids, edge = voronoi_cells(rng, 10)
    pal = [(104, 104, 108), (120, 120, 124), (136, 136, 140), (150, 150, 154)]
    out = np.zeros((16, 16, 4), dtype=np.uint8)
    for y in range(16):
        for x in range(16):
            base = pal[ids[y, x] % len(pal)]
            jitter = rng.randint(-5, 6)
            c = (base[0] + jitter, base[1] + jitter, base[2] + jitter)
            if edge[y, x] < 1.25:
                c = MORTAR
            out[y, x] = _opaque(shade(c, light))
    # Bevel: light on top/left edges next to mortar, dark on bottom/right
    res = out.copy()
    for y in range(16):
        for x in range(16):
            if tuple(out[y, x][:3]) == shade(MORTAR, light):
                continue
            up = tuple(out[(y - 1) % 16, x][:3]) == shade(MORTAR, light)
            lf = tuple(out[y, (x - 1) % 16][:3]) == shade(MORTAR, light)
            dn = tuple(out[(y + 1) % 16, x][:3]) == shade(MORTAR, light)
            rt = tuple(out[y, (x + 1) % 16][:3]) == shade(MORTAR, light)
            c = tuple(int(v) for v in out[y, x][:3])
            if up or lf:
                c = shade(c, 1.14)
            elif dn or rt:
                c = shade(c, 0.88)
            res[y, x] = _opaque(c)
    return res


def _planks_array(rng, boards: int = 4, base_shift: float = 1.0) -> np.ndarray:
    out = np.zeros((16, 16, 4), dtype=np.uint8)
    bh = 16 // boards
    for b in range(boards):
        tone = PLANK_PAL[rng.randint(0, len(PLANK_PAL))]
        tone = shade(tone, base_shift)
        joint = int(rng.randint(2, 14))
        grain_y = rng.randint(1, bh - 1)
        for y in range(bh):
            for x in range(16):
                yy = b * bh + y
                c = tone
                n = rng.randint(-4, 5)
                c = (c[0] + n, c[1] + n, c[2] + n)
                if y == bh - 1:
                    c = shade(tone, 0.68)
                elif y == 0:
                    c = shade(tone, 1.10)
                elif y == grain_y and (x + b * 3) % 7 < 5:
                    c = shade(tone, 0.90)
                if x == joint and y < bh - 1:
                    c = shade(tone, 0.66)
                out[yy, x] = _opaque(c)
    return out


def _tile_array(name: str) -> Optional[np.ndarray]:
    rng = _rng(name)
    px = np.zeros((16, 16, 4), dtype=np.uint8)

    if name == "grass_top":
        px = quantise(smooth_noise(rng, 16, 0.55), GRASS_PAL)
        for _ in range(10):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[y, x] = _opaque(shade(GRASS_PAL[0], 0.85))
        return px

    if name == "dirt":
        px = quantise(smooth_noise(rng, 16, 0.5), DIRT_PAL)
        for _ in range(7):
            x, y = rng.randint(0, 16), rng.randint(0, 15)
            px[y, x] = _opaque((92, 60, 38))
            if rng.rand() < 0.5:
                px[y, (x + 1) % 16] = _opaque((92, 60, 38))
        for _ in range(6):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[y, x] = _opaque((160, 124, 90))
        return px

    if name == "grass_side":
        px = _tile_array("dirt").copy()
        for x in range(16):
            depth = 3 + int(rng.randint(0, 3))
            if rng.rand() < 0.25:
                depth += 1
            for y in range(depth):
                tone = GRASS_PAL[min(3, max(0, 3 - y + rng.randint(-1, 2)))]
                if y == depth - 1:
                    tone = shade(GRASS_PAL[0], 0.82)
                px[y, x] = _opaque(tone)
        for x in range(16):
            px[0, x] = _opaque(GRASS_PAL[3] if rng.rand() < 0.6 else GRASS_PAL[2])
        return px

    if name == "stone":
        px = _stone_base(rng)
        for _ in range(3):
            x, y = rng.randint(1, 13), rng.randint(1, 15)
            for k in range(rng.randint(2, 5)):
                px[y, x + k] = _opaque((92, 92, 96))
                if rng.rand() < 0.4 and y + 1 < 16:
                    y += 1
        for _ in range(8):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[y, x] = _opaque((156, 156, 160))
        return px

    if name == "cobblestone":
        return _cobble(rng)

    if name == "sand":
        pal = [(208, 192, 136), (218, 203, 148), (228, 214, 160), (238, 225, 174)]
        px = quantise(smooth_noise(rng, 16, 0.65), pal)
        for _ in range(14):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[y, x] = _opaque((192, 174, 118))
        return px

    if name == "gravel":
        ids, edge = voronoi_cells(rng, 22)
        pal = [(112, 106, 102), (132, 126, 122), (150, 144, 140), (96, 92, 90), (166, 160, 156)]
        for y in range(16):
            for x in range(16):
                c = pal[ids[y, x] % len(pal)]
                j = rng.randint(-4, 5)
                c = (c[0] + j, c[1] + j, c[2] + j)
                if edge[y, x] < 0.9:
                    c = shade(c, 0.62)
                px[y, x] = _opaque(c)
        return px

    if name == "wood_side":
        pal = [(66, 48, 28), (80, 58, 34), (94, 70, 42), (108, 82, 50)]
        col_tone = rng.randint(0, 4, size=16)
        for x in range(16):
            for y in range(16):
                t = col_tone[x]
                if rng.rand() < 0.22:
                    t = max(0, min(3, t + rng.choice([-1, 1])))
                px[y, x] = _opaque(pal[t])
            if x % 4 == 0:
                for y in range(16):
                    px[y, x] = _opaque(shade(pal[0], 0.85))
        for _ in range(2):
            kx, ky = rng.randint(2, 13), rng.randint(2, 13)
            px[ky, kx] = _opaque((44, 30, 16))
            px[ky + 1, kx] = _opaque((44, 30, 16))
            px[ky, kx + 1] = _opaque((58, 40, 22))
        return px

    if name == "wood_top":
        for y in range(16):
            for x in range(16):
                d = max(abs(x - 7.5), abs(y - 7.5))
                if d > 6.6:
                    c = (86, 64, 38) if (x + y) % 2 else (96, 72, 44)
                else:
                    ring = int(d * 1.05)
                    c = (178, 142, 90) if ring % 2 == 0 else (156, 120, 72)
                    if d < 1.5:
                        c = (134, 98, 56)
                    c = shade(c, 1.0 + rng.randint(-3, 4) / 60.0)
                px[y, x] = _opaque(c)
        return px

    if name == "leaves":
        pal = [(24, 78, 26), (34, 98, 32), (48, 120, 40), (66, 144, 52)]
        px = quantise(smooth_noise(rng, 16, 0.55), pal)
        for _ in range(16):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[y, x] = _opaque((84, 168, 62))
        for _ in range(10):
            x, y = rng.randint(0, 15), rng.randint(0, 16)
            px[y, x] = _opaque((16, 54, 20))
            px[y, x + 1] = _opaque((18, 60, 22))
        return px

    if name == "glass":
        for y in range(16):
            for x in range(16):
                if x in (0, 15) or y in (0, 15):
                    px[y, x] = (206, 240, 250, 255)
                else:
                    px[y, x] = (176, 228, 240, 46)
        for i in range(3, 8):
            px[i, 12 - i + 2] = (245, 253, 255, 235)
        for i in range(2):
            px[9 + i, 10 - i + 1] = (240, 252, 255, 200)
        px[1, 1] = px[1, 14] = px[14, 1] = px[14, 14] = (150, 205, 220, 255)
        return px

    if name in ("coal_ore", "iron_ore", "gold_ore", "diamond_ore"):
        px = _stone_base(rng).copy()
        pal = {
            "coal_ore": ((20, 20, 24), (44, 44, 50), (74, 74, 82)),
            "iron_ore": ((168, 116, 84), (206, 156, 122), (236, 202, 176)),
            "gold_ore": ((206, 150, 20), (248, 206, 54), (255, 240, 150)),
            "diamond_ore": ((30, 150, 170), (72, 222, 232), (200, 255, 255)),
        }[name]
        dark, mid, light = pal
        occupied = set()
        centers = [(3, 3), (10, 2), (6, 8), (12, 9), (3, 12), (9, 13)]
        rng.shuffle(centers)
        for cx, cy in centers[:5]:
            cx += int(rng.randint(-1, 2))
            cy += int(rng.randint(-1, 2))
            cells = [(cx, cy)]
            for _ in range(rng.randint(4, 8)):
                bx, by = cells[rng.randint(0, len(cells))]
                dx, dy = [(1, 0), (0, 1), (-1, 0), (0, -1)][rng.randint(0, 4)]
                cells.append((bx + dx, by + dy))
            for (x, y) in cells:
                if 0 <= x < 16 and 0 <= y < 16:
                    occupied.add((x, y))
        for (x, y) in occupied:
            c = mid
            if (x, y - 1) not in occupied and (x - 1, y) not in occupied:
                c = light
            elif (x + 1, y) not in occupied or (x, y + 1) not in occupied:
                c = dark
            px[y, x] = _opaque(c)
        if name == "diamond_ore":
            for (x, y) in list(occupied)[:3]:
                px[y, x] = _opaque(light)
        return px

    if name == "water":
        for y in range(16):
            for x in range(16):
                w = math.sin((x + y * 0.5) * 0.9) + math.sin(y * 1.3 + x * 0.3) * 0.7
                base = (34 + w * 7, 96 + w * 10, 206 + w * 8)
                px[y, x] = (_clamp(base[0]), _clamp(base[1]), _clamp(base[2]), 208)
        for _ in range(9):
            x, y = rng.randint(0, 14), rng.randint(0, 16)
            px[y, x] = (130, 190, 255, 225)
            px[y, x + 1] = (110, 172, 250, 218)
        return px

    if name == "bedrock":
        pal = [(24, 24, 28), (42, 42, 46), (62, 62, 66), (84, 84, 88)]
        px = quantise(smooth_noise(rng, 16, 0.3), pal)
        for _ in range(12):
            x, y = rng.randint(0, 15), rng.randint(0, 16)
            px[y, x] = _opaque((16, 16, 18))
            px[y, x + 1] = _opaque((20, 20, 22))
        for _ in range(8):
            x, y = rng.randint(0, 16), rng.randint(0, 16)
            px[y, x] = _opaque((100, 100, 104))
        return px

    if name == "planks":
        return _planks_array(rng)

    if name == "crafting_top":
        px = _planks_array(rng, boards=4, base_shift=0.92)
        frame = (86, 56, 30)
        for i in range(16):
            for edge in (0, 1, 14, 15):
                px[edge, i] = _opaque(frame if edge in (0, 15) else shade(frame, 1.25))
                px[i, edge] = _opaque(frame if edge in (0, 15) else shade(frame, 1.25))
        for g in (5, 10):
            for i in range(2, 14):
                px[g, i] = _opaque((104, 72, 40))
                px[i, g] = _opaque((104, 72, 40))
        for (x, y) in ((3, 3), (12, 3), (3, 12), (12, 12)):
            px[y, x] = _opaque((196, 160, 104))
        return px

    if name == "crafting_side":
        px = _planks_array(rng, boards=4, base_shift=0.9)
        for y in range(4):
            for x in range(16):
                px[y, x] = _opaque(shade((112, 76, 42), 1.0 + (x % 2) * 0.05))
        for x in range(16):
            px[4, x] = _opaque((70, 46, 24))
        # hanging saw
        for y in range(6, 13):
            px[y, 3] = _opaque((170, 176, 186))
            px[y, 4] = _opaque((130, 136, 146))
        px[13, 3] = px[13, 4] = _opaque((92, 62, 34))
        # hammer
        for y in range(7, 14):
            px[y, 10] = _opaque((128, 90, 50))
        px[6, 9] = px[6, 10] = px[6, 11] = px[7, 9] = px[7, 11] = _opaque((156, 160, 170))
        # legs
        for y in range(5, 16):
            px[y, 0] = _opaque((84, 56, 30))
            px[y, 15] = _opaque((84, 56, 30))
        return px

    if name == "furnace_front":
        px = _cobble(rng, 1.0).copy()
        for y in range(2, 8):
            for x in range(3, 13):
                px[y, x] = _opaque((22, 22, 26))
        for x in range(3, 13):
            px[1, x] = _opaque((54, 54, 58))
            px[8, x] = _opaque((54, 54, 58))
        for y in range(9, 14):
            for x in range(3, 13):
                t = (y - 9) / 4.0
                c = mix((255, 220, 70), (200, 70, 20), t)
                if (x + y) % 3 == 0:
                    c = shade(c, 0.88)
                px[y, x] = _opaque(c)
        for x in range(3, 13):
            px[14, x] = _opaque((48, 48, 52))
        px[8, 3] = px[8, 12] = _opaque((54, 54, 58))
        for x in range(5, 11):
            px[3, x] = _opaque((36, 36, 40))
        return px

    if name == "furnace_side":
        px = _cobble(rng, 1.0).copy()
        return px

    if name == "furnace_top":
        px = _cobble(rng, 1.05).copy()
        for i in range(2, 14):
            for edge in (2, 13):
                px[edge, i] = _opaque((58, 58, 62))
                px[i, edge] = _opaque((58, 58, 62))
        for y in range(3, 13):
            for x in range(3, 13):
                px[y, x] = _opaque(shade(STONE_PAL[(x + y) % 2], 0.82))
        return px

    if name == "torch":
        # stick
        for y in range(7, 16):
            px[y, 7] = _opaque((176, 134, 74))
            px[y, 8] = _opaque((120, 86, 44))
        px[15, 7] = _opaque((140, 104, 56))
        px[15, 8] = _opaque((92, 64, 32))
        # charred head
        px[6, 7] = _opaque((74, 52, 30))
        px[6, 8] = _opaque((52, 36, 20))
        # flame
        flame = {
            (7, 5): (255, 214, 70), (8, 5): (255, 190, 50),
            (7, 4): (255, 236, 130), (8, 4): (255, 200, 60),
            (6, 4): (250, 150, 30), (9, 4): (240, 120, 24),
            (7, 3): (255, 170, 40), (8, 3): (250, 130, 28),
            (7, 2): (240, 110, 24), (8, 2): (210, 70, 20),
            (6, 5): (240, 140, 30), (9, 5): (220, 100, 24),
        }
        for (x, y), c in flame.items():
            px[y, x] = _opaque(c)
        return px

    if name in ("chest_front", "chest_side", "chest_top"):
        px = _planks_array(rng, boards=4, base_shift=0.88)
        outline = (50, 32, 14)
        for i in range(16):
            px[0, i] = px[15, i] = px[i, 0] = px[i, 15] = _opaque(outline)
            px[1, i] = _opaque(shade(PLANK_PAL[2], 1.05)) if name == "chest_top" else px[1, i]
        if name != "chest_top":
            for x in range(16):
                px[5, x] = _opaque(outline)
                px[6, x] = _opaque((98, 66, 32))
            for y in range(16):
                px[y, 0] = px[y, 15] = _opaque(outline)
                px[y, 1] = _opaque(shade(PLANK_PAL[2], 1.02)) if y > 6 else px[y, 1]
        if name == "chest_front":
            for y in range(4, 9):
                for x in range(6, 10):
                    px[y, x] = _opaque((180, 184, 192) if y < 7 else (150, 154, 162))
            px[4, 6:10] = _opaque((60, 60, 66))
            px[6, 7] = px[6, 8] = _opaque((40, 40, 46))
            px[7, 7] = px[7, 8] = _opaque((236, 204, 92))
        if name == "chest_top":
            for i in range(2, 14):
                px[i, 2] = _opaque((98, 66, 32))
                px[i, 13] = _opaque((98, 66, 32))
                px[2, i] = _opaque((98, 66, 32))
                px[13, i] = _opaque((98, 66, 32))
        return px

    return None


def generate_tile(tile_name: str) -> Image.Image:
    arr = _tile_array(tile_name)
    if arr is None:
        arr = np.full((16, 16, 4), (255, 0, 255, 255), dtype=np.uint8)
    return to_image(arr)


# ---------------------------------------------------------------------------
# Isometric block icons (32x32)
# ---------------------------------------------------------------------------

def render_iso_block(top: Image.Image, left: Image.Image, right: Image.Image, size: int = 32) -> Image.Image:
    """Render a shaded isometric cube icon from three 16x16 tiles."""
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    po = out.load()
    tp, lp, rp = top.convert("RGBA").load(), left.convert("RGBA").load(), right.convert("RGBA").load()
    s = size / 32.0
    for py in range(size):
        for px_ in range(size):
            sx = (px_ + 0.5) / s
            sy = (py + 0.5) / s
            # Top face (h = 1)
            ab_d = (sx - 16) / 14.0
            ab_s = (sy - 2) / 7.0
            a, b = (ab_s + ab_d) / 2.0, (ab_s - ab_d) / 2.0
            if 0 <= a < 1 and 0 <= b < 1:
                c = tp[min(15, int(a * 16)), min(15, int(b * 16))]
                po[px_, py] = _shade_px(c, 1.0)
                continue
            # Left face (b = 1)
            a = 1 + (sx - 16) / 14.0
            h = (23 + 7 * a - sy) / 14.0
            if 0 <= a < 1 and 0 <= h < 1:
                c = lp[min(15, int(a * 16)), min(15, int((1 - h) * 16))]
                po[px_, py] = _shade_px(c, 0.82)
                continue
            # Right face (a = 1)
            bb = 1 - (sx - 16) / 14.0
            h = (23 + 7 * bb - sy) / 14.0
            if 0 <= bb < 1 and 0 <= h < 1:
                u = min(15, int((1 - bb) * 16))
                c = rp[u, min(15, int((1 - h) * 16))]
                po[px_, py] = _shade_px(c, 0.62)
    return _add_outline(out, (18, 18, 24, 255), inner=False)


def _shade_px(c, f):
    if c[3] == 0:
        return (0, 0, 0, 0)
    a = max(c[3], 150) if c[3] < 255 else 255
    return (_clamp(c[0] * f), _clamp(c[1] * f), _clamp(c[2] * f), a)


def _add_outline(img: Image.Image, color: RGBA, inner: bool = False) -> Image.Image:
    w, h = img.size
    src = img.load()
    out = img.copy()
    po = out.load()
    for y in range(h):
        for x in range(w):
            if src[x, y][3] != 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and src[nx, ny][3] > 0:
                    po[x, y] = color
                    break
    return out


# ---------------------------------------------------------------------------
# Item sprites (16x16 -> upscaled to 32x32)
# ---------------------------------------------------------------------------

TIER_PALETTES: Dict[str, Tuple[RGB, RGB, RGB]] = {
    # (dark, mid, light)
    "wooden": ((112, 78, 40), (160, 120, 68), (196, 156, 96)),
    "stone": ((92, 92, 98), (134, 134, 140), (176, 176, 182)),
    "iron": ((150, 154, 164), (212, 216, 224), (248, 250, 255)),
    "diamond": ((30, 160, 180), (76, 226, 236), (200, 255, 255)),
}
HANDLE = ((84, 56, 28), (128, 92, 50), (160, 120, 70))


class Sprite:
    def __init__(self, size: int = 16):
        self.size = size
        self.img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self.px = self.img.load()

    def set(self, x: int, y: int, c: Sequence[int]) -> None:
        if 0 <= x < self.size and 0 <= y < self.size:
            self.px[x, y] = (c[0], c[1], c[2], 255)

    def get(self, x: int, y: int):
        if 0 <= x < self.size and 0 <= y < self.size:
            return self.px[x, y]
        return (0, 0, 0, 0)

    def line(self, p0, p1, c) -> None:
        for (x, y) in line_points(p0[0], p0[1], p1[0], p1[1]):
            self.set(x, y, c)

    def rows(self, spec: Dict[int, Tuple[int, int]], palette: Tuple[RGB, RGB, RGB]) -> None:
        """Fill horizontal spans with simple top-left lit shading."""
        dark, mid, light = palette
        filled = set()
        for y, (x0, x1) in spec.items():
            for x in range(x0, x1 + 1):
                filled.add((x, y))
        for (x, y) in filled:
            c = mid
            if (x, y - 1) not in filled or (x - 1, y) not in filled:
                c = light
            if (x, y + 1) not in filled or (x + 1, y) not in filled:
                c = dark if ((x, y - 1) in filled and (x - 1, y) in filled) else mid
            self.set(x, y, c)

    def finish(self, out_size: int = 32) -> Image.Image:
        outlined = _add_outline(self.img, (20, 16, 24, 255))
        # outline needs a 1px border, so draw on a canvas that has it
        return outlined.resize((out_size, out_size), Image.NEAREST)


def _handle_line(sp: Sprite, p0, p1) -> None:
    for i, (x, y) in enumerate(line_points(p0[0], p0[1], p1[0], p1[1])):
        sp.set(x, y, HANDLE[1] if i % 2 == 0 else HANDLE[1])
        sp.set(x + 1, y, HANDLE[0]) if sp.get(x + 1, y)[3] == 0 else None


def _sprite_pickaxe(pal) -> Image.Image:
    sp = Sprite()
    dark, mid, light = pal
    # Handle from bottom-left to the head
    for i, (x, y) in enumerate(line_points(2, 14, 11, 5)):
        sp.set(x, y, HANDLE[1])
        sp.set(x, y + 1, HANDLE[0]) if i > 0 else None
    # Head: curved bar
    head = [(3, 6), (4, 4), (5, 3), (6, 2), (7, 2), (8, 2), (9, 2), (10, 3), (11, 3), (12, 4), (13, 5), (13, 6), (13, 7)]
    arc = [(2, 7), (3, 5), (4, 4), (5, 3), (6, 3), (7, 3), (8, 3), (9, 3), (10, 4), (11, 4), (12, 5), (12, 6), (12, 7)]
    for (x, y) in arc:
        sp.set(x, y, mid)
    for (x, y) in head:
        sp.set(x, y, light if y <= 3 else mid)
    for (x, y) in [(3, 6), (2, 7), (2, 8), (13, 8), (12, 8), (3, 7), (12, 7), (12, 6), (13, 7)]:
        sp.set(x, y, dark)
    for (x, y) in [(5, 4), (6, 4), (7, 4), (8, 4), (9, 4), (10, 5), (11, 5)]:
        sp.set(x, y, dark if x % 2 else mid)
    return sp.finish()


def _sprite_axe(pal) -> Image.Image:
    sp = Sprite()
    dark, mid, light = pal
    for i, (x, y) in enumerate(line_points(2, 14, 10, 6)):
        sp.set(x, y, HANDLE[1])
        sp.set(x, y + 1, HANDLE[0]) if i > 0 else None
    spec = {
        1: (8, 10), 2: (6, 12), 3: (5, 13), 4: (5, 13), 5: (6, 13), 6: (9, 13), 7: (10, 12), 8: (10, 11),
    }
    sp.rows(spec, pal)
    for (x, y) in [(6, 2), (7, 2), (8, 1), (9, 1), (5, 3), (5, 4)]:
        sp.set(x, y, light)
    for (x, y) in [(13, 3), (13, 4), (13, 5), (12, 6), (11, 7), (11, 8)]:
        sp.set(x, y, dark)
    return sp.finish()


def _sprite_sword(pal) -> Image.Image:
    sp = Sprite()
    dark, mid, light = pal
    # Blade: two-pixel-wide diagonal with highlight edge
    for (x, y) in line_points(5, 10, 13, 2):
        sp.set(x, y, light)
        sp.set(x + 1, y, mid)
        sp.set(x, y + 1, dark)
    sp.set(14, 1, light)
    sp.set(14, 2, mid)
    sp.set(13, 1, light)
    # Crossguard
    for (x, y) in line_points(3, 8, 7, 12):
        sp.set(x, y, HANDLE[2])
        sp.set(x + 1, y, HANDLE[1])
    sp.set(3, 8, HANDLE[1])
    sp.set(7, 12, HANDLE[0])
    # Grip
    for (x, y) in line_points(3, 12, 1, 14):
        sp.set(x, y, HANDLE[1])
        sp.set(x + 1, y, HANDLE[0])
    sp.set(1, 14, HANDLE[2])
    sp.set(0, 15, HANDLE[0])
    return sp.finish()


def _sprite_stick() -> Image.Image:
    sp = Sprite()
    for i, (x, y) in enumerate(line_points(3, 13, 12, 4)):
        sp.set(x, y, HANDLE[2] if i % 3 == 0 else HANDLE[1])
        sp.set(x + 1, y, HANDLE[0])
    return sp.finish()


def _sprite_ingot(pal) -> Image.Image:
    sp = Sprite()
    dark, mid, light = pal
    spec = {5: (5, 12), 6: (4, 12), 7: (3, 11), 8: (3, 10), 9: (2, 9), 10: (2, 8)}
    # top slab (lighter), front slab
    for y in range(5, 8):
        for x in range(4 + (7 - y), 13 + (7 - y) - 1):
            sp.set(x, y, light if y == 5 else mid)
    for y in range(8, 11):
        for x in range(3, 11):
            sp.set(x, y, mid if y == 8 else dark)
    for y in range(8, 11):
        sp.set(11, y - 1 if y > 8 else y, dark)
    for (x, y) in [(11, 7), (10, 7), (11, 8), (10, 8)]:
        sp.set(x, y, dark)
    sp.set(5, 5, light)
    sp.set(6, 5, (255, 255, 255))
    return sp.finish()


def _sprite_gem(pal) -> Image.Image:
    sp = Sprite()
    dark, mid, light = pal
    spec = {2: (6, 9), 3: (4, 11), 4: (3, 12), 5: (3, 12), 6: (4, 11), 7: (4, 11), 8: (5, 10), 9: (6, 9), 10: (7, 8)}
    sp.rows(spec, pal)
    for (x, y) in [(6, 3), (7, 3), (5, 4), (4, 5), (7, 5), (8, 5)]:
        sp.set(x, y, light)
    sp.set(6, 4, (255, 255, 255))
    for (x, y) in [(10, 5), (9, 7), (9, 8), (8, 9), (11, 4), (10, 6)]:
        sp.set(x, y, dark)
    for x in range(3, 13):
        sp.set(x, 5, mid) if sp.get(x, 5)[3] else None
    return sp.finish()


def _sprite_coal() -> Image.Image:
    sp = Sprite()
    pal = ((18, 18, 22), (42, 42, 48), (84, 84, 94))
    spec = {3: (6, 10), 4: (4, 11), 5: (3, 12), 6: (3, 12), 7: (2, 12), 8: (3, 12), 9: (3, 11), 10: (4, 10), 11: (6, 9)}
    sp.rows(spec, pal)
    for (x, y) in [(5, 5), (6, 5), (4, 6), (9, 4), (10, 6), (7, 8)]:
        sp.set(x, y, pal[2])
    return sp.finish()


def _sprite_bone() -> Image.Image:
    sp = Sprite()
    light, mid, dark = (250, 248, 238), (222, 218, 202), (170, 166, 152)
    for (x, y) in line_points(4, 11, 11, 4):
        sp.set(x, y, light)
        sp.set(x + 1, y, mid)
        sp.set(x, y + 1, dark)
    for (x, y) in [(2, 11), (3, 12), (3, 10), (4, 12), (2, 12), (3, 11), (4, 11)]:
        sp.set(x, y, light if (x + y) % 2 else mid)
    for (x, y) in [(11, 2), (12, 3), (12, 2), (13, 3), (13, 4), (12, 4), (11, 3)]:
        sp.set(x, y, light if (x + y) % 2 else mid)
    sp.set(3, 13, dark)
    sp.set(13, 5, dark)
    return sp.finish()


def _sprite_apple() -> Image.Image:
    sp = Sprite()
    pal = ((150, 20, 28), (214, 40, 44), (252, 110, 98))
    spec = {4: (4, 6), 5: (3, 12), 6: (3, 12), 7: (2, 13), 8: (2, 13), 9: (3, 12), 10: (3, 12), 11: (4, 11), 12: (5, 6)}
    sp.rows(spec, pal)
    sp.set(10, 4, pal[1]); sp.set(11, 4, pal[1]); sp.set(9, 5, pal[0])
    sp.set(7, 4, pal[0]); sp.set(8, 4, pal[0]); sp.set(9, 4, pal[1])
    sp.set(12, 12, pal[0]) if False else None
    sp.set(7, 12, pal[0]); sp.set(8, 12, pal[0]); sp.set(7, 11, pal[0]); sp.set(8, 11, pal[0])
    for (x, y) in [(4, 6), (4, 7), (5, 6)]:
        sp.set(x, y, pal[2])
    sp.set(5, 6, (255, 220, 210))
    # stem and leaf
    sp.set(8, 3, HANDLE[1]); sp.set(8, 2, HANDLE[0])
    for (x, y) in [(9, 2), (10, 2), (10, 1), (11, 1)]:
        sp.set(x, y, (72, 162, 56) if (x + y) % 2 else (50, 126, 40))
    return sp.finish()


def _sprite_meat(kind: str, cooked: bool) -> Image.Image:
    sp = Sprite()
    if kind == "pork":
        pal = ((196, 120, 120), (240, 156, 156), (255, 206, 200)) if not cooked else ((130, 70, 44), (186, 110, 68), (222, 156, 100))
        bone_c = (246, 240, 226)
        spec = {3: (6, 10), 4: (4, 11), 5: (3, 12), 6: (3, 12), 7: (3, 12), 8: (4, 12), 9: (5, 11), 10: (6, 10), 11: (7, 9)}
        sp.rows(spec, pal)
        fat = (255, 236, 226) if not cooked else (230, 190, 130)
        for (x, y) in [(4, 5), (5, 4), (6, 4), (4, 6)]:
            sp.set(x, y, fat)
        for (x, y) in [(9, 6), (10, 7), (8, 8)]:
            sp.set(x, y, shade(pal[0], 0.9))
        # bone nub
        sp.set(11, 11, bone_c); sp.set(12, 12, bone_c); sp.set(12, 11, (200, 194, 180)); sp.set(13, 12, bone_c)
        sp.set(13, 13, bone_c); sp.set(12, 13, bone_c)
    else:
        pal = ((140, 28, 36), (196, 52, 58), (236, 108, 110)) if not cooked else ((92, 48, 30), (140, 80, 48), (186, 124, 78))
        spec = {3: (5, 10), 4: (3, 12), 5: (2, 13), 6: (2, 13), 7: (2, 13), 8: (3, 13), 9: (3, 12), 10: (4, 11), 11: (6, 9)}
        sp.rows(spec, pal)
        marble = (252, 214, 206) if not cooked else (206, 150, 104)
        for (x, y) in [(5, 5), (6, 5), (7, 6), (8, 6), (6, 8), (7, 8), (10, 7), (11, 7)]:
            sp.set(x, y, marble)
        if cooked:
            for (x, y) in [(5, 7), (9, 5), (10, 9), (4, 8), (8, 9)]:
                sp.set(x, y, pal[0])
    return sp.finish()


def _sprite_flesh() -> Image.Image:
    sp = Sprite()
    pal = ((78, 54, 36), (130, 96, 62), (160, 150, 90))
    spec = {3: (5, 10), 4: (3, 12), 5: (3, 12), 6: (2, 13), 7: (3, 13), 8: (3, 12), 9: (4, 12), 10: (4, 10), 11: (5, 8)}
    sp.rows(spec, pal)
    for (x, y) in [(5, 5), (6, 6), (9, 4), (10, 7), (7, 9), (4, 7)]:
        sp.set(x, y, (98, 140, 62) if (x + y) % 2 else (70, 110, 48))
    for (x, y) in [(8, 5), (6, 8)]:
        sp.set(x, y, (180, 40, 40))
    return sp.finish()


def _sprite_for_item(item) -> Image.Image:
    key = item.key
    if key.endswith(("_pickaxe", "_axe", "_sword")):
        tier = key.split("_")[0]
        pal = TIER_PALETTES.get(tier, TIER_PALETTES["stone"])
        if key.endswith("_pickaxe"):
            return _sprite_pickaxe(pal)
        if key.endswith("_axe"):
            return _sprite_axe(pal)
        return _sprite_sword(pal)
    table: Dict[str, Callable[[], Image.Image]] = {
        "stick": _sprite_stick,
        "iron_ingot": lambda: _sprite_ingot(TIER_PALETTES["iron"]),
        "gold_ingot": lambda: _sprite_ingot(((176, 120, 14), (248, 200, 50), (255, 240, 150))),
        "diamond": lambda: _sprite_gem(TIER_PALETTES["diamond"]),
        "coal": _sprite_coal,
        "bone": _sprite_bone,
        "apple": _sprite_apple,
        "raw_pork": lambda: _sprite_meat("pork", False),
        "cooked_pork": lambda: _sprite_meat("pork", True),
        "raw_beef": lambda: _sprite_meat("beef", False),
        "cooked_beef": lambda: _sprite_meat("beef", True),
        "rotten_flesh": _sprite_flesh,
    }
    fn = table.get(key)
    if fn is not None:
        return fn()
    # Generic fallback gem tinted with the item colour
    c = item.icon_color
    return _sprite_gem((shade(c, 0.6), tuple(c), mix(c, (255, 255, 255), 0.6)))


def generate_icon(item, block_def=None, tile_fn: Callable[[str], Image.Image] = generate_tile) -> Image.Image:
    """Create a 32x32 inventory icon for any item."""
    if block_def is not None and item.category == "block":
        faces = block_def.faces
        top = tile_fn(faces.get("top", "stone"))
        side = tile_fn(faces.get("side", faces.get("top", "stone")))
        front = tile_fn(faces.get("north", faces.get("side", "stone")))
        if block_def.key == "torch":
            sp = Sprite()
            t = tile_fn("torch")
            sp.img.paste(t, (0, 0))
            return sp.finish()
        if block_def.key == "glass":
            return render_iso_block(top, side, side)
        return render_iso_block(top, front, side)
    return _sprite_for_item(item)


# ---------------------------------------------------------------------------
# Mob skins & box-model UV layout
# ---------------------------------------------------------------------------

def box_uv_size(w: int, h: int, d: int) -> Tuple[int, int]:
    return (2 * d + 2 * w, d + h)


def box_face_rects(u: int, v: int, w: int, h: int, d: int) -> Dict[str, Tuple[int, int, int, int]]:
    """Minecraft-style cross layout. Rects are (x, y, width, height) in texture pixels.

    'front' is the +Z face (the direction mobs walk toward).
    """
    return {
        "top": (u + d, v, w, d),
        "bottom": (u + d + w, v, w, d),
        "right": (u, v + d, d, h),          # -X face
        "front": (u + d, v + d, w, h),      # +Z face
        "left": (u + d + w, v + d, d, h),   # +X face
        "back": (u + 2 * d + w, v + d, w, h),  # -Z face
    }


class Skin:
    def __init__(self, width: int, height: int, name: str):
        self.w, self.h = width, height
        self.img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self.px = self.img.load()
        self.rng = _rng(name)

    def fill_rect(self, rect, palette: Sequence[RGB], noise: float = 0.5, smooth_rng=None) -> None:
        x0, y0, w, h = rect
        for y in range(h):
            for x in range(w):
                c = palette[int(self.rng.randint(0, len(palette)))]
                if self.rng.rand() > noise:
                    c = palette[len(palette) // 2]
                self.px[x0 + x, y0 + y] = _opaque(c)

    def paint_box(self, u, v, w, h, d, palette: Sequence[RGB], noise: float = 0.5,
                  top_shift: float = 1.08, bottom_shift: float = 0.78, side_shift: Optional[Dict[str, float]] = None) -> Dict[str, Tuple[int, int, int, int]]:
        rects = box_face_rects(u, v, w, h, d)
        shifts = {"top": top_shift, "bottom": bottom_shift, "front": 1.0, "back": 0.9, "left": 0.92, "right": 0.92}
        if side_shift:
            shifts.update(side_shift)
        for face, rect in rects.items():
            pal = [shade(c, shifts[face]) for c in palette]
            self.fill_rect(rect, pal, noise)
        return rects

    def put(self, rect, dx: int, dy: int, c: Sequence[int]) -> None:
        x0, y0, w, h = rect
        if 0 <= dx < w and 0 <= dy < h:
            self.px[x0 + dx, y0 + dy] = _opaque(c)

    def put_rect(self, rect, dx: int, dy: int, w: int, h: int, c: Sequence[int]) -> None:
        for yy in range(h):
            for xx in range(w):
                self.put(rect, dx + xx, dy + yy, c)

    def done(self) -> Image.Image:
        return self.img


# Mob model specs: parts with (size, uv origin).  Geometry lives in game/mob_models.py;
# the UV origins here must stay in sync with it, so both import MOB_PARTS from this file.
# size = (w, h, d) in skin pixels
MOB_SKIN_SIZES: Dict[str, Tuple[int, int]] = {
    "pig": (64, 64),
    "cow": (64, 64),
    "zombie": (64, 32),
    "skeleton": (64, 32),
}

MOB_PARTS: Dict[str, Dict[str, Dict[str, Tuple[int, ...]]]] = {
    "zombie": {
        "head": {"size": (8, 8, 8), "uv": (0, 0)},
        "body": {"size": (8, 12, 4), "uv": (16, 16)},
        "arm": {"size": (4, 12, 4), "uv": (40, 16)},
        "leg": {"size": (4, 12, 4), "uv": (0, 16)},
    },
    "skeleton": {
        "head": {"size": (8, 8, 8), "uv": (0, 0)},
        "body": {"size": (8, 12, 4), "uv": (16, 16)},
        "arm": {"size": (2, 12, 2), "uv": (40, 16)},
        "leg": {"size": (2, 12, 2), "uv": (0, 16)},
    },
    "pig": {
        "head": {"size": (8, 8, 8), "uv": (0, 0)},
        "snout": {"size": (4, 3, 1), "uv": (32, 0)},
        "body": {"size": (10, 8, 16), "uv": (0, 16)},
        "leg": {"size": (4, 6, 4), "uv": (0, 40)},
    },
    "cow": {
        "head": {"size": (8, 8, 6), "uv": (0, 0)},
        "horn": {"size": (1, 3, 1), "uv": (28, 0)},
        "snout": {"size": (4, 3, 1), "uv": (36, 0)},
        "body": {"size": (12, 10, 18), "uv": (0, 16)},
        "leg": {"size": (4, 12, 4), "uv": (0, 44)},
        "udder": {"size": (4, 2, 4), "uv": (16, 44)},
    },
}


def _zombie_skin() -> Image.Image:
    sk = Skin(64, 32, "zombie")
    skin_pal = [(74, 128, 58), (84, 142, 66), (96, 156, 76), (64, 114, 52)]
    shirt_pal = [(34, 150, 170), (40, 164, 184), (30, 136, 156)]
    pants_pal = [(56, 50, 130), (64, 58, 144), (50, 44, 118)]
    P = MOB_PARTS["zombie"]
    # head
    hr = sk.paint_box(*P["head"]["uv"], *P["head"]["size"], skin_pal, 0.7)
    f = hr["front"]
    sk.put_rect(f, 0, 0, 8, 2, shade(skin_pal[3], 0.8))          # hair/brow shadow
    sk.put_rect(f, 1, 3, 2, 2, (250, 250, 250))                   # eye whites
    sk.put_rect(f, 5, 3, 2, 2, (250, 250, 250))
    sk.put_rect(f, 2, 3, 1, 2, (24, 24, 40))                      # pupils
    sk.put_rect(f, 5, 3, 1, 2, (24, 24, 40))
    sk.put_rect(f, 1, 2, 2, 1, (44, 84, 38))                      # angry brows
    sk.put_rect(f, 5, 2, 2, 1, (44, 84, 38))
    sk.put_rect(f, 3, 5, 2, 1, shade(skin_pal[3], 0.78))          # nose
    sk.put_rect(f, 2, 6, 4, 1, (52, 40, 40))                      # mouth
    sk.put(f, 3, 6, (190, 190, 170)); sk.put(f, 5, 6, (190, 190, 170))
    sk.put_rect(hr["top"], 0, 0, 8, 8, shade(skin_pal[3], 0.85))
    # body shirt
    br = sk.paint_box(*P["body"]["uv"], *P["body"]["size"], shirt_pal, 0.5)
    sk.put_rect(br["front"], 0, 0, 8, 1, shade(shirt_pal[1], 0.8))
    for (x, y) in [(2, 5), (5, 8), (3, 9), (6, 3)]:
        sk.put(br["front"], x, y, shade(shirt_pal[0], 0.7))     # tears/stains
    sk.put_rect(br["front"], 1, 8, 2, 1, (74, 128, 58))
    # arms: skin colour with sleeve
    ar = sk.paint_box(*P["arm"]["uv"], *P["arm"]["size"], skin_pal, 0.6)
    for face in ("front", "back", "left", "right"):
        sk.put_rect(ar[face], 0, 0, ar[face][2], 4, shirt_pal[1])
        sk.put_rect(ar[face], 0, 3, ar[face][2], 1, shade(shirt_pal[1], 0.8))
    # legs
    lr = sk.paint_box(*P["leg"]["uv"], *P["leg"]["size"], pants_pal, 0.5)
    for face in ("front", "back", "left", "right"):
        sk.put_rect(lr[face], 0, 10, lr[face][2], 2, (58, 56, 62))   # shoes
    return sk.done()


def _skeleton_skin() -> Image.Image:
    sk = Skin(64, 32, "skeleton")
    bone_pal = [(206, 206, 198), (220, 220, 212), (234, 234, 226), (190, 190, 182)]
    P = MOB_PARTS["skeleton"]
    hr = sk.paint_box(*P["head"]["uv"], *P["head"]["size"], bone_pal, 0.45)
    f = hr["front"]
    sk.put_rect(f, 1, 3, 2, 2, (30, 30, 34))
    sk.put_rect(f, 5, 3, 2, 2, (30, 30, 34))
    sk.put(f, 1, 3, (150, 20, 20)); sk.put(f, 5, 3, (150, 20, 20))   # glowing red hint
    sk.put_rect(f, 3, 5, 2, 1, (120, 120, 114))
    sk.put_rect(f, 1, 6, 6, 2, (60, 60, 60))
    for x in (1, 3, 5):
        sk.put_rect(f, x, 6, 1, 2, (226, 226, 218))
    br = sk.paint_box(*P["body"]["uv"], *P["body"]["size"], bone_pal, 0.4)
    fr = br["front"]
    sk.put_rect(fr, 0, 0, 8, 12, (46, 46, 50))                      # dark void between ribs
    sk.put_rect(fr, 3, 0, 2, 12, (214, 214, 206))                    # spine
    for y in (1, 4, 7):
        sk.put_rect(fr, 0, y, 8, 1, (222, 222, 214))
        sk.put_rect(fr, 0, y + 1, 8, 1, (182, 182, 174))
    sk.put_rect(fr, 0, 10, 8, 2, (200, 200, 192))
    bk = br["back"]
    sk.put_rect(bk, 0, 0, 8, 12, (46, 46, 50))
    sk.put_rect(bk, 3, 0, 2, 12, (214, 214, 206))
    for y in (1, 4, 7):
        sk.put_rect(bk, 0, y, 8, 1, (210, 210, 202))
    sk.paint_box(*P["arm"]["uv"], *P["arm"]["size"], bone_pal, 0.4)
    sk.paint_box(*P["leg"]["uv"], *P["leg"]["size"], bone_pal, 0.4)
    return sk.done()


def _pig_skin() -> Image.Image:
    sk = Skin(64, 64, "pig")
    pink = [(236, 150, 150), (244, 164, 164), (250, 178, 176), (226, 138, 140)]
    P = MOB_PARTS["pig"]
    hr = sk.paint_box(*P["head"]["uv"], *P["head"]["size"], pink, 0.35)
    f = hr["front"]
    sk.put_rect(f, 1, 3, 2, 2, (255, 255, 255))
    sk.put_rect(f, 5, 3, 2, 2, (255, 255, 255))
    sk.put_rect(f, 2, 3, 1, 2, (28, 22, 40))
    sk.put_rect(f, 5, 3, 1, 2, (28, 22, 40))
    sk.put_rect(f, 1, 2, 2, 1, shade(pink[3], 0.85))
    sk.put_rect(f, 5, 2, 2, 1, shade(pink[3], 0.85))
    sn = sk.paint_box(*P["snout"]["uv"], *P["snout"]["size"], [(246, 136, 148), (252, 148, 160), (240, 124, 138)], 0.3)
    sk.put_rect(sn["front"], 1, 1, 1, 1, (150, 60, 78))
    sk.put_rect(sn["front"], 2, 1, 1, 1, (150, 60, 78))
    sk.put_rect(sn["front"], 0, 0, 4, 1, (252, 160, 170))
    br = sk.paint_box(*P["body"]["uv"], *P["body"]["size"], pink, 0.3)
    for (x, y) in [(2, 3), (7, 5), (4, 6)]:
        sk.put(br["right"], x, y, (222, 130, 134))
    sk.put_rect(br["back"], 4, 6, 2, 2, (214, 118, 126))              # curly tail nub
    lr = sk.paint_box(*P["leg"]["uv"], *P["leg"]["size"], pink, 0.3)
    for face in ("front", "back", "left", "right"):
        sk.put_rect(lr[face], 0, 5, lr[face][2], 1, (96, 70, 70))     # hooves
    return sk.done()


def _cow_skin() -> Image.Image:
    sk = Skin(64, 64, "cow")
    brown = [(86, 54, 34), (98, 62, 40), (110, 72, 46), (76, 46, 28)]
    white = [(232, 228, 220), (242, 238, 230), (222, 218, 210)]
    P = MOB_PARTS["cow"]
    hr = sk.paint_box(*P["head"]["uv"], *P["head"]["size"], brown, 0.4)
    f = hr["front"]
    sk.put_rect(f, 3, 0, 2, 8, white[1])                              # blaze
    sk.put_rect(f, 1, 3, 2, 2, (255, 255, 255))
    sk.put_rect(f, 5, 3, 2, 2, (255, 255, 255))
    sk.put_rect(f, 1, 3, 1, 2, (24, 20, 28))
    sk.put_rect(f, 6, 3, 1, 2, (24, 20, 28))
    sn = sk.paint_box(*P["snout"]["uv"], *P["snout"]["size"], [(212, 170, 150), (222, 182, 162), (200, 158, 138)], 0.3)
    sk.put(sn["front"], 1, 1, (120, 70, 60)); sk.put(sn["front"], 2, 1, (120, 70, 60))
    sk.paint_box(*P["horn"]["uv"], *P["horn"]["size"], [(226, 222, 200), (240, 236, 214)], 0.3)
    br = sk.paint_box(*P["body"]["uv"], *P["body"]["size"], brown, 0.45)
    # white patches on every side
    patches = {
        "left": [(2, 1, 6, 5), (11, 6, 5, 3)],
        "right": [(1, 5, 5, 4), (9, 1, 7, 4)],
        "top": [(2, 3, 5, 6), (8, 10, 4, 5)],
        "back": [(2, 2, 5, 5)],
        "front": [(5, 3, 5, 5)],
    }
    for face, plist in patches.items():
        for (px_, py_, pw, ph) in plist:
            for yy in range(ph):
                for xx in range(pw):
                    if (xx in (0, pw - 1) and yy in (0, ph - 1)):
                        continue
                    c = white[int(sk.rng.randint(0, 3))]
                    sk.put(br[face], px_ + xx, py_ + yy, c)
    lr = sk.paint_box(*P["leg"]["uv"], *P["leg"]["size"], brown, 0.4)
    for face in ("front", "back", "left", "right"):
        sk.put_rect(lr[face], 0, 10, lr[face][2], 2, (170, 160, 150))    # hooves
    sk.paint_box(*P["udder"]["uv"], *P["udder"]["size"], [(236, 170, 170), (246, 184, 182), (226, 158, 160)], 0.3)
    return sk.done()


def generate_mob_skin(mob_type: str) -> Image.Image:
    return {
        "zombie": _zombie_skin,
        "skeleton": _skeleton_skin,
        "pig": _pig_skin,
        "cow": _cow_skin,
    }[mob_type]()


# ---------------------------------------------------------------------------
# Main menu art
# ---------------------------------------------------------------------------

def generate_panorama(width: int = 1024, height: int = 576) -> Image.Image:
    """Sunset voxel landscape used as the main-menu backdrop (no external assets)."""
    rng = _rng("panorama")
    img = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(img)

    # Sky gradient: deep blue -> teal -> warm horizon
    stops = [(0.0, (46, 84, 170)), (0.25, (84, 138, 214)), (0.45, (150, 186, 236)), (0.58, (252, 196, 150)), (0.7, (255, 214, 158)), (1.0, (255, 214, 158))]
    for y in range(height):
        t = y / (height - 1)
        for i in range(len(stops) - 1):
            if stops[i][0] <= t <= stops[i + 1][0]:
                k = (t - stops[i][0]) / (stops[i + 1][0] - stops[i][0])
                c = mix(stops[i][1], stops[i + 1][1], k)
                break
        d.line([(0, y), (width, y)], fill=c)

    px = 8  # voxel size for chunky look
    # Stars

    # Sun (blocky)
    sx, sy = int(width * 0.74), int(height * 0.46)
    for r, col in ((64, (255, 222, 150)), (48, (255, 232, 170)), (32, (255, 244, 200))):
        d.rectangle([sx - r, sy - r, sx + r, sy + r], fill=col)

    # Blocky clouds
    for cx, cy, cw in ((60, 250, 6), (360, 310, 5), (860, 330, 4), (620, 270, 3)):
        for i in range(cw):
            for j in range(2 if i % 3 else 1):
                x0 = cx + i * 16
                y0 = cy + j * 12 - (i % 2) * 4
                d.rectangle([x0, y0, x0 + 15, y0 + 11], fill=(255, 236, 226))
                d.rectangle([x0, y0 + 8, x0 + 15, y0 + 11], fill=(236, 202, 200))

    def layer(base_y: float, amp: float, color_top: RGB, color_body: RGB, seed: int, step: int = px, tint_dirt: bool = False):
        r = _rng("layer", seed)
        cols = width // step + 2
        heights = []
        h = base_y
        for i in range(cols):
            h += r.choice([-1, 0, 0, 1]) * step * 0.5 + math.sin(i * 0.22 + seed) * amp * 0.12
            h = max(base_y - amp, min(base_y + amp, h))
            heights.append(int(h // step) * step)
        for i, hh in enumerate(heights):
            x0 = i * step
            d.rectangle([x0, hh, x0 + step - 1, height], fill=color_body)
            d.rectangle([x0, hh, x0 + step - 1, hh + step - 1], fill=color_top)
            for yy in range(hh + step, height, step):
                if r.rand() < 0.12:
                    d.rectangle([x0, yy, x0 + step - 1, yy + step - 1], fill=shade(color_body, 0.9 + r.rand() * 0.2))
        return heights

    layer(height * 0.62, 70, (120, 100, 150), (96, 82, 134), 1, 12)
    layer(height * 0.70, 55, (88, 120, 96), (70, 98, 84), 2, 10)
    heights = layer(height * 0.80, 40, (66, 140, 58), (116, 82, 54), 3, 16)

    # Trees on the mid ridge
    r = _rng("trees")
    for i in range(5, len(heights) - 3, 7):
        hx = i * 16
        hy = heights[i]
        trunk_h = 16 * int(r.randint(2, 4))
        d.rectangle([hx + 4, hy - trunk_h, hx + 11, hy], fill=(84, 58, 34))
        d.rectangle([hx + 4, hy - trunk_h, hx + 6, hy], fill=(100, 72, 42))
        for lx in range(-1, 2):
            for ly in range(0, 2):
                d.rectangle([hx + lx * 16, hy - trunk_h - 16 - ly * 16, hx + lx * 16 + 15, hy - trunk_h - ly * 16 - 1], fill=(40, 110, 44) if (lx + ly) % 2 else (52, 128, 52))
        d.rectangle([hx, hy - trunk_h - 48, hx + 15, hy - trunk_h - 33], fill=(60, 140, 58))

    # Foreground
    layer(height * 0.92, 20, (50, 120, 46), (92, 64, 42), 4, 24)

    # Vignette
    arr = np.asarray(img).astype(np.float32)
    ys, xs = np.mgrid[0:height, 0:width]
    dist = np.sqrt(((xs - width / 2) / (width / 2)) ** 2 + ((ys - height / 2) / (height / 2)) ** 2)
    arr *= (1.0 - 0.38 * np.clip(dist - 0.35, 0, 1.2))[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# 5x7 pixel font for the logo (only the glyphs we need)
_FONT: Dict[str, List[str]] = {
    "P": ["XXXX.", "X...X", "X...X", "XXXX.", "X....", "X....", "X...."],
    "Y": ["X...X", "X...X", ".X.X.", "..X..", "..X..", "..X..", "..X.."],
    "C": [".XXXX", "X....", "X....", "X....", "X....", "X....", ".XXXX"],
    "R": ["XXXX.", "X...X", "X...X", "XXXX.", "X.X..", "X..X.", "X...X"],
    "A": [".XXX.", "X...X", "X...X", "XXXXX", "X...X", "X...X", "X...X"],
    "F": ["XXXXX", "X....", "X....", "XXXX.", "X....", "X....", "X...."],
    "T": ["XXXXX", "..X..", "..X..", "..X..", "..X..", "..X..", "..X.."],
}


def generate_logo(text: str = "PYCRAFT", cell: int = 8) -> Image.Image:
    """Chunky stone-block logo (each font pixel = 2x2 blocks) with bevel, drop shadow and moss."""
    scale = 2
    gap = 1
    glyph_w, glyph_h = 5 * scale, 7 * scale
    total_w = len(text) * (glyph_w + gap * scale) - gap * scale
    pad = 3
    W = (total_w + pad * 2) * cell
    H = (glyph_h + pad * 2) * cell
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    rng = _rng("logo")
    stone = [(150, 150, 156), (164, 164, 170), (140, 140, 146), (174, 174, 180)]
    d = ImageDraw.Draw(img)
    x_cursor = pad
    for ch in text:
        glyph = _FONT.get(ch)
        if glyph is None:
            x_cursor += glyph_w + gap * scale
            continue
        # expand glyph to block grid
        grid = [[glyph[gy // scale][gx // scale] == "X" for gx in range(glyph_w)] for gy in range(glyph_h)]
        for gy in range(glyph_h):
            for gx in range(glyph_w):
                if not grid[gy][gx]:
                    continue
                x0 = (x_cursor + gx) * cell
                y0 = (pad + gy) * cell
                exposed_top = gy == 0 or not grid[gy - 1][gx]
                base = stone[int(rng.randint(0, len(stone)))]
                sd.rectangle([x0 + 4, y0 + 5, x0 + 4 + cell - 1, y0 + 5 + cell - 1], fill=(0, 0, 0, 140))
                d.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=_opaque(shade(base, 0.60)))
                d.rectangle([x0 + 1, y0 + 1, x0 + cell - 2, y0 + cell - 2], fill=_opaque(base))
                d.line([(x0 + 1, y0 + 1), (x0 + cell - 2, y0 + 1)], fill=_opaque(shade(base, 1.22)))
                d.line([(x0 + 1, y0 + 1), (x0 + 1, y0 + cell - 2)], fill=_opaque(shade(base, 1.12)))
                d.line([(x0 + cell - 2, y0 + 2), (x0 + cell - 2, y0 + cell - 2)], fill=_opaque(shade(base, 0.80)))
                d.line([(x0 + 2, y0 + cell - 2), (x0 + cell - 2, y0 + cell - 2)], fill=_opaque(shade(base, 0.76)))
                for _ in range(2):
                    rx, ry = int(rng.randint(2, cell - 3)), int(rng.randint(3, cell - 3))
                    d.point((x0 + rx, y0 + ry), fill=_opaque(shade(base, 0.80 + rng.rand() * 0.3)))
                if exposed_top:
                    d.rectangle([x0 + 1, y0 + 1, x0 + cell - 2, y0 + 3], fill=(84, 156, 58, 255))
                    d.line([(x0 + 1, y0 + 1), (x0 + cell - 2, y0 + 1)], fill=(124, 202, 88, 255))
                    for dx in range(1, cell - 2, 2):
                        if rng.rand() < 0.55:
                            d.point((x0 + dx, y0 + 4), fill=(68, 130, 46, 255))
        x_cursor += glyph_w + gap * scale
    return Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(1.5)), img)


def generate_button(width: int = 200, height: int = 20, state: str = "normal") -> Image.Image:
    """Minecraft-ish bevelled stone button texture (200x20 logical px, upscaled x2)."""
    rng = _rng("button", {"normal": 0, "hover": 1, "pressed": 2, "disabled": 3}[state])
    base = {
        "normal": (176, 176, 182),
        "hover": (168, 188, 240),
        "pressed": (120, 136, 190),
        "disabled": (96, 96, 100),
    }[state]
    img = Image.new("RGBA", (width, height))
    px = img.load()
    for y in range(height):
        for x in range(width):
            n = int(rng.randint(-5, 6))
            c = (base[0] + n, base[1] + n, base[2] + n)
            px[x, y] = _opaque(c)
    d = ImageDraw.Draw(img)
    hi = shade(base, 1.35)
    lo = shade(base, 0.55)
    d.rectangle([0, 0, width - 1, height - 1], outline=(18, 18, 22, 255))
    d.line([(1, 1), (width - 2, 1)], fill=_opaque(hi))
    d.line([(1, 1), (1, height - 2)], fill=_opaque(hi))
    d.line([(1, height - 2), (width - 2, height - 2)], fill=_opaque(lo))
    d.line([(width - 2, 1), (width - 2, height - 2)], fill=_opaque(lo))
    d.line([(2, height - 3), (width - 3, height - 3)], fill=_opaque(shade(base, 0.75)))
    return img
