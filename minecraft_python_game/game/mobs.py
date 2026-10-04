"""
AI Mobs system: Passive (Pig, Cow) and Hostile (Zombie, Skeleton) mobs.
Handles 3D blocky mob models, wandering/chase AI, voxel collision, health,
damage, knockback, item drops, and day/night spawning rules.
"""

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from game.assets_gen import get_mob_texture, play_game_sound
from game.combat import DIFFICULTY_DAMAGE_MULTIPLIER
from game.mob_models import animate_rig, build_mob_rig
from game.terrain import CHUNK_HEIGHT, SEA_LEVEL


@dataclass(frozen=True)
class MobConfig:
    mob_type: str
    name: str
    hostile: bool
    max_health: float
    move_speed: float
    detect_range: float
    attack_range: float
    attack_damage: float
    attack_cooldown: float
    drops: List[Tuple[str, int, int]]  # (item_key, min_count, max_count)
    body_color: Tuple[float, float, float]
    head_color: Tuple[float, float, float]
    limb_color: Tuple[float, float, float]


MOB_CONFIGS: Dict[str, MobConfig] = {
    "pig": MobConfig(
        mob_type="pig",
        name="Pig",
        hostile=False,
        max_health=10.0,
        move_speed=2.1,
        detect_range=10.0,
        attack_range=0.0,
        attack_damage=0.0,
        attack_cooldown=1.5,
        drops=[("raw_pork", 1, 2)],
        body_color=(0.95, 0.65, 0.68),
        head_color=(0.98, 0.70, 0.73),
        limb_color=(0.88, 0.55, 0.58),
    ),
    "cow": MobConfig(
        mob_type="cow",
        name="Cow",
        hostile=False,
        max_health=12.0,
        move_speed=2.0,
        detect_range=10.0,
        attack_range=0.0,
        attack_damage=0.0,
        attack_cooldown=1.5,
        drops=[("raw_beef", 1, 2)],
        body_color=(0.42, 0.28, 0.18),
        head_color=(0.48, 0.34, 0.22),
        limb_color=(0.35, 0.22, 0.14),
    ),
    "zombie": MobConfig(
        mob_type="zombie",
        name="Zombie",
        hostile=True,
        max_health=20.0,
        move_speed=2.7,
        detect_range=18.0,
        attack_range=1.95,
        attack_damage=3.0,
        attack_cooldown=1.15,
        drops=[("rotten_flesh", 1, 2), ("iron_ingot", 0, 1)],
        body_color=(0.18, 0.48, 0.62),
        head_color=(0.34, 0.62, 0.32),
        limb_color=(0.24, 0.26, 0.52),
    ),
    "skeleton": MobConfig(
        mob_type="skeleton",
        name="Skeleton",
        hostile=True,
        max_health=16.0,
        move_speed=2.85,
        detect_range=20.0,
        attack_range=4.2,
        attack_damage=3.0,
        attack_cooldown=1.45,
        drops=[("bone", 1, 2), ("coal", 0, 1)],
        body_color=(0.86, 0.86, 0.82),
        head_color=(0.92, 0.92, 0.88),
        limb_color=(0.78, 0.78, 0.74),
    ),
}


class Mob:
    """Single AI Mob instance with 3D articulated voxel parts, health, physics, and AI."""

    def __init__(self, mob_type: str, position: Tuple[float, float, float], world):
        self.config: MobConfig = MOB_CONFIGS.get(mob_type, MOB_CONFIGS["pig"])
        self.mob_type = self.config.mob_type
        self.name = self.config.name
        self.hostile = self.config.hostile
        self.world = world

        self.x, self.y, self.z = float(position[0]), float(position[1]), float(position[2])
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.vz: float = 0.0
        self.yaw: float = random.uniform(0.0, 360.0)

        self.max_health: float = self.config.max_health
        self.health: float = self.max_health
        self.dead: bool = False
        self.hit_radius: float = 0.85

        # AI timers
        self.wander_timer: float = random.uniform(1.0, 3.5)
        self.wander_dir: Tuple[float, float] = (0.0, 0.0)
        self.flee_timer: float = 0.0
        self.attack_timer: float = 0.0
        self.hurt_flash_timer: float = 0.0
        self.anim_time: float = random.uniform(0.0, 10.0)
        self.swing_phase: float = 0.0
        self.move_blend: float = 0.0
        self.rig = None

        # Ursina visual entities
        self.root_entity = None
        self.part_entities: List[object] = []
        self.hp_bar_bg = None
        self.hp_bar_fg = None
        self._build_visual_model()

    @property
    def position(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.z)

    @position.setter
    def position(self, val: Tuple[float, float, float]) -> None:
        self.x, self.y, self.z = float(val[0]), float(val[1]), float(val[2])
        self._sync_visuals()

    def _build_visual_model(self) -> None:
        """Build the textured, articulated box model plus an overhead health bar."""
        try:
            from ursina import Entity, color

            self.root_entity = Entity(position=(self.x, self.y, self.z), rotation_y=self.yaw)
            self.rig = build_mob_rig(self.mob_type, self.root_entity, get_mob_texture(self.mob_type))
            self.part_entities = list(self.rig.meshes)
            bar_y = self.rig.bar_height

            # Floating overhead health indicator (billboard so it always faces the camera)
            self.hp_bar_bg = Entity(
                parent=self.root_entity,
                model="cube",
                scale=(0.72, 0.07, 0.04),
                position=(0, bar_y, 0),
                color=color.rgb(0.10, 0.10, 0.12),
            )
            self.hp_bar_fg = Entity(
                parent=self.root_entity,
                model="cube",
                scale=(0.70, 0.06, 0.05),
                position=(0, bar_y, 0),
                color=color.rgb(0.92, 0.22, 0.22) if self.hostile else color.rgb(0.25, 0.85, 0.35),
            )
        except Exception as exc:
            print(f"[Mobs] Could not build model for {self.mob_type}: {exc}")

    def _sync_visuals(self) -> None:
        if self.root_entity is not None:
            try:
                self.root_entity.position = (self.x, self.y, self.z)
                self.root_entity.rotation_y = self.yaw
                if self.hp_bar_fg is not None:
                    frac = max(0.0, min(1.0, self.health / max(1.0, self.max_health)))
                    self.hp_bar_fg.scale_x = 0.70 * frac
                from ursina import camera
                cam_yaw = camera.world_rotation_y
                if self.hp_bar_bg is not None:
                    self.hp_bar_bg.world_rotation_y = cam_yaw
                if self.hp_bar_fg is not None:
                    self.hp_bar_fg.world_rotation_y = cam_yaw
            except Exception:
                pass

    def take_damage(
        self,
        amount: float,
        knockback_dir: Tuple[float, float] = (0.0, 0.0),
        knockback_strength: float = 6.0,
        attacker_player=None,
        settings=None,
    ) -> bool:
        """Apply damage and knockback to this mob. Returns True if the mob died."""
        if self.dead:
            return False

        self.health = max(0.0, self.health - float(amount))
        self.hurt_flash_timer = 0.22

        # Apply knockback impulse
        self.vx = float(knockback_dir[0]) * knockback_strength
        self.vz = float(knockback_dir[1]) * knockback_strength
        self.vy = 4.2

        # Passive mobs panic-flee when hit
        if not self.hostile:
            self.flee_timer = 3.5
            self.wander_dir = (float(knockback_dir[0]), float(knockback_dir[1]))

        play_game_sound("hurt", settings)
        self._set_flash_color(True)
        self._sync_visuals()

        if self.health <= 0.0:
            self.die(attacker_player)
            return True
        return False

    def _set_flash_color(self, flashing: bool) -> None:
        """Tint the skin red while hurt, then restore the original skin colours."""
        if self.rig is None:
            return
        try:
            self.rig.tint((1.0, 0.35, 0.35, 1.0) if flashing else (1.0, 1.0, 1.0, 1.0))
        except Exception:
            pass

    def die(self, attacker_player=None) -> None:
        """Kill this mob, drop its loot items into the player's inventory, and destroy its entity."""
        if self.dead:
            return
        self.dead = True

        # Award drops to player if present
        if attacker_player is not None and hasattr(attacker_player, "inventory"):
            for item_key, min_c, max_c in self.config.drops:
                cnt = random.randint(min_c, max_c)
                if cnt > 0:
                    attacker_player.inventory.add_item(item_key, cnt)

        self.destroy_visuals()

    def destroy_visuals(self) -> None:
        try:
            from ursina import destroy
            if self.root_entity is not None:
                destroy(self.root_entity)
                self.root_entity = None
            self.part_entities.clear()
            self.rig = None
        except Exception:
            self.root_entity = None

    def update(self, dt: float, player, settings=None) -> None:
        """Update AI decision-making, movement, voxel collision, and melee attacks."""
        if self.dead:
            return
        dt = min(0.05, max(0.0, float(dt)))

        # Hurt flash recovery
        if self.hurt_flash_timer > 0.0:
            self.hurt_flash_timer -= dt
            if self.hurt_flash_timer <= 0.0:
                self._set_flash_color(False)

        if self.attack_timer > 0.0:
            self.attack_timer = max(0.0, self.attack_timer - dt)

        px, py, pz = player.position
        dx = px - self.x
        dy = py - self.y
        dz = pz - self.z
        horiz_dist = math.sqrt(dx * dx + dz * dz)
        full_dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        target_vx = 0.0
        target_vz = 0.0
        speed = self.config.move_speed

        if self.hostile and self.world.difficulty != "Peaceful" and not getattr(player, "is_dead", False):
            # Hostile AI: detect and pursue player
            if full_dist <= self.config.detect_range and horiz_dist > 0.05:
                dir_x = dx / horiz_dist
                dir_z = dz / horiz_dist
                self.yaw = math.degrees(math.atan2(dir_x, dir_z))

                if horiz_dist > max(1.1, self.config.attack_range * 0.75):
                    target_vx = dir_x * speed
                    target_vz = dir_z * speed

                # Attack player when in range
                if full_dist <= self.config.attack_range and self.attack_timer <= 0.0:
                    self.attack_timer = self.config.attack_cooldown
                    mult = DIFFICULTY_DAMAGE_MULTIPLIER.get(self.world.difficulty, 1.0)
                    dmg = self.config.attack_damage * mult
                    if dmg > 0.0:
                        player.take_damage(dmg, source=self.name, knockback_dir=(dir_x, dir_z), settings=settings)
            else:
                target_vx, target_vz = self._update_wander(dt, speed * 0.55)
        else:
            # Passive AI: flee if recently hit, otherwise wander peacefully
            if self.flee_timer > 0.0:
                self.flee_timer -= dt
                target_vx = self.wander_dir[0] * speed * 1.45
                target_vz = self.wander_dir[1] * speed * 1.45
                if abs(target_vx) + abs(target_vz) > 0.05:
                    self.yaw = math.degrees(math.atan2(target_vx, target_vz))
            else:
                target_vx, target_vz = self._update_wander(dt, speed * 0.65)

        # Blend knockback velocity with target movement velocity
        decay = min(1.0, dt * 8.0)
        self.vx = self.vx * (1.0 - decay) + target_vx * decay
        self.vz = self.vz * (1.0 - decay) + target_vz * decay

        # Gravity & water buoyancy
        bx, by, bz = math.floor(self.x), math.floor(self.y), math.floor(self.z)
        if self.world.is_water(bx, by, bz):
            self.vy = min(2.5, self.vy + 12.0 * dt)
        else:
            self.vy = max(-24.0, self.vy - 22.0 * dt)

        # Apply vertical movement and floor collision
        new_y = self.y + self.vy * dt
        floor_y = math.floor(new_y)
        if self.vy <= 0.0 and self.world.is_solid(bx, floor_y, bz):
            self.y = float(floor_y + 1)
            self.vy = 0.0
            on_ground = True
        else:
            self.y = max(1.0, new_y)
            on_ground = False

        # Apply horizontal movement with obstacle jump/step-up
        nx = self.x + self.vx * dt
        nz = self.z + self.vz * dt
        foot_y = math.floor(self.y + 0.05)

        # X axis check
        if not self.world.is_solid(math.floor(nx), foot_y, math.floor(self.z)) and not self.world.is_solid(math.floor(nx), foot_y + 1, math.floor(self.z)):
            self.x = nx
        elif on_ground and not self.world.is_solid(math.floor(nx), foot_y + 1, math.floor(self.z)) and not self.world.is_solid(math.floor(nx), foot_y + 2, math.floor(self.z)):
            # Jump over 1-block obstacle
            self.vy = 6.8

        # Z axis check
        if not self.world.is_solid(math.floor(self.x), foot_y, math.floor(nz)) and not self.world.is_solid(math.floor(self.x), foot_y + 1, math.floor(nz)):
            self.z = nz
        elif on_ground and not self.world.is_solid(math.floor(self.x), foot_y + 1, math.floor(nz)) and not self.world.is_solid(math.floor(self.x), foot_y + 2, math.floor(nz)):
            self.vy = 6.8

        # Limb swing / head animation
        move_mag = math.sqrt(self.vx * self.vx + self.vz * self.vz)
        self.anim_time += dt * (1.0 + move_mag * 3.2)
        self.swing_phase += dt * move_mag * 3.6
        moving = min(1.0, move_mag / 1.8)
        self.move_blend += (moving - self.move_blend) * min(1.0, dt * 8.0)
        if self.rig is not None:
            try:
                aggressive = self.hostile and full_dist <= self.config.detect_range
                animate_rig(self.rig, self.swing_phase, self.move_blend, self.anim_time, aggressive)
            except Exception:
                pass

        self._sync_visuals()

    def _update_wander(self, dt: float, speed: float) -> Tuple[float, float]:
        self.wander_timer -= dt
        if self.wander_timer <= 0.0:
            self.wander_timer = random.uniform(2.0, 4.5)
            if random.random() < 0.45:
                self.wander_dir = (0.0, 0.0)
            else:
                ang = random.uniform(0.0, 2.0 * math.pi)
                self.wander_dir = (math.sin(ang), math.cos(ang))
                self.yaw = math.degrees(ang)
        return (self.wander_dir[0] * speed, self.wander_dir[1] * speed)


class MobManager:
    """Manages active mobs in the world, spawning, despawning, and updates."""

    MAX_MOBS = 12
    DESPAWN_DISTANCE = 46.0

    def __init__(self, world):
        self.world = world
        self.mobs: List[Mob] = []
        self.spawn_timer: float = 2.0

    def spawn_mob(self, mob_type: str, position: Tuple[float, float, float]) -> Mob:
        mob = Mob(mob_type=mob_type, position=position, world=self.world)
        self.mobs.append(mob)
        return mob

    def spawn_initial_mobs(self, player_pos: Tuple[float, float, float]) -> None:
        """Spawn a balanced initial group of passive and hostile mobs around the spawn area."""
        px, _, pz = player_pos
        initial_types = ["pig", "cow", "pig", "cow"]
        if self.world.difficulty != "Peaceful":
            initial_types.extend(["zombie", "skeleton"])

        for idx, mtype in enumerate(initial_types):
            ang = (idx / len(initial_types)) * 2.0 * math.pi + 0.4
            dist = 9.0 if not MOB_CONFIGS[mtype].hostile else 15.0
            sx = int(round(px + math.cos(ang) * dist))
            sz = int(round(pz + math.sin(ang) * dist))
            pos = self._find_surface_pos(sx, sz)
            if pos is not None:
                self.spawn_mob(mtype, pos)

    def _find_surface_pos(self, wx: int, wz: int) -> Optional[Tuple[float, float, float]]:
        _, sy = self.world.terrain.get_biome_and_height(wx, wz)
        if sy <= SEA_LEVEL:
            return None
        for y in range(CHUNK_HEIGHT - 2, 1, -1):
            if self.world.is_solid(wx, y, wz):
                return (float(wx) + 0.5, float(y) + 1.02, float(wz) + 0.5)
        return (float(wx) + 0.5, float(sy) + 1.02, float(wz) + 0.5)

    def update(self, dt: float, player, settings=None) -> None:
        dt = min(0.1, max(0.0, float(dt)))
        px, py, pz = player.position

        # If Peaceful difficulty, remove hostile mobs
        if self.world.difficulty == "Peaceful":
            for m in self.mobs:
                if m.hostile and not m.dead:
                    m.destroy_visuals()
                    m.dead = True

        # Update living mobs and despawn distant/dead ones
        alive: List[Mob] = []
        for mob in self.mobs:
            if mob.dead:
                mob.destroy_visuals()
                continue
            dx = mob.x - px
            dz = mob.z - pz
            if dx * dx + dz * dz > self.DESPAWN_DISTANCE ** 2:
                mob.destroy_visuals()
                continue
            mob.update(dt, player, settings=settings)
            if not mob.dead:
                alive.append(mob)
        self.mobs = alive

        # Periodic spawning around player
        self.spawn_timer -= dt
        if self.spawn_timer <= 0.0:
            self.spawn_timer = 4.0 if self.world.is_night else 6.5
            if len(self.mobs) < self.MAX_MOBS:
                ang = random.uniform(0.0, 2.0 * math.pi)
                dist = random.uniform(12.0, 24.0)
                sx = int(round(px + math.cos(ang) * dist))
                sz = int(round(pz + math.sin(ang) * dist))
                pos = self._find_surface_pos(sx, sz)
                if pos is not None:
                    if self.world.difficulty == "Peaceful":
                        mtype = random.choice(["pig", "cow"])
                    elif self.world.is_night:
                        # Hostile mobs are much more common at night (Section 17)
                        mtype = random.choice(["zombie", "skeleton", "zombie", "skeleton", "pig"])
                    else:
                        mtype = random.choice(["pig", "cow", "pig", "cow", "zombie", "skeleton"])
                    self.spawn_mob(mtype, pos)

    def cleanup(self) -> None:
        for mob in self.mobs:
            mob.destroy_visuals()
        self.mobs.clear()
