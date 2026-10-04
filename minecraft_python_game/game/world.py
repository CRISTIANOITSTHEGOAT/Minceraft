"""
Voxel World manager: handles chunk loading/unloading, modified blocks,
3D DDA voxel raycasting, day/night sky cycle, and block break particles.
"""

import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from game.blocks import AIR, BEDROCK, CHEST, FURNACE, WATER, get_block_by_id
from game.chunk import Chunk
from game.terrain import CHUNK_HEIGHT, CHUNK_SIZE, SEA_LEVEL, TerrainGenerator


@dataclass
class VoxelHit:
    hit: bool = False
    block_pos: Tuple[int, int, int] = (0, 0, 0)
    place_pos: Tuple[int, int, int] = (0, 0, 0)
    normal: Tuple[int, int, int] = (0, 1, 0)
    block_id: int = AIR
    distance: float = 0.0


class World:
    """Manages chunks, terrain generation, block modifications, day/night cycle, and particles."""

    DAY_LENGTH_SECONDS = 240.0  # 4 minutes per full 24h in-game day

    def __init__(self, seed="PyCraft2026", world_name: str = "New World", difficulty: str = "Normal"):
        self.world_name = world_name
        self.difficulty = difficulty if difficulty in ("Peaceful", "Easy", "Normal", "Hard") else "Normal"
        self.terrain = TerrainGenerator(seed)
        self.seed = self.terrain.seed_str

        # Loaded chunks: (cx, cz) -> Chunk
        self.chunks: Dict[Tuple[int, int], Chunk] = {}
        # Persistent block modifications: (wx, wy, wz) -> block_id
        self.modified_blocks: Dict[Tuple[int, int, int], int] = {}
        # Chest inventories: (wx, wy, wz) -> list of slot dicts
        self.chests: Dict[Tuple[int, int, int], List[Optional[ dict ]]] = {}
        # Furnace states: (wx, wy, wz) -> dict
        self.furnace_data: Dict[Tuple[int, int, int], dict] = {}

        # Background terrain generation cache
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._pending_futures: Dict[Tuple[int, int], object] = {}
        self._chunk_queue: List[Tuple[int, int]] = []

        # Day/Night cycle state (0.0 .. 24.0 hours; 8.0 = morning)
        self.world_time: float = 8.0
        self.day_count: int = 1
        self.brightness: float = 1.0
        self._last_tinted_brightness: float = -1.0

        # Sky & Celestial entities
        self.sky_dome = None
        self.sun_entity = None
        self.moon_entity = None
        self._init_sky_entities()

        # Short-lived block break particles: list of [entity, vx, vy, vz, ttl]
        self._particles: List[list] = []

    def _init_sky_entities(self) -> None:
        try:
            from ursina import Entity, color, window
            sky_col = color.rgb(0.45, 0.75, 0.98)
            window.color = sky_col
            self.sky_dome = Entity(
                model="sphere",
                scale=500,
                double_sided=True,
                unlit=True,
                color=sky_col,
            )
            self.sun_entity = Entity(
                model="cube",
                scale=22,
                unlit=True,
                color=color.rgb(1.0, 0.95, 0.55),
                position=(0, 260, 0),
            )
            self.moon_entity = Entity(
                model="cube",
                scale=18,
                unlit=True,
                color=color.rgb(0.85, 0.90, 1.0),
                position=(0, -260, 0),
            )
        except Exception:
            pass

    @property
    def is_night(self) -> bool:
        return self.world_time >= 19.0 or self.world_time < 5.5

    def get_time_label(self) -> str:
        hours = int(self.world_time) % 24
        minutes = int((self.world_time - int(self.world_time)) * 60) % 60
        phase = "Night" if self.is_night else "Day"
        return f"Day {self.day_count} - {hours:02d}:{minutes:02d} [{phase}]"

    @staticmethod
    def world_to_chunk(wx: int, wz: int) -> Tuple[int, int, int, int]:
        cx = math.floor(wx / CHUNK_SIZE)
        cz = math.floor(wz / CHUNK_SIZE)
        lx = int(wx - cx * CHUNK_SIZE)
        lz = int(wz - cz * CHUNK_SIZE)
        return cx, cz, lx, lz

    def find_spawn_position(self, start_x: int = 8, start_z: int = 8) -> Tuple[float, float, float]:
        """Find a safe dry surface spawn coordinate near (start_x, start_z)."""
        best_pos = (float(start_x) + 0.5, 30.0, float(start_z) + 0.5)
        for radius in range(0, 32, 2):
            for dx in (-radius, 0, radius):
                for dz in (-radius, 0, radius):
                    wx = start_x + dx
                    wz = start_z + dz
                    biome, sy = self.terrain.get_biome_and_height(wx, wz)
                    if sy > SEA_LEVEL:
                        # Ensure chunk is loaded and check actual highest solid block
                        cx, cz, lx, lz = self.world_to_chunk(wx, wz)
                        chunk = self._ensure_chunk_data(cx, cz)
                        top_y = sy
                        for y in range(CHUNK_HEIGHT - 2, 1, -1):
                            bid = chunk.get_block_local(lx, y, lz)
                            if bid != AIR and bid != WATER:
                                top_y = y
                                break
                        return (float(wx) + 0.5, float(top_y) + 1.05, float(wz) + 0.5)
        # Fallback if area is mostly water
        _, sy = self.terrain.get_biome_and_height(start_x, start_z)
        return (float(start_x) + 0.5, float(max(sy, SEA_LEVEL) + 2.0), float(start_z) + 0.5)

    def _apply_modifications_to_chunk(self, cx: int, cz: int, blocks: np.ndarray) -> None:
        """Apply any saved/modified blocks that belong to chunk (cx, cz)."""
        x0 = cx * CHUNK_SIZE
        z0 = cz * CHUNK_SIZE
        for (wx, wy, wz), bid in self.modified_blocks.items():
            if x0 <= wx < x0 + CHUNK_SIZE and z0 <= wz < z0 + CHUNK_SIZE and 0 <= wy < CHUNK_HEIGHT:
                blocks[wx - x0, wy, wz - z0] = np.uint8(bid)

    def _ensure_chunk_data(self, cx: int, cz: int) -> Chunk:
        """Synchronously generate or retrieve chunk (cx, cz) without necessarily building its mesh yet."""
        key = (cx, cz)
        if key in self.chunks:
            return self.chunks[key]

        try:
            if key in self._pending_futures:
                fut = self._pending_futures.pop(key)
                blocks = fut.result(timeout=2.0)
            else:
                blocks = self.terrain.generate_chunk_blocks(cx, cz)
        except Exception as exc:
            print(f"[World] Fallback flat chunk at {key} due to error: {exc}")
            blocks = np.zeros((CHUNK_SIZE, CHUNK_HEIGHT, CHUNK_SIZE), dtype=np.uint8)
            blocks[:, 0, :] = BEDROCK
            blocks[:, 1:16, :] = 3  # Stone
            blocks[:, 16, :] = 1    # Grass

        self._apply_modifications_to_chunk(cx, cz, blocks)
        chunk = Chunk(cx, cz, blocks, world=self)
        self.chunks[key] = chunk
        return chunk

    def update_chunks(self, player_x: float, player_z: float, render_distance: int = 3, immediate: bool = False) -> None:
        """
        Load nearby chunks within render_distance and unload distant chunks.
        If immediate=True, builds all chunks within render_distance immediately (used on initial spawn).
        """
        rd = max(2, min(6, int(render_distance)))
        pcx = math.floor(player_x / CHUNK_SIZE)
        pcz = math.floor(player_z / CHUNK_SIZE)

        # 1. Unload chunks beyond rd + 1
        unload_dist = rd + 1
        to_unload = [
            key for key in self.chunks
            if abs(key[0] - pcx) > unload_dist or abs(key[1] - pcz) > unload_dist
        ]
        for key in to_unload:
            ch = self.chunks.pop(key, None)
            if ch is not None:
                ch.unload()

        # 2. Gather desired chunk coordinates sorted by distance to player
        desired: List[Tuple[int, int]] = []
        for dx in range(-rd, rd + 1):
            for dz in range(-rd, rd + 1):
                if dx * dx + dz * dz <= (rd + 0.5) ** 2:
                    desired.append((pcx + dx, pcz + dz))
        desired.sort(key=lambda c: (c[0] - pcx) ** 2 + (c[1] - pcz) ** 2)

        if immediate:
            for cx, cz in desired:
                self._ensure_chunk_data(cx, cz)
            for cx, cz in desired:
                ch = self.chunks[(cx, cz)]
                if ch.is_dirty:
                    ch.build_mesh()
                    ch.apply_lighting_tint(self.brightness)
            return

        # 3. Schedule background generation for missing chunks
        for key in desired:
            if key not in self.chunks and key not in self._pending_futures:
                if len(self._pending_futures) < 6:
                    self._pending_futures[key] = self._executor.submit(
                        self.terrain.generate_chunk_blocks, key[0], key[1]
                    )

        # 4. Harvest completed background futures
        done_keys = [k for k, fut in self._pending_futures.items() if fut.done()]
        for key in done_keys:
            self._ensure_chunk_data(key[0], key[1])
            # Mark neighbor chunks dirty so border faces update
            for nkey in ((key[0] - 1, key[1]), (key[0] + 1, key[1]), (key[0], key[1] - 1), (key[0], key[1] + 1)):
                if nkey in self.chunks:
                    self.chunks[nkey].is_dirty = True

        # 5. Ensure immediate 3x3 around player exists synchronously so player never steps on unloaded void
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                near_key = (pcx + dx, pcz + dz)
                if near_key not in self.chunks:
                    self._ensure_chunk_data(near_key[0], near_key[1])

        # 6. Build meshes for up to 2 dirty chunks per frame, closest first
        built_count = 0
        for key in desired:
            ch = self.chunks.get(key)
            if ch is not None and ch.is_dirty:
                ch.build_mesh()
                ch.apply_lighting_tint(self.brightness)
                built_count += 1
                if built_count >= 2:
                    break

    def get_block(self, wx: int, wy: int, wz: int) -> int:
        """Return block ID at integer world coordinates (wx, wy, wz)."""
        if wy < 0 or wy >= CHUNK_HEIGHT:
            return AIR
        pos = (int(wx), int(wy), int(wz))
        if pos in self.modified_blocks:
            return self.modified_blocks[pos]
        cx, cz, lx, lz = self.world_to_chunk(pos[0], pos[2])
        chunk = self.chunks.get((cx, cz))
        if chunk is not None:
            return chunk.get_block_local(lx, pos[1], lz)
        return AIR

    def is_solid(self, wx: int, wy: int, wz: int) -> bool:
        """Return True if the voxel at (wx, wy, wz) is solid for collision."""
        if wy < 0:
            return True  # Solid floor guard below bedrock
        if wy >= CHUNK_HEIGHT:
            return False
        bid = self.get_block(wx, wy, wz)
        if bid == AIR or bid == WATER:
            return False
        return get_block_by_id(bid).solid

    def is_water(self, wx: int, wy: int, wz: int) -> bool:
        if wy < 0 or wy >= CHUNK_HEIGHT:
            return False
        return self.get_block(wx, wy, wz) == WATER

    def set_block(self, wx: int, wy: int, wz: int, block_id: int, record_modification: bool = True) -> bool:
        """
        Modify a block at (wx, wy, wz), update the chunk mesh and adjacent neighbor chunk
        meshes if on a chunk boundary.
        """
        wx, wy, wz = int(wx), int(wy), int(wz)
        if wy < 0 or wy >= CHUNK_HEIGHT:
            return False

        current = self.get_block(wx, wy, wz)
        if current == BEDROCK and block_id == AIR:
            return False  # Bedrock cannot be broken

        cx, cz, lx, lz = self.world_to_chunk(wx, wz)
        chunk = self._ensure_chunk_data(cx, cz)
        chunk.set_block_local(lx, wy, lz, block_id)

        if record_modification:
            self.modified_blocks[(wx, wy, wz)] = int(block_id)
            if current == CHEST and block_id != CHEST:
                self.chests.pop((wx, wy, wz), None)
            if current == FURNACE and block_id != FURNACE:
                self.furnace_data.pop((wx, wy, wz), None)

        chunk.build_mesh()
        chunk.apply_lighting_tint(self.brightness)

        # Rebuild neighbor chunk if modification is on a chunk boundary
        if lx == 0 and (cx - 1, cz) in self.chunks:
            nb = self.chunks[(cx - 1, cz)]
            nb.build_mesh()
            nb.apply_lighting_tint(self.brightness)
        elif lx == CHUNK_SIZE - 1 and (cx + 1, cz) in self.chunks:
            nb = self.chunks[(cx + 1, cz)]
            nb.build_mesh()
            nb.apply_lighting_tint(self.brightness)

        if lz == 0 and (cx, cz - 1) in self.chunks:
            nb = self.chunks[(cx, cz - 1)]
            nb.build_mesh()
            nb.apply_lighting_tint(self.brightness)
        elif lz == CHUNK_SIZE - 1 and (cx, cz + 1) in self.chunks:
            nb = self.chunks[(cx, cz + 1)]
            nb.build_mesh()
            nb.apply_lighting_tint(self.brightness)

        return True

    def spawn_break_particles(self, wx: int, wy: int, wz: int, block_id: int) -> None:
        """Spawn a small burst of voxel debris particles when a block is broken."""
        bdef = get_block_by_id(block_id)
        try:
            from ursina import Entity, color
            r, g, b = [c / 255.0 for c in bdef.base_color]
            pcol = color.rgb(r, g, b)
            rng = np.random.RandomState((wx * 73 + wy * 31 + wz * 17) & 0xFFFF)
            for _ in range(8):
                ox = wx + 0.5 + float(rng.uniform(-0.25, 0.25))
                oy = wy + 0.5 + float(rng.uniform(-0.25, 0.25))
                oz = wz + 0.5 + float(rng.uniform(-0.25, 0.25))
                vx = float(rng.uniform(-2.2, 2.2))
                vy = float(rng.uniform(1.5, 3.8))
                vz = float(rng.uniform(-2.2, 2.2))
                ent = Entity(model="cube", scale=0.12, position=(ox, oy, oz), color=pcol)
                self._particles.append([ent, vx, vy, vz, 0.35])
        except Exception:
            pass

    def raycast_voxel(
        self,
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        max_dist: float = 6.0,
    ) -> VoxelHit:
        """
        Exact 3D DDA (Amanatides & Woo) voxel grid raycast.
        Finds the first targetable block (non-air, non-water) along the ray.
        """
        ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
        dx, dy, dz = float(direction[0]), float(direction[1]), float(direction[2])
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length < 1e-8:
            return VoxelHit(hit=False)
        dx, dy, dz = dx / length, dy / length, dz / length

        bx = math.floor(ox)
        by = math.floor(oy)
        bz = math.floor(oz)

        step_x = 1 if dx >= 0 else -1
        step_y = 1 if dy >= 0 else -1
        step_z = 1 if dz >= 0 else -1

        t_delta_x = abs(1.0 / dx) if abs(dx) > 1e-8 else 1e30
        t_delta_y = abs(1.0 / dy) if abs(dy) > 1e-8 else 1e30
        t_delta_z = abs(1.0 / dz) if abs(dz) > 1e-8 else 1e30

        t_max_x = ((bx + 1.0 - ox) if step_x > 0 else (ox - bx)) * t_delta_x
        t_max_y = ((by + 1.0 - oy) if step_y > 0 else (oy - by)) * t_delta_y
        t_max_z = ((bz + 1.0 - oz) if step_z > 0 else (oz - bz)) * t_delta_z

        normal = (0, 1, 0)
        dist = 0.0

        for _ in range(int(max_dist * 4) + 8):
            if 0 <= by < CHUNK_HEIGHT:
                bid = self.get_block(bx, by, bz)
                if bid != AIR and bid != WATER:
                    place_pos = (bx + normal[0], by + normal[1], bz + normal[2])
                    return VoxelHit(
                        hit=True,
                        block_pos=(bx, by, bz),
                        place_pos=place_pos,
                        normal=normal,
                        block_id=bid,
                        distance=dist,
                    )

            if t_max_x < t_max_y:
                if t_max_x < t_max_z:
                    bx += step_x
                    dist = t_max_x
                    t_max_x += t_delta_x
                    normal = (-step_x, 0, 0)
                else:
                    bz += step_z
                    dist = t_max_z
                    t_max_z += t_delta_z
                    normal = (0, 0, -step_z)
            else:
                if t_max_y < t_max_z:
                    by += step_y
                    dist = t_max_y
                    t_max_y += t_delta_y
                    normal = (0, -step_y, 0)
                else:
                    bz += step_z
                    dist = t_max_z
                    t_max_z += t_delta_z
                    normal = (0, 0, -step_z)

            if dist > max_dist:
                break

        return VoxelHit(hit=False)

    def update(self, dt: float, player_pos: Tuple[float, float, float], render_distance: int = 3) -> None:
        """Advance day/night cycle, update sky/sun/moon, update particles, and stream chunks."""
        dt = min(0.1, max(0.0, float(dt)))

        # 1. Advance world time (24 hours over DAY_LENGTH_SECONDS)
        hours_per_sec = 24.0 / self.DAY_LENGTH_SECONDS
        self.world_time += dt * hours_per_sec
        if self.world_time >= 24.0:
            self.world_time -= 24.0
            self.day_count += 1

        # 2. Compute daylight brightness from solar angle (noon=12.0 is peak, midnight=0.0 is lowest)
        solar_angle = ((self.world_time - 6.0) / 24.0) * 2.0 * math.pi
        sun_elev = math.sin(solar_angle)  # +1 at noon (12h), -1 at midnight (0h)
        raw_b = 0.64 + 0.46 * sun_elev
        self.brightness = max(0.28, min(1.0, raw_b))

        # 3. Update Sky Dome & Sun/Moon positions around player
        px, py, pz = player_pos
        try:
            from ursina import color, destroy, window
            if self.sky_dome is not None:
                self.sky_dome.position = (px, py, pz)
                # Interpolate sky color between night, dusk/dawn, and day
                if sun_elev > 0.2:
                    t = min(1.0, (sun_elev - 0.2) / 0.6)
                    r = 0.85 * (1 - t) + 0.42 * t
                    g = 0.58 * (1 - t) + 0.72 * t
                    b = 0.45 * (1 - t) + 0.98 * t
                elif sun_elev > -0.2:
                    t = (sun_elev + 0.2) / 0.4  # 0 at night edge, 1 at dawn/dusk peak
                    r = 0.06 * (1 - t) + 0.85 * t
                    g = 0.08 * (1 - t) + 0.52 * t
                    b = 0.18 * (1 - t) + 0.42 * t
                else:
                    r, g, b = 0.05, 0.07, 0.16
                sky_c = color.rgb(r, g, b)
                self.sky_dome.color = sky_c
                window.color = sky_c

            orbit_r = 250.0
            sx = px + math.cos(solar_angle) * orbit_r
            sy = py + math.sin(solar_angle) * orbit_r
            sz = pz - 40.0
            if self.sun_entity is not None:
                self.sun_entity.position = (sx, sy, sz)
            if self.moon_entity is not None:
                self.moon_entity.position = (px - math.cos(solar_angle) * orbit_r, py - math.sin(solar_angle) * orbit_r, sz)

            # Update chunk lighting tint when brightness shifts by >= 0.03
            if abs(self.brightness - self._last_tinted_brightness) >= 0.03:
                self._last_tinted_brightness = self.brightness
                for ch in self.chunks.values():
                    ch.apply_lighting_tint(self.brightness)

            # 4. Update debris particles
            alive_particles = []
            for p in self._particles:
                ent, vx, vy, vz, ttl = p
                ttl -= dt
                if ttl <= 0:
                    destroy(ent)
                else:
                    vy -= 14.0 * dt
                    ent.x += vx * dt
                    ent.y += vy * dt
                    ent.z += vz * dt
                    p[3] = vz
                    p[2] = vy
                    p[4] = ttl
                    alive_particles.append(p)
            self._particles = alive_particles
        except Exception:
            pass

        # 5. Update chunk streaming
        self.update_chunks(px, pz, render_distance=render_distance, immediate=False)

    def cleanup(self) -> None:
        """Destroy all chunk entities, particles, and sky entities cleanly."""
        try:
            from ursina import destroy
            for ch in list(self.chunks.values()):
                ch.unload()
            self.chunks.clear()
            for p in self._particles:
                destroy(p[0])
            self._particles.clear()
            for ent in (self.sky_dome, self.sun_entity, self.moon_entity):
                if ent is not None:
                    destroy(ent)
            self.sky_dome = None
            self.sun_entity = None
            self.moon_entity = None
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
