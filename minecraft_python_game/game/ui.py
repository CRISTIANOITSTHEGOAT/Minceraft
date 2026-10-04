"""
Complete UI & HUD Manager for PyCraft:
Includes Main Menu, New World Menu, Load/Delete World Menu, Settings Menu,
Pause Menu, Inventory/Crafting/Furnace Screen, Death Screen, and In-Game HUD.
"""

import random
from typing import Callable, Dict, List, Optional

from game.assets_gen import get_item_icon_texture, play_game_sound
from game.blocks import get_block_by_id, get_item_def
from game.furnace import SMELT_RECIPES
from game.inventory import HOTBAR_SIZE, TOTAL_SLOTS


class GameUI:
    """Manages all Ursina UI screens, menus, modals, and the in-game HUD."""

    def __init__(self, controller):
        self.ctrl = controller
        self.active_screen: str = "main_menu"  # 'main_menu', 'new_world', 'load_world', 'settings', 'hud', 'inventory', 'pause', 'death'
        self.previous_screen: str = "main_menu"
        self.inv_tab: str = "crafting"  # 'crafting' or 'furnace'
        self.recipe_page: int = 0

        # New world creation form state
        self.new_world_name: str = "Survival World"
        self.new_world_seed: str = "PyCraft2026"
        self.new_world_difficulty: str = "Normal"
        self._world_name_presets = ["Survival World", "Explorer World", "Mountain Realm", "Cavern Frontier", "Island Odyssey"]
        self._name_preset_idx = 0

        # Root UI containers
        self.hud_root = None
        self.screen_root = None

        # HUD element references
        self.crosshair_h = None
        self.crosshair_v = None
        self.mining_bar_bg = None
        self.mining_bar_fg = None
        self.info_text = None
        self.hp_bar_fg = None
        self.hp_text = None
        self.hunger_bar_fg = None
        self.hunger_text = None
        self.held_label = None
        self.status_banner = None
        self.status_timer: float = 0.0
        self.underwater_overlay = None
        self.hurt_overlay = None

        self.hotbar_frames: List[object] = []
        self.hotbar_icons: List[object] = []
        self.hotbar_counts: List[object] = []
        self.hotbar_dur_bars: List[object] = []

        self._init_hud()
        self.show_main_menu()

    def _clear_screen_root(self) -> None:
        try:
            from ursina import Entity, camera, destroy
            if self.screen_root is not None:
                destroy(self.screen_root)
            self.screen_root = Entity(parent=camera.ui)
        except Exception:
            pass

    def set_mouse_locked(self, locked: bool) -> None:
        try:
            from ursina import mouse
            mouse.locked = bool(locked)
            mouse.visible = not bool(locked)
        except Exception:
            pass

    def show_notification(self, message: str, duration: float = 2.5) -> None:
        self.status_timer = duration
        if self.status_banner is not None:
            try:
                self.status_banner.text = str(message)
                self.status_banner.enabled = True
            except Exception:
                pass

    def _init_hud(self) -> None:
        """Create persistent in-game HUD elements attached to `camera.ui`."""
        try:
            from ursina import Entity, Text, camera, color

            self.hud_root = Entity(parent=camera.ui, enabled=False)

            # Underwater & Hurt full-screen tint overlays
            self.underwater_overlay = Entity(
                parent=self.hud_root,
                model="quad",
                scale=(2.0, 1.2),
                z=0.5,
                color=color.rgba(0.08, 0.35, 0.78, 0.38),
                enabled=False,
            )
            self.hurt_overlay = Entity(
                parent=self.hud_root,
                model="quad",
                scale=(2.0, 1.2),
                z=0.45,
                color=color.rgba(0.85, 0.10, 0.10, 0.32),
                enabled=False,
            )

            # Crosshair (+)
            self.crosshair_h = Entity(
                parent=self.hud_root, model="quad", scale=(0.018, 0.0025), color=color.rgba(1, 1, 1, 0.88), z=-0.1
            )
            self.crosshair_v = Entity(
                parent=self.hud_root, model="quad", scale=(0.0025, 0.018), color=color.rgba(1, 1, 1, 0.88), z=-0.1
            )

            # Mining progress bar below crosshair
            self.mining_bar_bg = Entity(
                parent=self.hud_root,
                model="quad",
                position=(0, -0.045),
                scale=(0.12, 0.012),
                color=color.rgba(0.1, 0.1, 0.1, 0.75),
                enabled=False,
                z=-0.1,
            )
            self.mining_bar_fg = Entity(
                parent=self.hud_root,
                model="quad",
                position=(-0.06, -0.045),
                origin=(-0.5, 0),
                scale=(0.0, 0.009),
                color=color.rgb(0.3, 0.95, 0.4),
                enabled=False,
                z=-0.12,
            )

            # Top-left debug & world info panel
            Entity(
                parent=self.hud_root,
                model="quad",
                position=(-0.86, 0.48),
                origin=(-0.5, 0.5),
                scale=(0.56, 0.14),
                color=color.rgba(0.06, 0.08, 0.12, 0.68),
                z=0.1,
            )
            self.info_text = Text(
                parent=self.hud_root,
                text="XYZ: 0, 0, 0 | FPS: 60\nSeed: PyCraft2026\nDay 1",
                position=(-0.84, 0.465),
                scale=0.82,
                color=color.rgb(0.92, 0.95, 1.0),
                z=-0.1,
            )

            # Status notification banner
            self.status_banner = Text(
                parent=self.hud_root,
                text="",
                origin=(0, 0),
                position=(0, 0.36),
                scale=1.05,
                color=color.rgb(1.0, 0.92, 0.38),
                enabled=False,
                z=-0.2,
            )

            # Health Bar (left above hotbar)
            Entity(
                parent=self.hud_root,
                model="quad",
                position=(-0.31, -0.35),
                origin=(-0.5, 0),
                scale=(0.28, 0.032),
                color=color.rgba(0.12, 0.05, 0.05, 0.85),
                z=0.05,
            )
            self.hp_bar_fg = Entity(
                parent=self.hud_root,
                model="quad",
                position=(-0.308, -0.35),
                origin=(-0.5, 0),
                scale=(0.276, 0.026),
                color=color.rgb(0.88, 0.20, 0.22),
                z=0.0,
            )
            self.hp_text = Text(
                parent=self.hud_root,
                text="HP: 20 / 20",
                origin=(0, 0),
                position=(-0.17, -0.35),
                scale=0.78,
                color=color.white,
                z=-0.1,
            )

            # Hunger Bar (right above hotbar)
            Entity(
                parent=self.hud_root,
                model="quad",
                position=(0.03, -0.35),
                origin=(-0.5, 0),
                scale=(0.28, 0.032),
                color=color.rgba(0.14, 0.09, 0.04, 0.85),
                z=0.05,
            )
            self.hunger_bar_fg = Entity(
                parent=self.hud_root,
                model="quad",
                position=(0.032, -0.35),
                origin=(-0.5, 0),
                scale=(0.276, 0.026),
                color=color.rgb(0.88, 0.56, 0.16),
                z=0.0,
            )
            self.hunger_text = Text(
                parent=self.hud_root,
                text="Hunger: 20 / 20",
                origin=(0, 0),
                position=(0.17, -0.35),
                scale=0.78,
                color=color.white,
                z=-0.1,
            )

            # Held item title above health/hunger
            self.held_label = Text(
                parent=self.hud_root,
                text="Hand",
                origin=(0, 0),
                position=(0, -0.305),
                scale=0.90,
                color=color.rgb(1.0, 0.96, 0.78),
                z=-0.1,
            )

            # 9-Slot Hotbar at bottom center
            slot_spacing = 0.070
            start_x = -((HOTBAR_SIZE - 1) * slot_spacing) / 2.0
            y_pos = -0.435

            # Hotbar backing panel
            Entity(
                parent=self.hud_root,
                model="quad",
                position=(0, y_pos),
                scale=(HOTBAR_SIZE * slot_spacing + 0.02, 0.078),
                color=color.rgba(0.06, 0.07, 0.10, 0.88),
                z=0.1,
            )

            for i in range(HOTBAR_SIZE):
                sx = start_x + i * slot_spacing
                frame = Entity(
                    parent=self.hud_root,
                    model="quad",
                    position=(sx, y_pos),
                    scale=(0.062, 0.062),
                    color=color.rgb(0.24, 0.26, 0.30),
                    z=0.05,
                )
                icon = Entity(
                    parent=self.hud_root,
                    model="quad",
                    position=(sx, y_pos),
                    scale=(0.048, 0.048),
                    color=color.white,
                    enabled=False,
                    z=0.0,
                )
                cnt_txt = Text(
                    parent=self.hud_root,
                    text="",
                    origin=(0.5, -0.5),
                    position=(sx + 0.027, y_pos - 0.028),
                    scale=0.72,
                    color=color.white,
                    z=-0.1,
                )
                # Keybind number label in top-left corner of slot
                Text(
                    parent=self.hud_root,
                    text=str(i + 1),
                    origin=(-0.5, 0.5),
                    position=(sx - 0.027, y_pos + 0.028),
                    scale=0.60,
                    color=color.rgb(0.70, 0.72, 0.78),
                    z=-0.1,
                )
                dur_bar = Entity(
                    parent=self.hud_root,
                    model="quad",
                    position=(sx - 0.024, y_pos - 0.025),
                    origin=(-0.5, 0),
                    scale=(0.048, 0.005),
                    color=color.rgb(0.2, 0.95, 0.3),
                    enabled=False,
                    z=-0.08,
                )
                self.hotbar_frames.append(frame)
                self.hotbar_icons.append(icon)
                self.hotbar_counts.append(cnt_txt)
                self.hotbar_dur_bars.append(dur_bar)
        except Exception as exc:
            print(f"[UI] Warning initializing HUD: {exc}")

    def update_hud(self, dt: float) -> None:
        """Refresh HUD bars, hotbar icons/quantities, coordinates, FPS, and overlays."""
        if self.hud_root is None:
            return
        player = self.ctrl.player
        world = self.ctrl.world
        if player is None or world is None:
            return

        if self.status_timer > 0.0:
            self.status_timer -= dt
            if self.status_timer <= 0.0 and self.status_banner is not None:
                self.status_banner.enabled = False

        try:
            from ursina import color, time as utime

            # Underwater & Hurt overlays
            if self.underwater_overlay is not None:
                self.underwater_overlay.enabled = bool(player.head_underwater)
            if self.hurt_overlay is not None:
                self.hurt_overlay.enabled = player.hurt_flash_timer > 0.0

            # Mining bar
            prog = player.mining_progress
            if self.mining_bar_bg is not None and self.mining_bar_fg is not None:
                if prog > 0.01:
                    self.mining_bar_bg.enabled = True
                    self.mining_bar_fg.enabled = True
                    self.mining_bar_fg.scale_x = 0.116 * prog
                else:
                    self.mining_bar_bg.enabled = False
                    self.mining_bar_fg.enabled = False

            # Top-left info text
            fps = int(round(1.0 / max(0.001, getattr(utime, "dt", 0.016))))
            px, py, pz = player.position
            biome, _ = world.terrain.get_biome_and_height(int(px), int(pz))
            if self.info_text is not None:
                self.info_text.text = (
                    f"XYZ: {px:.1f}, {py:.1f}, {pz:.1f}  |  FPS: {min(240, fps)}\n"
                    f"Seed: {world.seed}  |  Biome: {biome}\n"
                    f"{world.get_time_label()}  |  {world.difficulty}"
                )

            # Health & Hunger bars
            hp_frac = max(0.0, min(1.0, player.health / max(1.0, player.max_health)))
            if self.hp_bar_fg is not None:
                self.hp_bar_fg.scale_x = 0.276 * hp_frac
            if self.hp_text is not None:
                self.hp_text.text = f"HP: {int(round(player.health))} / {int(player.max_health)}"

            hg_frac = max(0.0, min(1.0, player.hunger / max(1.0, player.max_hunger)))
            if self.hunger_bar_fg is not None:
                self.hunger_bar_fg.scale_x = 0.276 * hg_frac
            if self.hunger_text is not None:
                self.hunger_text.text = f"Hunger: {int(round(player.hunger))} / {int(player.max_hunger)}"

            # Selected item label
            sel_stack = player.inventory.get_selected_stack()
            if self.held_label is not None:
                if sel_stack is not None and sel_stack.item_def is not None:
                    idef = sel_stack.item_def
                    extra = ""
                    if sel_stack.durability is not None and idef.max_durability:
                        extra = f" [{sel_stack.durability}/{idef.max_durability}]"
                    elif idef.food_restore > 0:
                        extra = f" (+{idef.food_restore} Hunger - Right Click/F)"
                    self.held_label.text = f"{idef.name}{extra}"
                else:
                    self.held_label.text = "Empty Hand"

            # Update 9 Hotbar slots
            for i in range(HOTBAR_SIZE):
                st = player.inventory.slots[i]
                is_sel = (i == player.inventory.selected_slot)
                self.hotbar_frames[i].color = (
                    color.rgb(0.95, 0.80, 0.22) if is_sel else color.rgb(0.24, 0.26, 0.30)
                )
                self.hotbar_frames[i].scale = (0.066, 0.066) if is_sel else (0.060, 0.060)

                if st is not None:
                    self.hotbar_icons[i].texture = get_item_icon_texture(st.item_id)
                    self.hotbar_icons[i].enabled = True
                    self.hotbar_counts[i].text = str(st.count) if st.count > 1 else ""
                    if st.durability is not None and st.max_durability:
                        d_frac = max(0.0, min(1.0, st.durability / st.max_durability))
                        self.hotbar_dur_bars[i].enabled = True
                        self.hotbar_dur_bars[i].scale_x = 0.048 * d_frac
                    else:
                        self.hotbar_dur_bars[i].enabled = False
                else:
                    self.hotbar_icons[i].enabled = False
                    self.hotbar_counts[i].text = ""
                    self.hotbar_dur_bars[i].enabled = False
        except Exception:
            pass

    # =========================================================================
    # SCREENS & MENUS
    # =========================================================================

    def show_hud_only(self) -> None:
        """Close modal menus and return to active first-person gameplay."""
        if self.ctrl.player is not None:
            self.ctrl.player.inventory.return_cursor_to_inventory()
        self._clear_screen_root()
        self.active_screen = "hud"
        if self.hud_root is not None:
            self.hud_root.enabled = True
        self.set_mouse_locked(True)

    def show_main_menu(self) -> None:
        self._clear_screen_root()
        self.active_screen = "main_menu"
        if self.hud_root is not None:
            self.hud_root.enabled = False
        self.set_mouse_locked(False)

        try:
            from ursina import Button, Entity, Text, color

            # Dark stylized backdrop
            Entity(
                parent=self.screen_root,
                model="quad",
                scale=(2.0, 1.2),
                color=color.rgb(0.07, 0.10, 0.15),
                z=0.2,
            )
            # Decorative card panel
            Entity(
                parent=self.screen_root,
                model="quad",
                position=(0, 0.02),
                scale=(0.76, 0.76),
                color=color.rgba(0.12, 0.16, 0.22, 0.96),
                z=0.1,
            )

            Text(
                parent=self.screen_root,
                text="PYCRAFT",
                origin=(0, 0),
                position=(0, 0.28),
                scale=2.8,
                color=color.rgb(0.38, 0.88, 0.48),
            )
            Text(
                parent=self.screen_root,
                text="VOXEL SURVIVAL SANDBOX",
                origin=(0, 0),
                position=(0, 0.20),
                scale=1.05,
                color=color.rgb(0.82, 0.86, 0.92),
            )

            btn_specs = [
                ("NEW WORLD", 0.08, self.show_new_world_menu, color.rgb(0.20, 0.62, 0.34)),
                ("LOAD WORLD", -0.02, self.show_load_world_menu, color.rgb(0.22, 0.48, 0.72)),
                ("SETTINGS", -0.12, lambda: self.show_settings_menu(return_to="main_menu"), color.rgb(0.32, 0.36, 0.44)),
                ("QUIT GAME", -0.22, self.ctrl.quit_application, color.rgb(0.65, 0.22, 0.22)),
            ]
            for label, ypos, action, bcol in btn_specs:
                b = Button(
                    parent=self.screen_root,
                    text=label,
                    position=(0, ypos),
                    scale=(0.42, 0.072),
                    color=bcol,
                )
                b.on_click = action
        except Exception as exc:
            print(f"[UI] Error building main menu: {exc}")

    def show_new_world_menu(self) -> None:
        self._clear_screen_root()
        self.active_screen = "new_world"
        self.set_mouse_locked(False)

        try:
            from ursina import Button, Entity, InputField, Text, color

            Entity(parent=self.screen_root, model="quad", scale=(2.0, 1.2), color=color.rgb(0.07, 0.10, 0.15), z=0.2)
            Entity(parent=self.screen_root, model="quad", position=(0, 0), scale=(0.92, 0.82), color=color.rgba(0.12, 0.16, 0.22, 0.96), z=0.1)

            Text(parent=self.screen_root, text="CREATE NEW WORLD", origin=(0, 0), position=(0, 0.32), scale=1.6, color=color.rgb(0.42, 0.90, 0.52))

            # World Name InputField + Cycle Preset Button
            Text(parent=self.screen_root, text="World Name:", origin=(-0.5, 0), position=(-0.38, 0.18), scale=0.95)
            name_input = InputField(
                parent=self.screen_root,
                default_value=self.new_world_name,
                position=(-0.02, 0.18),
                scale=(0.38, 0.055),
            )

            def cycle_name():
                self._name_preset_idx = (self._name_preset_idx + 1) % len(self._world_name_presets)
                self.new_world_name = self._world_name_presets[self._name_preset_idx]
                name_input.text = self.new_world_name

            b_preset = Button(parent=self.screen_root, text="Preset", position=(0.28, 0.18), scale=(0.14, 0.055), color=color.rgb(0.28, 0.34, 0.44))
            b_preset.on_click = cycle_name

            # World Seed InputField + Randomize Button
            Text(parent=self.screen_root, text="World Seed:", origin=(-0.5, 0), position=(-0.38, 0.07), scale=0.95)
            seed_input = InputField(
                parent=self.screen_root,
                default_value=self.new_world_seed,
                position=(-0.02, 0.07),
                scale=(0.38, 0.055),
            )

            def randomize_seed():
                self.new_world_seed = f"Seed{random.randint(10000, 99999)}"
                seed_input.text = self.new_world_seed

            b_rand = Button(parent=self.screen_root, text="Random", position=(0.28, 0.07), scale=(0.14, 0.055), color=color.rgb(0.28, 0.34, 0.44))
            b_rand.on_click = randomize_seed

            # Difficulty Selector (Peaceful, Easy, Normal, Hard)
            Text(parent=self.screen_root, text="Difficulty:", origin=(-0.5, 0), position=(-0.38, -0.05), scale=0.95)
            diffs = ["Peaceful", "Easy", "Normal", "Hard"]
            diff_buttons: List[Button] = []

            def select_diff(d_val: str):
                self.new_world_difficulty = d_val
                for btn in diff_buttons:
                    btn.color = color.rgb(0.22, 0.65, 0.36) if btn.text == d_val else color.rgb(0.25, 0.28, 0.35)

            for idx, d_name in enumerate(diffs):
                bx = -0.14 + idx * 0.15
                btn = Button(
                    parent=self.screen_root,
                    text=d_name,
                    position=(bx, -0.05),
                    scale=(0.135, 0.058),
                    color=color.rgb(0.22, 0.65, 0.36) if d_name == self.new_world_difficulty else color.rgb(0.25, 0.28, 0.35),
                )
                btn.on_click = lambda dn=d_name: select_diff(dn)
                diff_buttons.append(btn)

            def on_create():
                w_name = getattr(name_input, "text", "").strip() or self.new_world_name
                w_seed = getattr(seed_input, "text", "").strip() or self.new_world_seed
                self.ctrl.start_new_world(
                    world_name=w_name,
                    seed=w_seed,
                    difficulty=self.new_world_difficulty,
                )

            b_create = Button(
                parent=self.screen_root,
                text="CREATE & PLAY WORLD",
                position=(-0.12, -0.22),
                scale=(0.36, 0.075),
                color=color.rgb(0.20, 0.65, 0.35),
            )
            b_create.on_click = on_create

            b_back = Button(
                parent=self.screen_root,
                text="BACK",
                position=(0.22, -0.22),
                scale=(0.20, 0.075),
                color=color.rgb(0.45, 0.25, 0.25),
            )
            b_back.on_click = self.show_main_menu
        except Exception as exc:
            print(f"[UI] Error building new world menu: {exc}")

    def show_load_world_menu(self) -> None:
        self._clear_screen_root()
        self.active_screen = "load_world"
        self.set_mouse_locked(False)

        try:
            from ursina import Button, Entity, Text, color

            Entity(parent=self.screen_root, model="quad", scale=(2.0, 1.2), color=color.rgb(0.07, 0.10, 0.15), z=0.2)
            Entity(parent=self.screen_root, model="quad", position=(0, 0), scale=(1.05, 0.86), color=color.rgba(0.12, 0.16, 0.22, 0.96), z=0.1)

            Text(parent=self.screen_root, text="SAVED WORLDS", origin=(0, 0), position=(0, 0.35), scale=1.6, color=color.rgb(0.45, 0.78, 0.98))

            worlds = self.ctrl.save_manager.list_saved_worlds()
            if not worlds:
                Text(
                    parent=self.screen_root,
                    text="No saved worlds found yet. Create a New World first!",
                    origin=(0, 0),
                    position=(0, 0.05),
                    scale=1.0,
                    color=color.rgb(0.75, 0.78, 0.84),
                )
            else:
                for idx, winfo in enumerate(worlds[:5]):
                    ypos = 0.21 - idx * 0.105
                    slug = winfo["slug"]
                    label = f"{winfo['world_name']}  |  Seed: {winfo['seed']}  |  {winfo['difficulty']} (Day {winfo['day_count']})"
                    Entity(
                        parent=self.screen_root,
                        model="quad",
                        position=(-0.12, ypos),
                        scale=(0.68, 0.082),
                        color=color.rgb(0.18, 0.22, 0.29),
                        z=0.05,
                    )
                    Text(
                        parent=self.screen_root,
                        text=label,
                        origin=(-0.5, 0),
                        position=(-0.44, ypos),
                        scale=0.82,
                        color=color.white,
                    )
                    b_load = Button(
                        parent=self.screen_root,
                        text="LOAD",
                        position=(0.30, ypos),
                        scale=(0.12, 0.068),
                        color=color.rgb(0.20, 0.62, 0.34),
                    )
                    b_load.on_click = lambda s=slug: self.ctrl.load_saved_world(s)

                    b_del = Button(
                        parent=self.screen_root,
                        text="DELETE",
                        position=(0.43, ypos),
                        scale=(0.12, 0.068),
                        color=color.rgb(0.68, 0.22, 0.22),
                    )

                    def make_del(s=slug):
                        self.ctrl.save_manager.delete_world(s)
                        self.show_load_world_menu()

                    b_del.on_click = make_del

            b_back = Button(
                parent=self.screen_root,
                text="BACK TO MAIN MENU",
                position=(0, -0.34),
                scale=(0.36, 0.072),
                color=color.rgb(0.38, 0.32, 0.32),
            )
            b_back.on_click = self.show_main_menu
        except Exception as exc:
            print(f"[UI] Error building load world menu: {exc}")

    def show_settings_menu(self, return_to: str = "main_menu") -> None:
        self._clear_screen_root()
        self.previous_screen = return_to
        self.active_screen = "settings"
        if self.hud_root is not None:
            self.hud_root.enabled = False
        self.set_mouse_locked(False)
        s = self.ctrl.settings

        try:
            from ursina import Button, Entity, Text, color

            Entity(parent=self.screen_root, model="quad", scale=(2.0, 1.2), color=color.rgba(0.05, 0.08, 0.12, 0.92), z=0.2)
            Entity(parent=self.screen_root, model="quad", position=(0, 0), scale=(1.02, 0.88), color=color.rgba(0.12, 0.16, 0.22, 0.98), z=0.1)

            Text(parent=self.screen_root, text="GAME SETTINGS", origin=(0, 0), position=(0, 0.36), scale=1.55, color=color.rgb(0.95, 0.82, 0.35))

            def refresh():
                s.save()
                s.apply_to_engine()
                self.show_settings_menu(return_to=return_to)

            rows = [
                (
                    f"Mouse Sensitivity: {int(s.mouse_sensitivity)}",
                    lambda: (setattr(s, "mouse_sensitivity", max(10, s.mouse_sensitivity - 5)), refresh()),
                    lambda: (setattr(s, "mouse_sensitivity", min(150, s.mouse_sensitivity + 5)), refresh()),
                ),
                (
                    f"Field of View (FOV): {int(s.fov)}",
                    lambda: (setattr(s, "fov", max(60, s.fov - 5)), refresh()),
                    lambda: (setattr(s, "fov", min(120, s.fov + 5)), refresh()),
                ),
                (
                    f"Render Distance: {int(s.render_distance)} Chunks",
                    lambda: (setattr(s, "render_distance", max(2, s.render_distance - 1)), refresh()),
                    lambda: (setattr(s, "render_distance", min(6, s.render_distance + 1)), refresh()),
                ),
                (
                    f"Master Volume: {int(round(s.volume * 100))}%",
                    lambda: (setattr(s, "volume", max(0.0, round(s.volume - 0.1, 2))), refresh()),
                    lambda: (setattr(s, "volume", min(1.0, round(s.volume + 0.1, 2))), refresh()),
                ),
            ]

            for idx, (label, dec_fn, inc_fn) in enumerate(rows):
                ypos = 0.24 - idx * 0.082
                Text(parent=self.screen_root, text=label, origin=(-0.5, 0), position=(-0.42, ypos), scale=0.88)
                b_minus = Button(parent=self.screen_root, text="-", position=(0.18, ypos), scale=(0.08, 0.055), color=color.rgb(0.30, 0.34, 0.42))
                b_minus.on_click = dec_fn
                b_plus = Button(parent=self.screen_root, text="+", position=(0.28, ypos), scale=(0.08, 0.055), color=color.rgb(0.30, 0.34, 0.42))
                b_plus.on_click = inc_fn

            # Toggle buttons row 1: Music, Sound Effects, Fullscreen
            toggles = [
                (f"Music: {'ON' if s.music else 'OFF'}", (-0.30, -0.11), lambda: (setattr(s, "music", not s.music), refresh())),
                (f"SFX: {'ON' if s.sound_effects else 'OFF'}", (0.0, -0.11), lambda: (setattr(s, "sound_effects", not s.sound_effects), refresh())),
                (f"Fullscreen: {'ON' if s.fullscreen else 'OFF'}", (0.30, -0.11), lambda: (setattr(s, "fullscreen", not s.fullscreen), refresh())),
                (
                    f"Graphics: {s.graphics_quality}",
                    (-0.18, -0.20),
                    lambda: (
                        setattr(
                            s,
                            "graphics_quality",
                            {"Low": "Medium", "Medium": "High", "High": "Low"}.get(s.graphics_quality, "High"),
                        ),
                        refresh(),
                    ),
                ),
                (
                    f"Keep Inventory: {'ON' if s.keep_inventory else 'OFF'}",
                    (0.20, -0.20),
                    lambda: (setattr(s, "keep_inventory", not s.keep_inventory), refresh()),
                ),
            ]
            for t_label, t_pos, t_fn in toggles:
                btn = Button(parent=self.screen_root, text=t_label, position=t_pos, scale=(0.27, 0.062), color=color.rgb(0.24, 0.42, 0.56))
                btn.on_click = t_fn

            def go_back():
                s.save()
                s.apply_to_engine()
                if return_to == "pause":
                    self.show_pause_menu()
                else:
                    self.show_main_menu()

            b_done = Button(
                parent=self.screen_root,
                text="SAVE & BACK",
                position=(0, -0.34),
                scale=(0.34, 0.072),
                color=color.rgb(0.20, 0.62, 0.34),
            )
            b_done.on_click = go_back
        except Exception as exc:
            print(f"[UI] Error building settings menu: {exc}")

    def show_pause_menu(self) -> None:
        self._clear_screen_root()
        self.active_screen = "pause"
        if self.hud_root is not None:
            self.hud_root.enabled = False
        self.set_mouse_locked(False)

        try:
            from ursina import Button, Entity, Text, color

            Entity(parent=self.screen_root, model="quad", scale=(2.0, 1.2), color=color.rgba(0.02, 0.03, 0.05, 0.72), z=0.2)
            Entity(parent=self.screen_root, model="quad", position=(0, 0), scale=(0.62, 0.66), color=color.rgba(0.12, 0.16, 0.22, 0.96), z=0.1)

            Text(parent=self.screen_root, text="GAME PAUSED", origin=(0, 0), position=(0, 0.22), scale=1.5, color=color.white)

            def on_save():
                if self.ctrl.save_current_world():
                    self.show_notification("World Saved Successfully!")
                self.show_hud_only()

            def on_save_quit():
                self.ctrl.save_current_world()
                self.ctrl.return_to_main_menu()

            btns = [
                ("RESUME GAME", 0.09, self.show_hud_only, color.rgb(0.20, 0.62, 0.34)),
                ("SAVE WORLD", -0.01, on_save, color.rgb(0.22, 0.48, 0.72)),
                ("SETTINGS", -0.11, lambda: self.show_settings_menu(return_to="pause"), color.rgb(0.32, 0.36, 0.44)),
                ("SAVE & QUIT TO TITLE", -0.21, on_save_quit, color.rgb(0.65, 0.22, 0.22)),
            ]
            for lbl, yp, fn, col in btns:
                b = Button(parent=self.screen_root, text=lbl, position=(0, yp), scale=(0.42, 0.070), color=col)
                b.on_click = fn
        except Exception as exc:
            print(f"[UI] Error building pause menu: {exc}")

    def show_inventory_screen(self, mode: str = "crafting") -> None:
        """
        Show the unified Inventory + Crafting / Furnace screen.
        Left side: 36-slot interactive inventory (click to move/swap items).
        Right side: Crafting recipes list OR Furnace smelting panel.
        """
        self._clear_screen_root()
        self.active_screen = "inventory"
        self.inv_tab = mode if mode in ("crafting", "furnace") else "crafting"
        if self.hud_root is not None:
            self.hud_root.enabled = False
        self.set_mouse_locked(False)

        player = self.ctrl.player
        if player is None:
            return
        inv = player.inventory

        try:
            from ursina import Button, Entity, Text, color

            Entity(parent=self.screen_root, model="quad", scale=(2.0, 1.2), color=color.rgba(0.02, 0.03, 0.06, 0.74), z=0.25)
            Entity(parent=self.screen_root, model="quad", position=(0, 0.02), scale=(1.42, 0.86), color=color.rgba(0.11, 0.14, 0.20, 0.97), z=0.15)

            # Top header & Mode switch tabs
            Text(parent=self.screen_root, text="INVENTORY & WORKBENCH", origin=(-0.5, 0), position=(-0.66, 0.38), scale=1.2, color=color.rgb(0.95, 0.88, 0.45))

            b_tab_craft = Button(
                parent=self.screen_root,
                text="CRAFTING",
                position=(0.15, 0.38),
                scale=(0.20, 0.055),
                color=color.rgb(0.22, 0.62, 0.35) if self.inv_tab == "crafting" else color.rgb(0.24, 0.28, 0.36),
            )
            b_tab_craft.on_click = lambda: self.show_inventory_screen("crafting")

            b_tab_furn = Button(
                parent=self.screen_root,
                text="FURNACE",
                position=(0.37, 0.38),
                scale=(0.20, 0.055),
                color=color.rgb(0.82, 0.42, 0.18) if self.inv_tab == "furnace" else color.rgb(0.24, 0.28, 0.36),
            )
            b_tab_furn.on_click = lambda: self.show_inventory_screen("furnace")

            b_close = Button(
                parent=self.screen_root,
                text="CLOSE [E]",
                position=(0.58, 0.38),
                scale=(0.16, 0.055),
                color=color.rgb(0.62, 0.22, 0.22),
            )
            b_close.on_click = self.show_hud_only

            # Cursor stack status indicator
            cursor_txt = "Cursor: Empty (Click any slot to move/swap items)"
            if inv.cursor_stack is not None:
                c_def = inv.cursor_stack.item_def
                c_name = c_def.name if c_def else inv.cursor_stack.item_id
                cursor_txt = f"Holding: {inv.cursor_stack.count}x {c_name} (Click destination slot to place)"
            Text(
                parent=self.screen_root,
                text=cursor_txt,
                origin=(-0.5, 0),
                position=(-0.66, 0.31),
                scale=0.82,
                color=color.rgb(0.65, 0.95, 0.72) if inv.cursor_stack else color.rgb(0.78, 0.82, 0.88),
            )

            # LEFT PANEL: 27 Main Backpack Slots (3 rows of 9) + 9 Hotbar Slots
            slot_step = 0.072
            grid_left = -0.62

            def make_slot_button(slot_idx: int, sx: float, sy: float, is_hotbar: bool = False):
                st = inv.slots[slot_idx]
                base_col = color.rgb(0.26, 0.30, 0.38) if not is_hotbar else color.rgb(0.22, 0.26, 0.34)
                if is_hotbar and slot_idx == inv.selected_slot:
                    base_col = color.rgb(0.55, 0.48, 0.18)

                btn = Button(
                    parent=self.screen_root,
                    text="",
                    position=(sx, sy),
                    scale=(0.064, 0.064),
                    color=base_col,
                    z=0.05,
                )

                def on_slot_click(idx=slot_idx):
                    inv.click_slot(idx, right_click=False)
                    player.update_held_visual()
                    self.show_inventory_screen(self.inv_tab)

                btn.on_click = on_slot_click

                if st is not None:
                    Entity(
                        parent=self.screen_root,
                        model="quad",
                        texture=get_item_icon_texture(st.item_id),
                        position=(sx, sy),
                        scale=(0.048, 0.048),
                        color=color.white,
                        z=0.0,
                    )
                    if st.count > 1:
                        Text(
                            parent=self.screen_root,
                            text=str(st.count),
                            origin=(0.5, -0.5),
                            position=(sx + 0.028, sy - 0.028),
                            scale=0.70,
                            color=color.white,
                            z=-0.05,
                        )

            Text(parent=self.screen_root, text="Backpack (27 Slots):", origin=(-0.5, 0), position=(-0.65, 0.23), scale=0.82)
            for row in range(3):
                for col in range(9):
                    s_idx = 9 + row * 9 + col
                    sx = grid_left + col * slot_step
                    sy = 0.16 - row * slot_step
                    make_slot_button(s_idx, sx, sy, is_hotbar=False)

            Text(parent=self.screen_root, text="Hotbar (Slots 1-9):", origin=(-0.5, 0), position=(-0.65, -0.09), scale=0.82)
            for col in range(9):
                sx = grid_left + col * slot_step
                sy = -0.16
                make_slot_button(col, sx, sy, is_hotbar=True)

            # RIGHT PANEL: Crafting OR Furnace
            if self.inv_tab == "crafting":
                self._build_crafting_subpanel(player)
            else:
                self._build_furnace_subpanel(player)

        except Exception as exc:
            print(f"[UI] Error building inventory screen: {exc}")

    def _build_crafting_subpanel(self, player) -> None:
        from ursina import Button, Entity, Text, color

        inv = player.inventory
        cs = self.ctrl.crafting
        recipes = cs.recipes
        per_page = 6
        max_page = max(0, (len(recipes) - 1) // per_page)
        self.recipe_page = max(0, min(max_page, self.recipe_page))

        Text(
            parent=self.screen_root,
            text=f"Crafting Recipes (Page {self.recipe_page + 1}/{max_page + 1}):",
            origin=(-0.5, 0),
            position=(0.04, 0.23),
            scale=0.88,
            color=color.rgb(0.90, 0.95, 1.0),
        )

        page_slice = recipes[self.recipe_page * per_page : (self.recipe_page + 1) * per_page]
        for idx, rec in enumerate(page_slice):
            ry = 0.15 - idx * 0.072
            craftable = cs.can_craft(rec, inv)

            # Row background
            Entity(
                parent=self.screen_root,
                model="quad",
                position=(0.35, ry),
                scale=(0.62, 0.062),
                color=color.rgb(0.16, 0.24, 0.20) if craftable else color.rgb(0.16, 0.18, 0.24),
                z=0.05,
            )
            # Output icon
            Entity(
                parent=self.screen_root,
                model="quad",
                texture=get_item_icon_texture(rec.result_item),
                position=(0.075, ry),
                scale=(0.045, 0.045),
                color=color.white,
                z=0.0,
            )
            Text(
                parent=self.screen_root,
                text=f"{rec.name}\nNeeds: {rec.format_ingredients()}",
                origin=(-0.5, 0),
                position=(0.11, ry),
                scale=0.68,
                color=color.white if craftable else color.rgb(0.65, 0.68, 0.72),
                z=-0.02,
            )

            btn_craft = Button(
                parent=self.screen_root,
                text="CRAFT",
                position=(0.58, ry),
                scale=(0.13, 0.052),
                color=color.rgb(0.20, 0.68, 0.34) if craftable else color.rgb(0.28, 0.30, 0.35),
                z=0.02,
            )

            def on_craft_click(r_id=rec.id):
                if cs.craft(r_id, inv):
                    play_game_sound("craft", self.ctrl.settings)
                    player.update_held_visual()
                    self.show_notification(f"Crafted {cs.by_id[r_id].name}!")
                self.show_inventory_screen("crafting")

            btn_craft.on_click = on_craft_click

        # Pagination buttons
        b_prev = Button(
            parent=self.screen_root,
            text="< Prev Page",
            position=(0.22, -0.29),
            scale=(0.18, 0.055),
            color=color.rgb(0.28, 0.34, 0.44),
        )
        b_prev.on_click = lambda: (setattr(self, "recipe_page", max(0, self.recipe_page - 1)), self.show_inventory_screen("crafting"))

        b_next = Button(
            parent=self.screen_root,
            text="Next Page >",
            position=(0.46, -0.29),
            scale=(0.18, 0.055),
            color=color.rgb(0.28, 0.34, 0.44),
        )
        b_next.on_click = lambda: (setattr(self, "recipe_page", min(max_page, self.recipe_page + 1)), self.show_inventory_screen("crafting"))

    def _build_furnace_subpanel(self, player) -> None:
        from ursina import Button, Entity, Text, color

        furn = self.ctrl.furnace
        inv = player.inventory

        Text(
            parent=self.screen_root,
            text="FURNACE SMELTING & COOKING",
            origin=(-0.5, 0),
            position=(0.06, 0.23),
            scale=0.92,
            color=color.rgb(1.0, 0.72, 0.35),
        )

        # Display Input, Fuel, and Output slots
        in_txt = f"{furn.input_slot.count}x {furn.input_slot.item_def.name}" if furn.input_slot and furn.input_slot.item_def else "Empty"
        fuel_txt = f"{furn.fuel_slot.count}x {furn.fuel_slot.item_def.name}" if furn.fuel_slot and furn.fuel_slot.item_def else "Empty"
        out_txt = f"{furn.output_slot.count}x {furn.output_slot.item_def.name}" if furn.output_slot and furn.output_slot.item_def else "Empty"

        info_str = (
            f"Input Slot:   {in_txt}\n"
            f"Fuel Slot:    {fuel_txt}\n"
            f"Output Slot:  {out_txt}\n\n"
            f"Smelt Progress: {int(furn.progress * 100)}%   |   Fire Remaining: {furn.burn_time:.1f}s"
        )
        Text(
            parent=self.screen_root,
            text=info_str,
            origin=(-0.5, 0.5),
            position=(0.06, 0.16),
            scale=0.80,
            color=color.white,
        )

        # Action buttons to load input, load fuel, step smelt, or collect output
        def load_input():
            furn.add_input_from_inventory(inv, count=1)
            self.show_inventory_screen("furnace")

        def load_fuel():
            furn.add_fuel_from_inventory(inv, count=1)
            self.show_inventory_screen("furnace")

        def collect_out():
            cnt = furn.collect_output(inv)
            if cnt > 0:
                play_game_sound("craft", self.ctrl.settings)
                player.update_held_visual()
            self.show_inventory_screen("furnace")

        b_in = Button(parent=self.screen_root, text="+ Add Ore / Raw Food", position=(0.20, -0.08), scale=(0.26, 0.06), color=color.rgb(0.24, 0.48, 0.68))
        b_in.on_click = load_input

        b_fuel = Button(parent=self.screen_root, text="+ Add Fuel (Coal/Wood)", position=(0.50, -0.08), scale=(0.26, 0.06), color=color.rgb(0.68, 0.42, 0.18))
        b_fuel.on_click = load_fuel

        b_out = Button(parent=self.screen_root, text="Collect Smelted Output", position=(0.35, -0.18), scale=(0.36, 0.065), color=color.rgb(0.22, 0.65, 0.35))
        b_out.on_click = collect_out

    def show_death_screen(self) -> None:
        self._clear_screen_root()
        self.active_screen = "death"
        if self.hud_root is not None:
            self.hud_root.enabled = False
        self.set_mouse_locked(False)

        reason = getattr(self.ctrl.player, "death_reason", "") or "You lost all health"

        try:
            from ursina import Button, Entity, Text, color

            Entity(parent=self.screen_root, model="quad", scale=(2.0, 1.2), color=color.rgba(0.38, 0.04, 0.04, 0.85), z=0.2)
            Entity(parent=self.screen_root, model="quad", position=(0, 0), scale=(0.74, 0.56), color=color.rgba(0.14, 0.06, 0.06, 0.96), z=0.1)

            Text(parent=self.screen_root, text="YOU DIED!", origin=(0, 0), position=(0, 0.15), scale=2.2, color=color.rgb(1.0, 0.28, 0.28))
            Text(parent=self.screen_root, text=reason, origin=(0, 0), position=(0, 0.05), scale=1.0, color=color.rgb(0.92, 0.82, 0.82))

            def on_respawn():
                self.ctrl.respawn_player()

            b_resp = Button(
                parent=self.screen_root,
                text="RESPAWN",
                position=(0, -0.07),
                scale=(0.38, 0.075),
                color=color.rgb(0.22, 0.64, 0.34),
            )
            b_resp.on_click = on_respawn

            b_menu = Button(
                parent=self.screen_root,
                text="MAIN MENU",
                position=(0, -0.18),
                scale=(0.38, 0.070),
                color=color.rgb(0.48, 0.24, 0.24),
            )
            b_menu.on_click = self.ctrl.return_to_main_menu
        except Exception as exc:
            print(f"[UI] Error building death screen: {exc}")
