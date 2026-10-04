"""
First-Person Player Controller:
Handles movement (W/A/S/D, Sprint, Jump, Swim), smooth camera look,
3D Voxel AABB collision detection, block mining & placement, first-person
held tool/item display, health, hunger, eating food, death, and respawning.
"""

import math
from typing import Any, Dict, Optional, Tuple

from game.assets_gen import get_item_icon_texture, play_game_sound
from game.blocks import (
    AIR,
    BEDROCK,
    CHEST,
    CRAFTING_TABLE,
    FURNACE,
    WATER,
    calculate_mining_time,
    get_block_by_id,
    get_item_def,
)
from game.inventory import Inventory
from game.terrain import CHUNK_HEIGHT
from game.world import VoxelHit, World


class Player:
    """First-person survival player with voxel AABB physics, inventory, health, and hunger."""

    HALF_WIDTH = 0.30
    HEIGHT = 1.74
    EYE_HEIGHT = 1.56

    WALK_SPEED = 4.6
    SPRINT_SPEED = 7.0
    SWIM_SPEED = 2.9
    JUMP_VELOCITY = 7.7
    GRAVITY = 22.0
    REACH_DISTANCE = 5.8

    def __init__(self, world: World, spawn_pos: Tuple[float, float, float] = (8.5, 25.0, 8.5)):
        self.world = world
        self.spawn_pos = (float(spawn_pos[0]), float(spawn_pos[1]), float(spawn_pos[2]))
        self.x, self.y, self.z = self.spawn_pos
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.vz: float = 0.0

        # Camera orientation in degrees
        self.yaw: float = 0.0
        self.pitch: float = 10.0

        # Physics state
        self.on_ground: bool = False
        self.in_water: bool = False
        self.head_underwater: bool = False
        self.is_sprinting: bool = False
        self.fall_distance: float = 0.0

        # Survival stats (Section 16)
        self.max_health: float = 20.0
        self.health: float = 20.0
        self.max_hunger: float = 20.0
        self.hunger: float = 20.0
        self.is_dead: bool = False
        self.death_reason: str = ""
        self.hurt_flash_timer: float = 0.0
        self._regen_timer: float = 0.0
        self._starve_timer: float = 0.0
        self._step_sound_timer: float = 0.0

        # Inventory
        self.inventory = Inventory()

        # Block targeting & mining progress (Section 7)
        self.targeted_hit: VoxelHit = VoxelHit(hit=False)
        self.mining_block_pos: Optional[Tuple[int, int, int]] = None
        self.mining_timer: float = 0.0
        self.mining_required_time: float = 1.0

        # First-person held item & block selection outline entities
        self.selection_box = None
        self.held_entity = None
        self._last_held_key: Optional[str] = "__init__"
        self._swing_anim: float = 0.0

        self._init_visual_entities()
        self.sync_camera()

    @property
    def position(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @position.setter
    def position(self, pos: Tuple[float, float, float]) -> None:
        self.x, self.y, self.z = float(pos[0]), float(pos[1]), float(pos[2])
        self.sync_camera()

    def get_eye_position(self) -> Tuple[float, float, float]:
        return (self.x, self.y + self.EYE_HEIGHT, self.z)

    def get_look_direction(self) -> Tuple[float, float, float]:
        """Compute unit 3D forward vector from current yaw and pitch (Ursina +Z forward convention)."""
        yaw_rad = math.radians(self.yaw)
        pitch_rad = math.radians(self.pitch)
        cos_p = math.cos(pitch_rad)
        dx = math.sin(yaw_rad) * cos_p
        dy = -math.sin(pitch_rad)
        dz = math.cos(yaw_rad) * cos_p
        return (dx, dy, dz)

    def _init_visual_entities(self) -> None:
        try:
            from ursina import Entity, camera, color
            # Translucent wireframe-like highlight around targeted block
            self.selection_box = Entity(
                model="cube",
                scale=1.012,
                color=color.rgba(1.0, 1.0, 1.0, 0.24),
                enabled=False,
            )
            # First-person held item / tool attached to camera
            self.held_entity = Entity(
                parent=camera,
                model="cube",
                position=(0.52, -0.38, 0.78),
                scale=(0.22, 0.22, 0.22),
                rotation=(12, -28, 8),
                enabled=True,
            )
        except Exception:
            pass

    def sync_camera(self) -> None:
        """Synchronize Ursina's first-person camera to the player's eye position and orientation."""
        try:
            from ursina import camera
            camera.position = (self.x, self.y + self.EYE_HEIGHT, self.z)
            camera.rotation = (self.pitch, self.yaw, 0.0)
        except Exception:
            pass

    def rotate_view(self, delta_yaw: float, delta_pitch: float) -> None:
        self.yaw = (self.yaw + float(delta_yaw)) % 360.0
        self.pitch = max(-89.0, min(89.0, self.pitch + float(delta_pitch)))
        self.sync_camera()

    def trigger_swing(self) -> None:
        self._swing_anim = 1.0

    def update_held_visual(self) -> None:
        """Update the 3D first-person held item/tool appearance when hotbar selection changes."""
        if self.held_entity is None:
            return
        held_key = self.inventory.get_selected_item_key()
        if held_key == self._last_held_key:
            return
        self._last_held_key = held_key

        try:
            from ursina import color
            if held_key is None:
                # Bare hand
                self.held_entity.scale = (0.14, 0.14, 0.34)
                self.held_entity.texture = None
                self.held_entity.color = color.rgb(0.92, 0.74, 0.60)
                return

            idef = get_item_def(held_key)
            tex = get_item_icon_texture(held_key)
            if idef is not None and idef.category == "block":
                self.held_entity.scale = (0.26, 0.26, 0.26)
                self.held_entity.texture = tex
                self.held_entity.color = color.white
            elif idef is not None and idef.tool_type in ("pickaxe", "axe", "sword"):
                # Elongated held tool/blade in first person
                self.held_entity.scale = (0.10, 0.34, 0.34)
                self.held_entity.texture = tex
                r, g, b = [c / 255.0 for c in idef.icon_color]
                self.held_entity.color = color.rgb(r, g, b)
            else:
                self.held_entity.scale = (0.20, 0.20, 0.10)
                self.held_entity.texture = tex
                self.held_entity.color = color.white
        except Exception:
            pass

    def _collides_aabb(self, px: float, py: float, pz: float) -> bool:
        """Return True if player's bounding box at (px, py, pz) overlaps any solid block."""
        hw = self.HALF_WIDTH
        min_bx = math.floor(px - hw)
        max_bx = math.floor(px + hw - 1e-5)
        min_by = math.floor(py)
        max_by = math.floor(py + self.HEIGHT - 1e-5)
        min_bz = math.floor(pz - hw)
        max_bz = math.floor(pz + hw - 1e-5)

        for bx in range(min_bx, max_bx + 1):
            for by in range(min_by, max_by + 1):
                for bz in range(min_bz, max_bz + 1):
                    if self.world.is_solid(bx, by, bz):
                        return True
        return False

    def block_intersects_player(self, bx: int, by: int, bz: int) -> bool:
        """Check whether placing a solid 1x1x1 block at (bx, by, bz) would intersect the player's body."""
        hw = self.HALF_WIDTH - 0.02
        p_min_x, p_max_x = self.x - hw, self.x + hw
        p_min_y, p_max_y = self.y + 0.02, self.y + self.HEIGHT - 0.02
        p_min_z, p_max_z = self.z - hw, self.z + hw

        return (
            p_max_x > bx and p_min_x < bx + 1
            and p_max_y > by and p_min_y < by + 1
            and p_max_z > bz and p_min_z < bz + 1
        )

    def move_and_collide(self, move_dx: float, move_dz: float, dt: float, jump_pressed: bool = False, settings=None) -> None:
        """
        Execute 1 physics step: horizontal movement, gravity/swimming, jumping,
        and exact axis-separated 3D voxel AABB collision resolution.
        """
        if self.is_dead:
            return
        dt = min(0.05, max(0.0, float(dt)))

        # Check water immersion
        bx_center = math.floor(self.x)
        bz_center = math.floor(self.z)
        feet_water = self.world.is_water(bx_center, math.floor(self.y + 0.1), bz_center)
        waist_water = self.world.is_water(bx_center, math.floor(self.y + 0.85), bz_center)
        was_in_water = self.in_water
        self.in_water = feet_water or waist_water
        self.head_underwater = self.world.is_water(bx_center, math.floor(self.y + self.EYE_HEIGHT), bz_center)

        if self.in_water and not was_in_water:
            play_game_sound("splash", settings)

        # Determine movement speed
        if self.in_water:
            speed = self.SWIM_SPEED
            self.fall_distance = 0.0
        elif self.is_sprinting and self.hunger > 2.0:
            speed = self.SPRINT_SPEED
        else:
            speed = self.WALK_SPEED

        self.vx = move_dx * speed
        self.vz = move_dz * speed

        # Vertical velocity (gravity / jumping / swimming)
        if self.in_water:
            if jump_pressed:
                self.vy = 3.8
            else:
                self.vy = max(-3.2, self.vy - 6.5 * dt)
        else:
            if jump_pressed and self.on_ground:
                self.vy = self.JUMP_VELOCITY
                self.on_ground = False
                # Small hunger cost for jumping
                if self.world.difficulty != "Peaceful":
                    self.hunger = max(0.0, self.hunger - 0.05)
            self.vy = max(-32.0, self.vy - self.GRAVITY * dt)

        # 1. Resolve X-axis movement
        new_x = self.x + self.vx * dt
        if not self._collides_aabb(new_x, self.y, self.z):
            self.x = new_x
        else:
            self.vx = 0.0

        # 2. Resolve Z-axis movement
        new_z = self.z + self.vz * dt
        if not self._collides_aabb(self.x, self.y, new_z):
            self.z = new_z
        else:
            self.vz = 0.0

        # 3. Resolve Y-axis movement
        dy = self.vy * dt
        new_y = self.y + dy
        if not self._collides_aabb(self.x, new_y, self.z):
            if dy < 0.0 and not self.in_water:
                self.fall_distance += abs(dy)
            self.y = new_y
            self.on_ground = False
        else:
            if self.vy < 0.0:
                # Landed on solid ground; snap feet cleanly onto top of supporting block
                self.y = float(math.floor(self.y + 0.05))
                while self._collides_aabb(self.x, self.y, self.z) and self.y < CHUNK_HEIGHT:
                    self.y += 0.05
                self.on_ground = True

                # Apply fall damage if fell > 4.0 blocks (Section 16)
                if self.fall_distance > 4.2 and not self.in_water and self.world.difficulty != "Peaceful":
                    dmg = (self.fall_distance - 3.8) * 1.6
                    self.take_damage(dmg, source="Fall", settings=settings)
                self.fall_distance = 0.0
            elif self.vy > 0.0:
                # Hit ceiling
                self.fall_distance = 0.0
            self.vy = 0.0

        # Guard against leaving world bounds vertically (Section 25)
        if self.y < -5.0:
            self.y = float(self.spawn_pos[1])
            self.vy = 0.0
            self.fall_distance = 0.0

        # Footstep audio
        horiz_speed = math.sqrt(self.vx * self.vx + self.vz * self.vz)
        if self.on_ground and horiz_speed > 0.5:
            self._step_sound_timer -= dt
            if self._step_sound_timer <= 0.0:
                self._step_sound_timer = 0.36 if self.is_sprinting else 0.48
                play_game_sound("step", settings)

        self.sync_camera()

    def update_raycast_and_selection(self) -> VoxelHit:
        """Raycast from camera eye to find targeted block and update selection box."""
        self.targeted_hit = self.world.raycast_voxel(
            self.get_eye_position(),
            self.get_look_direction(),
            max_dist=self.REACH_DISTANCE,
        )
        if self.selection_box is not None:
            try:
                if self.targeted_hit.hit:
                    bx, by, bz = self.targeted_hit.block_pos
                    self.selection_box.position = (bx + 0.5, by + 0.5, bz + 0.5)
                    self.selection_box.enabled = True
                else:
                    self.selection_box.enabled = False
            except Exception:
                pass

        # Reset mining timer if player looked at a different block
        if not self.targeted_hit.hit or self.targeted_hit.block_pos != self.mining_block_pos:
            self.mining_block_pos = self.targeted_hit.block_pos if self.targeted_hit.hit else None
            self.mining_timer = 0.0
            if self.targeted_hit.hit:
                self.mining_required_time = calculate_mining_time(
                    self.targeted_hit.block_id,
                    self.inventory.get_selected_item_key(),
                )
            else:
                self.mining_required_time = 1.0

        return self.targeted_hit

    @property
    def mining_progress(self) -> float:
        if not self.targeted_hit.hit or math.isinf(self.mining_required_time) or self.mining_required_time <= 0:
            return 0.0
        return min(1.0, max(0.0, self.mining_timer / self.mining_required_time))

    def mine_step(self, dt: float, settings=None) -> bool:
        """
        Advance block mining while left mouse button is held.
        Returns True when the targeted block finishes breaking.
        """
        if self.is_dead:
            return False
        self.update_raycast_and_selection()
        if not self.targeted_hit.hit:
            self.mining_timer = 0.0
            return False

        bid = self.targeted_hit.block_id
        bdef = get_block_by_id(bid)
        if bdef.unbreakable or bid == AIR or bid == WATER:
            self.mining_timer = 0.0
            return False

        held_key = self.inventory.get_selected_item_key()
        self.mining_required_time = calculate_mining_time(bid, held_key)
        self.mining_timer += float(dt)
        self.trigger_swing()

        if self.mining_timer >= self.mining_required_time:
            return self.break_targeted_block(settings=settings)
        return False

    def break_targeted_block(self, settings=None) -> bool:
        """
        Break the currently targeted block (if breakable), spawn particles,
        collect its dropped item into inventory, and apply tool durability wear.
        """
        if not self.targeted_hit.hit:
            self.update_raycast_and_selection()
        if not self.targeted_hit.hit:
            return False

        bx, by, bz = self.targeted_hit.block_pos
        bid = self.world.get_block(bx, by, bz)
        bdef = get_block_by_id(bid)
        if bdef.unbreakable or bid == AIR or bid == WATER:
            return False

        if not self.world.set_block(bx, by, bz, AIR):
            return False

        self.world.spawn_break_particles(bx, by, bz, bid)
        play_game_sound("dig", settings)

        if bdef.drop_item:
            self.inventory.add_item(bdef.drop_item, bdef.drop_count)

        # Reduce tool durability if holding a tool
        self.inventory.damage_selected_tool(1)
        self.mining_timer = 0.0
        self.mining_block_pos = None
        self.update_raycast_and_selection()
        self.update_held_visual()
        return True

    def place_selected_block(self, settings=None) -> Optional[str]:
        """
        Right-click action:
        - If targeting a Crafting Table or Furnace, returns 'crafting_table' or 'furnace' so UI opens it
          (unless sneaking/holding Shift).
        - If holding a food item and hungry, eats the food.
        - If holding a placeable block and targeting a valid block face not intersecting the player,
          places the block in the world and consumes 1 from hotbar.
        Returns status string: 'placed', 'ate', 'crafting_table', 'furnace', 'chest', or None.
        """
        if self.is_dead:
            return None

        self.update_raycast_and_selection()
        held_stack = self.inventory.get_selected_stack()
        held_def = held_stack.item_def if held_stack else None

        # Check block interaction first (Crafting Table, Furnace, Chest) when not holding Shift
        if self.targeted_hit.hit and not self.is_sprinting:
            t_bid = self.targeted_hit.block_id
            if t_bid == CRAFTING_TABLE:
                return "crafting_table"
            if t_bid == FURNACE:
                return "furnace"
            if t_bid == CHEST:
                return "chest"

        # Check if holding food
        if held_def is not None and held_def.category == "food":
            if self.eat_selected_food(settings=settings):
                return "ate"

        # Place block if holding a block item
        if held_def is None or held_def.block_id is None:
            return None

        if not self.targeted_hit.hit:
            return None

        px, py, pz = self.targeted_hit.place_pos
        if not (0 <= py < CHUNK_HEIGHT):
            return None

        # Cannot place in occupied solid voxel
        existing = self.world.get_block(px, py, pz)
        if existing != AIR and existing != WATER:
            return None

        # Cannot place solid block inside player's body (Section 8)
        new_bdef = get_block_by_id(held_def.block_id)
        if new_bdef.solid and self.block_intersects_player(px, py, pz):
            return None

        if self.world.set_block(px, py, pz, held_def.block_id):
            self.inventory.consume_selected(1)
            self.trigger_swing()
            play_game_sound("place", settings)
            self.update_raycast_and_selection()
            self.update_held_visual()
            return "placed"

        return None

    def eat_selected_food(self, settings=None) -> bool:
        """Consume 1 food item from the selected hotbar slot to restore hunger."""
        if self.is_dead:
            return False
        st = self.inventory.get_selected_stack()
        if st is None:
            return False
        idef = st.item_def
        if idef is None or idef.food_restore <= 0:
            return False
        if self.hunger >= self.max_hunger:
            return False

        self.hunger = min(self.max_hunger, self.hunger + float(idef.food_restore))
        self.inventory.consume_selected(1)
        self.trigger_swing()
        play_game_sound("eat", settings)
        self.update_held_visual()
        return True

    def take_damage(
        self,
        amount: float,
        source: str = "Damage",
        knockback_dir: Tuple[float, float] = (0.0, 0.0),
        settings=None,
    ) -> bool:
        """Reduce player health, apply knockback, and trigger death if health reaches 0."""
        if self.is_dead or amount <= 0.0:
            return False

        self.health = max(0.0, self.health - float(amount))
        self.hurt_flash_timer = 0.35
        self.vx += float(knockback_dir[0]) * 4.5
        self.vz += float(knockback_dir[1]) * 4.5
        if self.on_ground:
            self.vy = 3.2

        play_game_sound("hurt", settings)

        if self.health <= 0.0:
            self.health = 0.0
            self.is_dead = True
            self.death_reason = f"Slain by {source}" if source not in ("Fall", "Starvation") else source
            return True
        return False

    def respawn(self, keep_inventory: bool = True) -> None:
        """Respawn player at world spawn point with full health and hunger."""
        self.health = self.max_health
        self.hunger = self.max_hunger
        self.is_dead = False
        self.death_reason = ""
        self.hurt_flash_timer = 0.0
        self.fall_distance = 0.0
        self.vx = self.vy = self.vz = 0.0

        if not keep_inventory:
            self.inventory.clear()

        self.spawn_pos = self.world.find_spawn_position(int(self.spawn_pos[0]), int(self.spawn_pos[2]))
        self.position = self.spawn_pos
        self.update_held_visual()

    def update_survival(self, dt: float, settings=None) -> None:
        """Update hunger depletion, health regeneration, starvation, and animations."""
        if self.is_dead:
            return
        dt = min(0.1, max(0.0, float(dt)))

        if self.hurt_flash_timer > 0.0:
            self.hurt_flash_timer = max(0.0, self.hurt_flash_timer - dt)

        # Animate first-person held item swing
        if self._swing_anim > 0.0:
            self._swing_anim = max(0.0, self._swing_anim - dt * 4.5)
            if self.held_entity is not None:
                try:
                    ang = math.sin(self._swing_anim * math.pi) * 38.0
                    self.held_entity.rotation = (12 + ang, -28 - ang * 0.5, 8)
                except Exception:
                    pass

        self.update_held_visual()

        if self.world.difficulty == "Peaceful":
            # Peaceful mode slowly restores hunger & health
            self.hunger = min(self.max_hunger, self.hunger + dt * 0.5)
            self.health = min(self.max_health, self.health + dt * 0.5)
            return

        # 1. Passive & sprint hunger drain
        drain_rate = 0.045 if not self.is_sprinting else 0.14
        self.hunger = max(0.0, self.hunger - drain_rate * dt)

        # 2. Natural health regeneration when hunger >= 18
        if self.hunger >= 18.0 and self.health < self.max_health:
            self._regen_timer += dt
            if self._regen_timer >= 3.5:
                self._regen_timer = 0.0
                self.health = min(self.max_health, self.health + 1.0)
                self.hunger = max(0.0, self.hunger - 0.3)
        else:
            self._regen_timer = 0.0

        # 3. Starvation damage when hunger == 0
        if self.hunger <= 0.0:
            self._starve_timer += dt
            if self._starve_timer >= 3.5:
                self._starve_timer = 0.0
                self.take_damage(1.0, source="Starvation", settings=settings)
        else:
            self._starve_timer = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": [self.x, self.y, self.z],
            "spawn_pos": list(self.spawn_pos),
            "yaw": self.yaw,
            "pitch": self.pitch,
            "health": self.health,
            "hunger": self.hunger,
            "selected_slot": self.inventory.selected_slot,
            "inventory": self.inventory.to_list(),
        }

    def load_from_dict(self, data: Optional[Dict[str, Any]]) -> None:
        if not data or not isinstance(data, dict):
            return
        pos = data.get("position")
        if isinstance(pos, list) and len(pos) == 3:
            self.x, self.y, self.z = float(pos[0]), float(pos[1]), float(pos[2])
        spos = data.get("spawn_pos")
        if isinstance(spos, list) and len(spos) == 3:
            self.spawn_pos = (float(spos[0]), float(spos[1]), float(spos[2]))
        self.yaw = float(data.get("yaw", 0.0))
        self.pitch = float(data.get("pitch", 10.0))
        self.health = max(1.0, min(self.max_health, float(data.get("health", 20.0))))
        self.hunger = max(0.0, min(self.max_hunger, float(data.get("hunger", 20.0))))
        self.inventory.load_from_list(data.get("inventory", []))
        self.inventory.select_slot(int(data.get("selected_slot", 0)))
        self.sync_camera()
        self.update_held_visual()

    def cleanup(self) -> None:
        try:
            from ursina import destroy
            if self.selection_box is not None:
                destroy(self.selection_box)
                self.selection_box = None
            if self.held_entity is not None:
                destroy(self.held_entity)
                self.held_entity = None
        except Exception:
            pass
