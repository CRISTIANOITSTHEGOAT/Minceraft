"""
Melee combat system: handles attack cooldowns, weapon damage calculation,
ray/cone hit detection against mobs, knockback impulses, and difficulty scaling.
"""

import math
from typing import List, Optional, Tuple

from game.assets_gen import play_game_sound
from game.blocks import get_attack_damage

DIFFICULTY_DAMAGE_MULTIPLIER = {
    "Peaceful": 0.0,
    "Easy": 0.65,
    "Normal": 1.0,
    "Hard": 1.5,
}


class CombatSystem:
    """Manages player melee attacks, cooldowns, hit detection, and knockback."""

    ATTACK_COOLDOWN: float = 0.40
    ATTACK_RANGE: float = 4.0

    def __init__(self):
        self.cooldown_timer: float = 0.0

    def update(self, dt: float) -> None:
        if self.cooldown_timer > 0.0:
            self.cooldown_timer = max(0.0, self.cooldown_timer - float(dt))

    @property
    def can_attack(self) -> bool:
        return self.cooldown_timer <= 0.0

    def find_target_mob(
        self,
        origin: Tuple[float, float, float],
        direction: Tuple[float, float, float],
        mobs: List[object],
        max_range: float = ATTACK_RANGE,
    ) -> Optional[object]:
        """
        Find the closest living mob within `max_range` intersected by the player's aim ray/cone.
        """
        ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
        dx, dy, dz = float(direction[0]), float(direction[1]), float(direction[2])
        d_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        if d_len < 1e-8:
            return None
        dx, dy, dz = dx / d_len, dy / d_len, dz / d_len

        best_mob = None
        best_dist = max_range + 1.0

        for mob in mobs:
            if getattr(mob, "dead", False):
                continue
            mx, my, mz = mob.position
            # Aim at vertical center of mob body (my + 0.75)
            cy = my + 0.75
            vx = mx - ox
            vy = cy - oy
            vz = mz - oz
            dist = math.sqrt(vx * vx + vy * vy + vz * vz)
            if dist > max_range or dist < 1e-5:
                continue

            # Projection along look vector
            proj = vx * dx + vy * dy + vz * dz
            if proj < -0.2:
                continue

            # Perpendicular distance from ray to mob center
            perp_sq = max(0.0, (vx * vx + vy * vy + vz * vz) - proj * proj)
            perp_dist = math.sqrt(perp_sq)
            hit_radius = getattr(mob, "hit_radius", 0.85)
            if perp_dist <= hit_radius and dist < best_dist:
                best_dist = dist
                best_mob = mob

        return best_mob

    def perform_player_attack(
        self,
        player,
        mobs: List[object],
        target_mob: Optional[object] = None,
        settings=None,
    ) -> Tuple[bool, float, bool]:
        """
        Execute a melee attack from `player`.
        Returns `(did_hit_mob, damage_dealt, mob_killed)`.
        """
        if not self.can_attack:
            return (False, 0.0, False)

        self.cooldown_timer = self.ATTACK_COOLDOWN
        held_key = player.inventory.get_selected_item_key()
        damage = get_attack_damage(held_key)

        if target_mob is None:
            eye_pos = player.get_eye_position()
            look_dir = player.get_look_direction()
            target_mob = self.find_target_mob(eye_pos, look_dir, mobs, max_range=self.ATTACK_RANGE)

        play_game_sound("swing", settings)

        if target_mob is None or getattr(target_mob, "dead", False):
            return (False, 0.0, False)

        # Compute knockback direction from player to mob
        px, _, pz = player.position
        mx, _, mz = target_mob.position
        kx = mx - px
        kz = mz - pz
        k_len = math.sqrt(kx * kx + kz * kz)
        if k_len > 1e-5:
            kx, kz = kx / k_len, kz / k_len
        else:
            look = player.get_look_direction()
            kx, kz = look[0], look[2]

        killed = target_mob.take_damage(
            amount=damage,
            knockback_dir=(kx, kz),
            knockback_strength=6.5,
            attacker_player=player,
            settings=settings,
        )

        # Reduce weapon/tool durability on hit
        player.inventory.damage_selected_tool(1)
        return (True, damage, killed)
