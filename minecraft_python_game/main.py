#!/usr/bin/env python3
"""
PyCraft - A Complete Minecraft-Inspired Voxel Survival Sandbox Game in Python.
Built with Ursina Engine / Panda3D, NumPy, and Pillow.

Controls:
  W / S / A / D   : Move Forward / Backward / Left / Right
  Space           : Jump / Swim Up
  Shift           : Sprint
  Mouse           : Look Around (First-Person Camera)
  Left Mouse      : Mine Block (hold) / Attack Mob
  Right Mouse     : Place Block / Open Crafting Table or Furnace / Eat Food
  1 - 9           : Select Hotbar Slot
  Mouse Wheel     : Cycle Hotbar Selection
  E               : Open / Close Inventory & Crafting
  F               : Eat Selected Food
  Esc             : Pause Menu / Back
"""

import math
import os
import sys
from typing import Optional

from game.assets_gen import ensure_all_assets
from game.combat import CombatSystem
from game.crafting import CraftingSystem
from game.furnace import FurnaceSystem
from game.mobs import MobManager
from game.player import Player
from game.save import SaveManager
from game.settings import GameSettings
from game.ui import GameUI
from game.world import World


class GameController:
    """Central game state and loop coordinator."""

    def __init__(self):
        ensure_all_assets()
        self.settings = GameSettings.load()
        self.save_manager = SaveManager()
        self.crafting = CraftingSystem()
        self.furnace = FurnaceSystem()
        self.combat = CombatSystem()

        self.world: Optional[World] = None
        self.player: Optional[Player] = None
        self.mob_manager: Optional[MobManager] = None
        self.ui: Optional[GameUI] = None

        self._autosave_timer: float = 0.0

    def init_ui(self) -> None:
        self.settings.apply_to_engine()
        self.ui = GameUI(self)

    def _cleanup_active_session(self) -> None:
        if self.mob_manager is not None:
            self.mob_manager.cleanup()
            self.mob_manager = None
        if self.player is not None:
            self.player.cleanup()
            self.player = None
        if self.world is not None:
            self.world.cleanup()
            self.world = None
        self.furnace = FurnaceSystem()

    def start_new_world(
        self,
        world_name: str = "Survival World",
        seed: str = "PyCraft2026",
        difficulty: str = "Normal",
    ) -> None:
        """Create and initialize a brand-new procedural voxel world."""
        self._cleanup_active_session()

        self.world = World(seed=seed, world_name=world_name, difficulty=difficulty)
        spawn_pos = self.world.find_spawn_position(8, 8)
        self.world.update_chunks(spawn_pos[0], spawn_pos[2], render_distance=self.settings.render_distance, immediate=True)
        # Re-verify spawn height after chunks are built
        spawn_pos = self.world.find_spawn_position(int(spawn_pos[0]), int(spawn_pos[2]))

        self.player = Player(self.world, spawn_pos=spawn_pos)
        # Starter survival kit in hotbar so player can immediately mine, fight, build, or eat
        self.player.inventory.add_item("wooden_pickaxe", 1)
        self.player.inventory.add_item("wooden_sword", 1)
        self.player.inventory.add_item("torch", 8)
        self.player.inventory.add_item("apple", 4)
        self.player.update_held_visual()
        self.player.update_raycast_and_selection()

        self.mob_manager = MobManager(self.world)
        self.mob_manager.spawn_initial_mobs(spawn_pos)

        self.save_current_world()
        if self.ui is not None:
            self.ui.show_hud_only()
            self.ui.show_notification(f"Welcome to {self.world.world_name} (Seed: {self.world.seed})")

    def load_saved_world(self, world_name_or_slug: str) -> bool:
        """Load an existing saved world from `saves/`."""
        data = self.save_manager.load_raw_data(world_name_or_slug)
        if data is None:
            if self.ui is not None:
                self.ui.show_notification("Could not load save file (missing or corrupted).")
            return False

        self._cleanup_active_session()

        seed = data.get("seed", "PyCraft2026")
        w_name = data.get("world_name", world_name_or_slug)
        diff = data.get("difficulty", "Normal")

        self.world = World(seed=seed, world_name=w_name, difficulty=diff)
        self.player = Player(self.world, spawn_pos=(8.5, 25.0, 8.5))
        self.save_manager.apply_loaded_data(data, self.world, self.player, self.furnace)

        px, py, pz = self.player.position
        self.world.update_chunks(px, pz, render_distance=self.settings.render_distance, immediate=True)
        self.player.sync_camera()
        self.player.update_held_visual()
        self.player.update_raycast_and_selection()

        self.mob_manager = MobManager(self.world)
        self.mob_manager.spawn_initial_mobs(self.player.position)

        if self.ui is not None:
            self.ui.show_hud_only()
            self.ui.show_notification(f"Loaded World: {self.world.world_name}")
        return True

    def save_current_world(self) -> bool:
        if self.world is None or self.player is None:
            return False
        return self.save_manager.save_game(self.world, self.player, self.furnace)

    def respawn_player(self) -> None:
        if self.player is None:
            return
        self.player.respawn(keep_inventory=self.settings.keep_inventory)
        if self.ui is not None:
            self.ui.show_hud_only()
            self.ui.show_notification("Respawned!")

    def return_to_main_menu(self) -> None:
        self.save_current_world()
        self._cleanup_active_session()
        if self.ui is not None:
            self.ui.show_main_menu()

    def quit_application(self) -> None:
        self.save_current_world()
        self._cleanup_active_session()
        try:
            from ursina import application
            application.quit()
        except Exception:
            sys.exit(0)

    def handle_input(self, key: str) -> None:
        """Process discrete keyboard and mouse events."""
        if self.ui is None:
            return

        # Escape key navigation
        if key == "escape":
            if self.ui.active_screen == "hud":
                self.ui.show_pause_menu()
            elif self.ui.active_screen in ("inventory", "pause"):
                self.ui.show_hud_only()
            elif self.ui.active_screen in ("new_world", "load_world", "settings"):
                if self.world is not None and self.ui.previous_screen == "pause":
                    self.ui.show_pause_menu()
                else:
                    self.ui.show_main_menu()
            return

        # Inventory toggle [E]
        if key == "e":
            if self.ui.active_screen == "hud":
                self.ui.show_inventory_screen("crafting")
                return
            elif self.ui.active_screen == "inventory":
                self.ui.show_hud_only()
                return

        # Only process gameplay hotkeys when in active HUD view
        if self.ui.active_screen != "hud" or self.player is None or self.player.is_dead:
            return

        # Hotbar number keys 1-9
        if key in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
            self.player.inventory.select_slot(int(key) - 1)
            self.player.update_held_visual()
            return

        # Mouse wheel hotbar selection
        if key == "scroll up":
            self.player.inventory.scroll_hotbar(-1)
            self.player.update_held_visual()
            return
        if key == "scroll down":
            self.player.inventory.scroll_hotbar(1)
            self.player.update_held_visual()
            return

        # Eat food shortcut [F]
        if key == "f":
            if self.player.eat_selected_food(settings=self.settings):
                self.ui.show_notification("Ate food (+Hunger)")
            return

        # Left mouse click: check for mob melee attack first, otherwise start/step mining
        if key == "left mouse down":
            self.player.trigger_swing()
            if self.mob_manager is not None:
                target_mob = self.combat.find_target_mob(
                    self.player.get_eye_position(),
                    self.player.get_look_direction(),
                    self.mob_manager.mobs,
                )
                if target_mob is not None:
                    hit, dmg, killed = self.combat.perform_player_attack(
                        self.player,
                        self.mob_manager.mobs,
                        target_mob=target_mob,
                        settings=self.settings,
                    )
                    if hit:
                        msg = f"Defeated {target_mob.name}!" if killed else f"Hit {target_mob.name} (-{dmg:.0f} HP)"
                        self.ui.show_notification(msg, duration=1.5)
                        self.player.update_held_visual()
                    return

        # Right mouse click: interact with block (Crafting Table / Furnace), eat food, or place block
        if key == "right mouse down":
            res = self.player.place_selected_block(settings=self.settings)
            if res == "crafting_table":
                self.ui.show_inventory_screen("crafting")
            elif res == "furnace":
                self.ui.show_inventory_screen("furnace")
            elif res == "chest":
                self.ui.show_inventory_screen("crafting")
            elif res == "ate":
                self.ui.show_notification("Ate food (+Hunger)", duration=1.5)

    def update(self, dt: float) -> None:
        """Per-frame update loop."""
        dt = min(0.1, max(0.0, float(dt)))

        # Always tick active furnace even while in inventory screen
        if self.world is not None:
            self.furnace.update(dt)

        if self.ui is None:
            return

        # Check player death transition
        if self.player is not None and self.player.is_dead and self.ui.active_screen != "death":
            self.ui.show_death_screen()
            return

        # Only run active 3D movement/camera/mining when HUD is active
        if self.ui.active_screen == "hud" and self.world is not None and self.player is not None and not self.player.is_dead:
            try:
                from ursina import held_keys, mouse

                # 1. Smooth First-Person Mouse Look
                sens = self.settings.mouse_sensitivity
                mv_x = float(getattr(mouse, "velocity", (0, 0))[0])
                mv_y = float(getattr(mouse, "velocity", (0, 0))[1])
                if abs(mv_x) > 1e-6 or abs(mv_y) > 1e-6:
                    self.player.rotate_view(mv_x * sens, -mv_y * sens)

                # 2. WASD + Sprint + Jump movement
                fwd = float(held_keys["w"]) - float(held_keys["s"])
                strafe = float(held_keys["d"]) - float(held_keys["a"])
                self.player.is_sprinting = bool(held_keys["shift"] or held_keys["left shift"]) and fwd > 0

                yaw_rad = math.radians(self.player.yaw)
                sin_y = math.sin(yaw_rad)
                cos_y = math.cos(yaw_rad)

                move_dx = fwd * sin_y + strafe * cos_y
                move_dz = fwd * cos_y - strafe * sin_y
                mag = math.sqrt(move_dx * move_dx + move_dz * move_dz)
                if mag > 1.0:
                    move_dx /= mag
                    move_dz /= mag

                jump_held = bool(held_keys["space"])
                self.player.move_and_collide(move_dx, move_dz, dt, jump_pressed=jump_held, settings=self.settings)

                # 3. Raycast block selection & continuous Left-Mouse block mining
                self.player.update_raycast_and_selection()
                if bool(held_keys["left mouse"]):
                    # Only mine if not currently aiming at a mob right in front of the player
                    mob_in_front = None
                    if self.mob_manager is not None:
                        mob_in_front = self.combat.find_target_mob(
                            self.player.get_eye_position(),
                            self.player.get_look_direction(),
                            self.mob_manager.mobs,
                        )
                    if mob_in_front is None:
                        self.player.mine_step(dt, settings=self.settings)
                    elif self.combat.can_attack:
                        self.combat.perform_player_attack(
                            self.player,
                            self.mob_manager.mobs,
                            target_mob=mob_in_front,
                            settings=self.settings,
                        )
                else:
                    self.player.mining_timer = 0.0
            except Exception:
                pass

            # 4. Update Combat, Survival, Mobs, World, and HUD
            self.combat.update(dt)
            self.player.update_survival(dt, settings=self.settings)
            if self.mob_manager is not None:
                self.mob_manager.update(dt, self.player, settings=self.settings)
            self.world.update(dt, self.player.position, render_distance=self.settings.render_distance)
            self.ui.update_hud(dt)

            # Periodic autosave every 60 seconds
            self._autosave_timer += dt
            if self._autosave_timer >= 60.0:
                self._autosave_timer = 0.0
                self.save_current_world()


def create_ursina_app(headless: bool = False):
    """Initialize the Ursina engine, automatically detecting headless environments."""
    from panda3d.core import loadPrcFileData

    is_linux_headless = (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
    )
    use_headless = headless or is_linux_headless or ("--headless" in sys.argv)

    if use_headless:
        loadPrcFileData("", "window-type none")
        loadPrcFileData("", "audio-library-name null")

    from ursina import Ursina

    if use_headless:
        app = Ursina(window_type="none")
    else:
        app = Ursina(
            title="PyCraft - Voxel Survival Sandbox",
            borderless=False,
            size=(1280, 720),
            development_mode=False,
        )
    return app


# Global controller instance wired to Ursina's top-level update() and input() hooks
GAME_CONTROLLER: Optional[GameController] = None


def update():
    if GAME_CONTROLLER is not None:
        from ursina import time as utime
        GAME_CONTROLLER.update(getattr(utime, "dt", 0.016))


def input(key):
    if GAME_CONTROLLER is not None:
        GAME_CONTROLLER.handle_input(str(key))


def main():
    global GAME_CONTROLLER
    app = create_ursina_app()
    GAME_CONTROLLER = GameController()
    GAME_CONTROLLER.init_ui()
    app.run()


if __name__ == "__main__":
    main()
