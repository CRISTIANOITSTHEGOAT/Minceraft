"""
Procedural terrain generator using deterministic seeded multi-octave 2D & 3D noise.
Generates Plains, Hills, Mountains, Valleys, Beaches, Rivers, Lakes, Caves, Trees, and Ores.
"""

import hashlib
from typing import Tuple

import numpy as np

from game.blocks import (
    AIR,
    BEDROCK,
    COAL_ORE,
    DIAMOND_ORE,
    DIRT,
    GOLD_ORE,
    GRASS,
    GRAVEL,
    IRON_ORE,
    LEAVES,
    SAND,
    STONE,
    WATER,
    WOOD,
)

CHUNK_SIZE = 16
CHUNK_HEIGHT = 64
SEA_LEVEL = 14


def normalize_seed(seed_input) -> Tuple[str, int]:
    """
    Convert any user-supplied seed (string, int, None, invalid) into a clean
    display string and a deterministic 32-bit integer seed.
    """
    if seed_input is None:
        seed_str = "PyCraft2026"
    else:
        seed_str = str(seed_input).strip()
        if not seed_str:
            seed_str = "PyCraft2026"

    # If purely numeric, keep exact numeric representation
    try:
        val = int(seed_str)
        seed_int = abs(val) % (2**31 - 1)
        if seed_int == 0:
            seed_int = 1337
        return seed_str, seed_int
    except ValueError:
        digest = hashlib.sha256(seed_str.encode("utf-8", errors="replace")).hexdigest()
        seed_int = int(digest[:8], 16) % (2**31 - 1)
        if seed_int == 0:
            seed_int = 1337
        return seed_str, seed_int


class TerrainGenerator:
    """Deterministic procedural voxel terrain generator."""

    def __init__(self, seed="PyCraft2026"):
        self.seed_str, self.seed_int = normalize_seed(seed)
        rng = np.random.RandomState(self.seed_int)
        p = np.arange(256, dtype=np.int32)
        rng.shuffle(p)
        self.perm = np.concatenate([p, p])

    @staticmethod
    def _fade(t: np.ndarray) -> np.ndarray:
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

    def noise2d(self, x: np.ndarray, z: np.ndarray) -> np.ndarray:
        """Vectorized 2D smooth value noise in [-1.0, 1.0]."""
        xi = np.floor(x).astype(np.int32) & 255
        zi = np.floor(z).astype(np.int32) & 255
        xf = x - np.floor(x)
        zf = z - np.floor(z)

        u = self._fade(xf)
        v = self._fade(zf)

        p = self.perm
        aa = p[p[xi] + zi]
        ab = p[p[xi] + zi + 1]
        ba = p[p[xi + 1] + zi]
        bb = p[p[xi + 1] + zi + 1]

        # Normalize 0..255 to -1..1
        va = (aa / 127.5) - 1.0
        vb = (ba / 127.5) - 1.0
        vc = (ab / 127.5) - 1.0
        vd = (bb / 127.5) - 1.0

        x1 = va + u * (vb - va)
        x2 = vc + u * (vd - vc)
        return x1 + v * (x2 - x1)

    def fbm2d(self, x: np.ndarray, z: np.ndarray, octaves: int = 4, persistence: float = 0.5, lacunarity: float = 2.0) -> np.ndarray:
        """Multi-octave 2D Fractal Brownian Motion noise in [-1.0, 1.0]."""
        out_shape = np.broadcast_shapes(np.shape(x), np.shape(z))
        total = np.zeros(out_shape, dtype=np.float32)
        amplitude = 1.0
        frequency = 1.0
        max_amp = 0.0
        for i in range(octaves):
            total += self.noise2d(x * frequency + i * 17.3, z * frequency + i * 31.7) * amplitude
            max_amp += amplitude
            amplitude *= persistence
            frequency *= lacunarity
        return total / max_amp

    def noise3d(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
        """Vectorized 3D smooth value noise in [-1.0, 1.0] for caves and ore veins."""
        xi = np.floor(x).astype(np.int32) & 255
        yi = np.floor(y).astype(np.int32) & 255
        zi = np.floor(z).astype(np.int32) & 255

        xf = x - np.floor(x)
        yf = y - np.floor(y)
        zf = z - np.floor(z)

        u = self._fade(xf)
        v = self._fade(yf)
        w = self._fade(zf)

        p = self.perm
        A = p[xi] + yi
        AA = p[A] + zi
        AB = p[A + 1] + zi
        B = p[xi + 1] + yi
        BA = p[B] + zi
        BB = p[B + 1] + zi

        c000 = (p[AA] / 127.5) - 1.0
        c100 = (p[BA] / 127.5) - 1.0
        c010 = (p[AB] / 127.5) - 1.0
        c110 = (p[BB] / 127.5) - 1.0
        c001 = (p[AA + 1] / 127.5) - 1.0
        c101 = (p[BA + 1] / 127.5) - 1.0
        c011 = (p[AB + 1] / 127.5) - 1.0
        c111 = (p[BB + 1] / 127.5) - 1.0

        x00 = c000 + u * (c100 - c000)
        x10 = c010 + u * (c110 - c010)
        x01 = c001 + u * (c101 - c001)
        x11 = c011 + u * (c111 - c011)

        y0 = x00 + v * (x10 - x00)
        y1 = x01 + v * (x11 - x01)
        return y0 + w * (y1 - y0)

    def get_biome_and_height(self, wx: int, wz: int) -> Tuple[str, int]:
        """Return (biome_name, surface_y) at world column (wx, wz)."""
        xa = np.array([[float(wx)]], dtype=np.float32)
        za = np.array([[float(wz)]], dtype=np.float32)
        h_map, b_map = self._compute_height_and_biome_grid(xa, za)
        b_code = int(b_map[0, 0])
        names = {
            0: "Lake",
            1: "River",
            2: "Beach",
            3: "Valley",
            4: "Plains",
            5: "Hills",
            6: "Mountains",
        }
        return names.get(b_code, "Plains"), int(h_map[0, 0])

    def _compute_height_and_biome_grid(self, wx: np.ndarray, wz: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute heightmap and biome codes for a 2D grid of world coordinates (wx, wz).
        Biome codes:
          0 = Lake, 1 = River, 2 = Beach, 3 = Valley, 4 = Plains, 5 = Hills, 6 = Mountains
        """
        # Continental / elevation macro-noise
        macro = self.fbm2d(wx * 0.009, wz * 0.009, octaves=3)
        # Detail terrain noise
        detail = self.fbm2d(wx * 0.032, wz * 0.032, octaves=4)
        # Mountain ridge noise
        mountain_raw = self.fbm2d(wx * 0.015 + 100.0, wz * 0.015 + 100.0, octaves=3)
        mountain_factor = np.clip((mountain_raw - 0.18) * 2.4, 0.0, 1.0)
        # River channel ridged noise (close to 0 creates winding river valleys)
        river_val = np.abs(self.fbm2d(wx * 0.014 - 55.0, wz * 0.014 + 77.0, octaves=2))

        # Base height around plains (18..22)
        height_f = 19.0 + macro * 7.0 + detail * 4.5 + (mountain_factor ** 1.6) * 22.0

        # Carve winding rivers where river_val is small and not on high mountain peaks
        river_mask = (river_val < 0.055) & (mountain_factor < 0.45)
        river_bank_mask = (river_val < 0.095) & (mountain_factor < 0.45)
        river_depth = np.clip((0.095 - river_val) / 0.095, 0.0, 1.0)
        height_f = np.where(river_bank_mask, height_f * (1.0 - river_depth) + (SEA_LEVEL - 2.5) * river_depth, height_f)

        heights = np.clip(np.round(height_f), 4, CHUNK_HEIGHT - 10).astype(np.int32)

        # Assign biome codes
        biomes = np.full(heights.shape, 4, dtype=np.int32)  # Default: Plains (4)
        biomes = np.where(heights <= SEA_LEVEL - 1, 0, biomes)  # Lake (0)
        biomes = np.where(river_mask & (heights <= SEA_LEVEL), 1, biomes)  # River (1)
        biomes = np.where((heights >= SEA_LEVEL) & (heights <= SEA_LEVEL + 1) & (biomes >= 3), 2, biomes)  # Beach (2)
        biomes = np.where((heights > SEA_LEVEL + 1) & (heights <= 17), 3, biomes)  # Valley (3)
        biomes = np.where((heights >= 24) & (heights < 31), 5, biomes)  # Hills (5)
        biomes = np.where(heights >= 31, 6, biomes)  # Mountains (6)

        return heights, biomes

    def generate_chunk_blocks(self, cx: int, cz: int) -> np.ndarray:
        """
        Generate the 3D uint8 voxel block array of shape (CHUNK_SIZE, CHUNK_HEIGHT, CHUNK_SIZE)
        for chunk coordinates (cx, cz).
        """
        blocks = np.zeros((CHUNK_SIZE, CHUNK_HEIGHT, CHUNK_SIZE), dtype=np.uint8)

        # World X and Z coordinate grids of shape (16, 16)
        lx = np.arange(CHUNK_SIZE, dtype=np.float32)[:, None]
        lz = np.arange(CHUNK_SIZE, dtype=np.float32)[None, :]
        wx = cx * CHUNK_SIZE + lx
        wz = cz * CHUNK_SIZE + lz

        heights, biomes = self._compute_height_and_biome_grid(wx, wz)

        # Y grid (1, 64, 1)
        y_grid = np.arange(CHUNK_HEIGHT, dtype=np.int32)[None, :, None]
        h_3d = heights[:, None, :]
        b_3d = biomes[:, None, :]

        # 1. Base stone fill up to surface height
        blocks[y_grid <= h_3d] = STONE

        # 2. Sub-surface layers (Dirt, Sand, Gravel, Mountain Stone)
        is_beach_or_water = (b_3d <= 2)
        is_river = (b_3d == 1)
        is_mountain = (b_3d == 6)

        # Top 3 layers below surface
        sub_mask = (y_grid < h_3d) & (y_grid >= h_3d - 3)
        blocks[sub_mask & (~is_beach_or_water) & (~is_mountain)] = DIRT
        blocks[sub_mask & is_beach_or_water & (~is_river)] = SAND
        blocks[sub_mask & is_river] = GRAVEL

        # Surface block at y == h_3d
        surf_mask = (y_grid == h_3d)
        blocks[surf_mask & (~is_beach_or_water) & (~is_mountain)] = GRASS
        blocks[surf_mask & is_beach_or_water & (~is_river)] = SAND
        blocks[surf_mask & is_river] = GRAVEL
        # High mountains have exposed stone, lower mountain slopes have grass/stone mix
        blocks[surf_mask & is_mountain & (h_3d < 36)] = GRASS
        blocks[surf_mask & is_mountain & (h_3d >= 36)] = STONE

        # 3. Carve Underground Caves using 3D noise (between y=2 and h - 3)
        wx_3d = wx[:, None, :]
        wz_3d = wz[:, None, :]
        wy_3d = y_grid.astype(np.float32)

        cave_n1 = self.noise3d(wx_3d * 0.065, wy_3d * 0.085, wz_3d * 0.065)
        cave_n2 = self.noise3d(wx_3d * 0.065 + 43.0, wy_3d * 0.085 + 19.0, wz_3d * 0.065 - 29.0)
        # Cave tunnel where both noise fields are high or combined intensity > threshold
        cave_mask = (
            (y_grid >= 2)
            & (y_grid < h_3d - 2)
            & (y_grid > SEA_LEVEL - 8)
            & ((cave_n1 * cave_n1 + cave_n2 * cave_n2) > 0.54)
        )
        blocks[cave_mask] = AIR

        #Also allow occasional cave entrances on hillsides above sea level
        entrance_mask = (
            (y_grid >= SEA_LEVEL + 2)
            & (y_grid <= h_3d)
            & (b_3d >= 5)
            & (cave_n1 > 0.62)
            & (cave_n2 > 0.35)
        )
        blocks[entrance_mask] = AIR

        # 4. Fill Water in Lakes and Rivers up to SEA_LEVEL
        water_mask = (y_grid > h_3d) & (y_grid <= SEA_LEVEL)
        blocks[water_mask] = WATER

        # 5. Generate Underground Ores inside remaining STONE blocks
        # Rarer ores generate deeper underground (Section 12)
        stone_mask = (blocks == STONE)

        # Gravel pockets underground
        gravel_n = self.noise3d(wx_3d * 0.14 + 7.0, wy_3d * 0.14, wz_3d * 0.14 + 11.0)
        blocks[stone_mask & (y_grid >= 4) & (y_grid <= 40) & (gravel_n > 0.66)] = GRAVEL

        # Coal Ore: y = 3..42 (most common)
        coal_n = self.noise3d(wx_3d * 0.22 + 101.0, wy_3d * 0.22 + 13.0, wz_3d * 0.22 + 202.0)
        blocks[(blocks == STONE) & (y_grid >= 3) & (y_grid <= 42) & (coal_n > 0.56)] = COAL_ORE

        # Iron Ore: y = 2..30 (medium depth)
        iron_n = self.noise3d(wx_3d * 0.24 + 303.0, wy_3d * 0.24 + 55.0, wz_3d * 0.24 + 404.0)
        blocks[(blocks == STONE) & (y_grid >= 2) & (y_grid <= 30) & (iron_n > 0.61)] = IRON_ORE

        # Gold Ore: y = 2..18 (rare, deeper underground)
        gold_n = self.noise3d(wx_3d * 0.27 + 505.0, wy_3d * 0.27 + 77.0, wz_3d * 0.27 + 606.0)
        blocks[(blocks == STONE) & (y_grid >= 2) & (y_grid <= 18) & (gold_n > 0.66)] = GOLD_ORE

        # Diamond Ore: y = 1..11 (very rare, deepest underground)
        diamond_n = self.noise3d(wx_3d * 0.30 + 707.0, wy_3d * 0.30 + 99.0, wz_3d * 0.30 + 808.0)
        blocks[(blocks == STONE) & (y_grid >= 1) & (y_grid <= 11) & (diamond_n > 0.70)] = DIAMOND_ORE

        # 6. Indestructible Bedrock layer at y = 0
        blocks[:, 0, :] = BEDROCK

        # 7. Procedural Trees on Grass in Plains, Hills, and Valleys
        # Keep 2-block margin from chunk edges so canopies stay cleanly inside the chunk
        for x in range(2, CHUNK_SIZE - 2):
            for z in range(2, CHUNK_SIZE - 2):
                sy = int(heights[x, z])
                biome = int(biomes[x, z])
                if sy <= SEA_LEVEL + 1 or sy >= CHUNK_HEIGHT - 9:
                    continue
                if biome not in (3, 4, 5):  # Valley, Plains, Hills
                    continue
                if blocks[x, sy, z] != GRASS:
                    continue

                # Deterministic per-coordinate hash for tree placement
                world_x = int(cx * CHUNK_SIZE + x)
                world_z = int(cz * CHUNK_SIZE + z)
                h_val = ((world_x * 73856093) ^ (world_z * 19349663) ^ self.seed_int) & 0xFFFFFFFF
                # ~1.8% chance on eligible grass columns, spaced on a 3x3 subgrid
                if (world_x % 3 == 0) and (world_z % 3 == 0) and (h_val % 100 < 14):
                    trunk_h = 4 + (h_val % 2)
                    # Build trunk
                    for ty in range(sy + 1, sy + 1 + trunk_h):
                        blocks[x, ty, z] = WOOD
                    # Build leaf canopy
                    canopy_base = sy + trunk_h - 1
                    for ly in range(canopy_base, canopy_base + 2):
                        for lx_off in range(-2, 3):
                            for lz_off in range(-2, 3):
                                if abs(lx_off) == 2 and abs(lz_off) == 2:
                                    continue
                                if lx_off == 0 and lz_off == 0 and ly < sy + trunk_h + 1:
                                    continue
                                if blocks[x + lx_off, ly, z + lz_off] == AIR:
                                    blocks[x + lx_off, ly, z + lz_off] = LEAVES
                    # Top crown of leaves
                    top_y = canopy_base + 2
                    for lx_off in range(-1, 2):
                        for lz_off in range(-1, 2):
                            if abs(lx_off) == 1 and abs(lz_off) == 1 and (lx_off + lz_off != 0):
                                continue
                            if blocks[x + lx_off, top_y, z + lz_off] == AIR:
                                blocks[x + lx_off, top_y, z + lz_off] = LEAVES

        return blocks
