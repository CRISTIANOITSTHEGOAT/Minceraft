"""
Chunk management and optimized voxel mesh builder with hidden-face culling.
Combines all visible block faces in a 16x64x16 chunk into a single Ursina Mesh
to achieve high framerates and low draw-call overhead.
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

from game.assets_gen import get_atlas_texture
from game.blocks import (
    AIR,
    BLOCKS_BY_ID,
    TORCH,
    WATER,
    get_block_by_id,
    get_tile_uvs,
)
from game.terrain import CHUNK_HEIGHT, CHUNK_SIZE

# Precompute a boolean lookup table of transparent block IDs (air, water, leaves, glass, torch)
_TRANSPARENT_LUT = np.zeros(256, dtype=bool)
_OPAQUE_SOLID_LUT = np.zeros(256, dtype=bool)
for _bid, _bdef in BLOCKS_BY_ID.items():
    _TRANSPARENT_LUT[_bid] = _bdef.transparent
    _OPAQUE_SOLID_LUT[_bid] = (_bdef.id != AIR) and (not _bdef.liquid) and (_bdef.id != TORCH)

# Precompute UVs for every (block_id, face_name)
_FACE_NAMES = ("top", "bottom", "north", "south", "east", "west")
_UV_LUT: Dict[Tuple[int, str], Tuple[Tuple[float, float], ...]] = {}
for _bid, _bdef in BLOCKS_BY_ID.items():
    if _bid == AIR:
        continue
    for _fname in _FACE_NAMES:
        col, row = _bdef.get_tile(_fname)
        _UV_LUT[(_bid, _fname)] = get_tile_uvs(col, row)


class Chunk:
    """Represents a 16x64x16 column of voxels and its rendered 3D mesh entities."""

    def __init__(self, cx: int, cz: int, blocks: np.ndarray, world=None):
        self.cx = int(cx)
        self.cz = int(cz)
        self.world = world
        self.blocks: np.ndarray = blocks  # uint8 array of shape (16, 64, 16)
        self.solid_entity = None
        self.water_entity = None
        self.is_dirty: bool = True
        self.unloaded: bool = False

    @property
    def world_x(self) -> int:
        return self.cx * CHUNK_SIZE

    @property
    def world_z(self) -> int:
        return self.cz * CHUNK_SIZE

    def get_block_local(self, lx: int, ly: int, lz: int) -> int:
        if 0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_HEIGHT and 0 <= lz < CHUNK_SIZE:
            return int(self.blocks[lx, ly, lz])
        return AIR

    def set_block_local(self, lx: int, ly: int, lz: int, block_id: int) -> bool:
        if 0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_HEIGHT and 0 <= lz < CHUNK_SIZE:
            self.blocks[lx, ly, lz] = np.uint8(block_id)
            self.is_dirty = True
            return True
        return False

    def _get_padded_blocks(self) -> np.ndarray:
        """
        Create an (18, 66, 18) padded block array including 1-voxel slices from
        neighboring chunks if loaded so boundary faces are accurately culled.
        """
        padded = np.zeros((CHUNK_SIZE + 2, CHUNK_HEIGHT + 2, CHUNK_SIZE + 2), dtype=np.uint8)
        padded[1:-1, 1:-1, 1:-1] = self.blocks

        if self.world is not None:
            chunks = self.world.chunks
            # -X neighbor
            c_west = chunks.get((self.cx - 1, self.cz))
            if c_west is not None:
                padded[0, 1:-1, 1:-1] = c_west.blocks[-1, :, :]
            # +X neighbor
            c_east = chunks.get((self.cx + 1, self.cz))
            if c_east is not None:
                padded[-1, 1:-1, 1:-1] = c_east.blocks[0, :, :]
            # -Z neighbor
            c_south = chunks.get((self.cx, self.cz - 1))
            if c_south is not None:
                padded[1:-1, 1:-1, 0] = c_south.blocks[:, :, -1]
            # +Z neighbor
            c_north = chunks.get((self.cx, self.cz + 1))
            if c_north is not None:
                padded[1:-1, 1:-1, -1] = c_north.blocks[:, :, 0]

        return padded

    def build_mesh(self) -> None:
        """
        Build or rebuild the Ursina Mesh for solid blocks and water blocks in this chunk.
        Uses NumPy boolean masks for fast hidden-face culling.
        """
        if self.unloaded:
            return

        from ursina import Entity, Mesh, Vec2, Vec3, color, destroy

        padded = self._get_padded_blocks()
        center = padded[1:-1, 1:-1, 1:-1]
        is_solid_blk = _OPAQUE_SOLID_LUT[center]

        # Neighbor transparency masks
        trans_padded = _TRANSPARENT_LUT[padded]

        # Exposed faces for solid/leaves/glass blocks:
        # For opaque blocks, show face if neighbor is transparent.
        # For transparent solid blocks (leaves, glass), show face if neighbor is transparent AND not identical glass.
        verts: List[Tuple[float, float, float]] = []
        tris: List[int] = []
        uvs: List[Tuple[float, float]] = []
        cols: List[object] = []

        # Helper to append a quad with 4 vertices, 4 UVs, and a brightness shade
        def add_quad(v0, v1, v2, v3, uv4, shade: float):
            base_idx = len(verts)
            verts.extend((v0, v1, v2, v3))
            tris.extend((base_idx, base_idx + 1, base_idx + 2, base_idx, base_idx + 2, base_idx + 3))
            uvs.extend(uv4)
            c = color.rgb(shade, shade, shade)
            cols.extend((c, c, c, c))

        # 1. Top (+Y)
        nb_top = padded[1:-1, 2:, 1:-1]
        mask_top = is_solid_blk & trans_padded[1:-1, 2:, 1:-1] & ~((center == nb_top) & (center != 7))
        for x, y, z in np.argwhere(mask_top):
            bid = int(center[x, y, z])
            fx, fy, fz = float(x), float(y), float(z)
            add_quad(
                (fx, fy + 1.0, fz),
                (fx + 1.0, fy + 1.0, fz),
                (fx + 1.0, fy + 1.0, fz + 1.0),
                (fx, fy + 1.0, fz + 1.0),
                _UV_LUT[(bid, "top")],
                1.0,
            )

        # 2. Bottom (-Y)
        nb_bot = padded[1:-1, :-2, 1:-1]
        mask_bot = is_solid_blk & trans_padded[1:-1, :-2, 1:-1] & (y_mask := (np.arange(CHUNK_HEIGHT)[None, :, None] > 0)) & ~((center == nb_bot) & (center != 7))
        for x, y, z in np.argwhere(mask_bot):
            bid = int(center[x, y, z])
            fx, fy, fz = float(x), float(y), float(z)
            add_quad(
                (fx, fy, fz + 1.0),
                (fx + 1.0, fy, fz + 1.0),
                (fx + 1.0, fy, fz),
                (fx, fy, fz),
                _UV_LUT[(bid, "bottom")],
                0.55,
            )

        # 3. North (+Z)
        nb_north = padded[1:-1, 1:-1, 2:]
        mask_north = is_solid_blk & trans_padded[1:-1, 1:-1, 2:] & ~((center == nb_north) & (center != 7))
        for x, y, z in np.argwhere(mask_north):
            bid = int(center[x, y, z])
            fx, fy, fz = float(x), float(y), float(z)
            add_quad(
                (fx + 1.0, fy, fz + 1.0),
                (fx, fy, fz + 1.0),
                (fx, fy + 1.0, fz + 1.0),
                (fx + 1.0, fy + 1.0, fz + 1.0),
                _UV_LUT[(bid, "north")],
                0.86,
            )

        # 4. South (-Z)
        nb_south = padded[1:-1, 1:-1, :-2]
        mask_south = is_solid_blk & trans_padded[1:-1, 1:-1, :-2] & ~((center == nb_south) & (center != 7))
        for x, y, z in np.argwhere(mask_south):
            bid = int(center[x, y, z])
            fx, fy, fz = float(x), float(y), float(z)
            add_quad(
                (fx, fy, fz),
                (fx + 1.0, fy, fz),
                (fx + 1.0, fy + 1.0, fz),
                (fx, fy + 1.0, fz),
                _UV_LUT[(bid, "south")],
                0.82,
            )

        # 5. East (+X)
        nb_east = padded[2:, 1:-1, 1:-1]
        mask_east = is_solid_blk & trans_padded[2:, 1:-1, 1:-1] & ~((center == nb_east) & (center != 7))
        for x, y, z in np.argwhere(mask_east):
            bid = int(center[x, y, z])
            fx, fy, fz = float(x), float(y), float(z)
            add_quad(
                (fx + 1.0, fy, fz),
                (fx + 1.0, fy, fz + 1.0),
                (fx + 1.0, fy + 1.0, fz + 1.0),
                (fx + 1.0, fy + 1.0, fz),
                _UV_LUT[(bid, "east")],
                0.74,
            )

        # 6. West (-X)
        nb_west = padded[:-2, 1:-1, 1:-1]
        mask_west = is_solid_blk & trans_padded[:-2, 1:-1, 1:-1] & ~((center == nb_west) & (center != 7))
        for x, y, z in np.argwhere(mask_west):
            bid = int(center[x, y, z])
            fx, fy, fz = float(x), float(y), float(z)
            add_quad(
                (fx, fy, fz + 1.0),
                (fx, fy, fz),
                (fx, fy + 1.0, fz),
                (fx, fy + 1.0, fz + 1.0),
                _UV_LUT[(bid, "west")],
                0.70,
            )

        # 7. Torches (slender glowing post)
        torch_coords = np.argwhere(center == TORCH)
        if len(torch_coords) > 0:
            t_uv = _UV_LUT[(TORCH, "side")]
            for x, y, z in torch_coords:
                fx, fy, fz = float(x), float(y), float(z)
                x0, x1 = fx + 0.4, fx + 0.6
                z0, z1 = fz + 0.4, fz + 0.6
                y0, y1 = fy, fy + 0.72
                add_quad((x1, y0, z1), (x0, y0, z1), (x0, y1, z1), (x1, y1, z1), t_uv, 1.0)
                add_quad((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), t_uv, 1.0)
                add_quad((x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0), t_uv, 1.0)
                add_quad((x0, y0, z1), (x0, y0, z0), (x0, y1, z0), (x0, y1, z1), t_uv, 1.0)
                add_quad((x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1), _UV_LUT[(TORCH, "top")], 1.0)

        atlas_tex = get_atlas_texture()

        # Create or update solid chunk entity
        if verts:
            mesh = Mesh(vertices=verts, triangles=tris, uvs=uvs, colors=cols, static=True)
            if self.solid_entity is None:
                self.solid_entity = Entity(
                    model=mesh,
                    texture=atlas_tex,
                    position=(self.world_x, 0, self.world_z),
                    double_sided=True,
                )
            else:
                self.solid_entity.model = mesh
        else:
            if self.solid_entity is not None:
                destroy(self.solid_entity)
                self.solid_entity = None

        # Build translucent Water surface mesh (only where water meets air)
        is_water = (center == WATER)
        water_top_mask = is_water & (padded[1:-1, 2:, 1:-1] == AIR)
        w_coords = np.argwhere(water_top_mask)
        if len(w_coords) > 0:
            w_verts: List[Tuple[float, float, float]] = []
            w_tris: List[int] = []
            w_uvs: List[Tuple[float, float]] = []
            w_cols: List[object] = []
            w_uv4 = _UV_LUT[(WATER, "top")]
            wc = color.rgba(0.85, 0.92, 1.0, 0.72)

            for x, y, z in w_coords:
                fx, fy, fz = float(x), float(y) + 0.88, float(z)
                b_idx = len(w_verts)
                w_verts.extend((
                    (fx, fy, fz),
                    (fx + 1.0, fy, fz),
                    (fx + 1.0, fy, fz + 1.0),
                    (fx, fy, fz + 1.0),
                ))
                w_tris.extend((b_idx, b_idx + 1, b_idx + 2, b_idx, b_idx + 2, b_idx + 3))
                w_uvs.extend(w_uv4)
                w_cols.extend((wc, wc, wc, wc))

            w_mesh = Mesh(vertices=w_verts, triangles=w_tris, uvs=w_uvs, colors=w_cols, static=True)
            if self.water_entity is None:
                self.water_entity = Entity(
                    model=w_mesh,
                    texture=atlas_tex,
                    position=(self.world_x, 0, self.world_z),
                    double_sided=True,
                )
            else:
                self.water_entity.model = w_mesh
        else:
            if self.water_entity is not None:
                destroy(self.water_entity)
                self.water_entity = None

        self.is_dirty = False

    def apply_lighting_tint(self, brightness: float) -> None:
        """Update chunk entity tint based on day/night cycle brightness."""
        b = max(0.25, min(1.0, float(brightness)))
        try:
            from ursina import color
            c = color.rgb(b, b, min(1.0, b * 1.05))
            if self.solid_entity is not None:
                self.solid_entity.color = c
            if self.water_entity is not None:
                self.water_entity.color = color.rgba(b * 0.85, b * 0.92, min(1.0, b * 1.05), 0.74)
        except Exception:
            pass

    def unload(self) -> None:
        """Destroy Ursina entities cleanly when chunk is unloaded."""
        self.unloaded = True
        try:
            from ursina import destroy
            if self.solid_entity is not None:
                destroy(self.solid_entity)
                self.solid_entity = None
            if self.water_entity is not None:
                destroy(self.water_entity)
                self.water_entity = None
        except Exception:
            self.solid_entity = None
            self.water_entity = None
