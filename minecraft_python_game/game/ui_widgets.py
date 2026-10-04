"""
Reusable Ursina widgets for the PyCraft menus: textured stone buttons, an animated
panorama backdrop, a bobbing logo and a pulsing splash text.

Ursina classes are created lazily (on first use) so importing this module never
requires a display or the engine to be installed.
"""

import math
import random
from typing import Optional

from game.assets_gen import get_item_icon_texture, get_ui_texture

SPLASHES = [
    "Dig straight down at your own risk!",
    "100% procedural!",
    "Now with textured mobs!",
    "Beware the night!",
    "Pixel art, made in code!",
    "Crafted with Python!",
    "Mind the skeletons!",
    "Torches are your friends!",
    "Try the steak!",
    "Don't forget your pickaxe!",
    "Diamonds are deep!",
    "Pigs can't fly (yet)!",
]

_CLASSES = {}


def tint_from_accent(c) -> tuple:
    """Turn a saturated accent colour into a light multiplier for the grey button texture."""
    r, g, b = float(c[0]), float(c[1]), float(c[2])
    return (0.64 + 0.36 * r, 0.64 + 0.36 * g, 0.64 + 0.36 * b)


def _classes():
    if _CLASSES:
        return _CLASSES
    from ursina import Button, Default, Entity, Text, color, time

    class MenuButton(Button):
        """Stone-textured button with hover/pressed states."""

        def __init__(self, text="", color=Default, **kwargs):
            if color is Default or color is None:
                tint = (1.0, 1.0, 1.0, 1.0)
            else:
                tint = tint_from_accent(color) + (1.0,)
            self._tint_rgba = tint
            super().__init__(
                text=text,
                model="quad",
                color=_rgba(tint),
                texture=get_ui_texture("button_normal"),
                **kwargs,
            )
            self.highlight_color = _rgba(tint)
            self.pressed_color = _rgba(tint)
            self._set_label(False)

        def _set_label(self, hot: bool) -> None:
            try:
                if self.text_entity is not None:
                    self.text_entity.color = _rgba((1.0, 1.0, 0.62, 1.0)) if hot else _rgba((1.0, 1.0, 1.0, 1.0))
            except Exception:
                pass

        def on_mouse_enter(self):
            super().on_mouse_enter()
            if not self.disabled:
                self.texture = get_ui_texture("button_hover")
                self._set_label(True)

        def on_mouse_exit(self):
            super().on_mouse_exit()
            self.texture = get_ui_texture("button_normal")
            self._set_label(False)

        def input(self, key):
            super().input(key)
            if key == "left mouse down" and self.hovered:
                self.texture = get_ui_texture("button_pressed")
            elif key == "left mouse up":
                self.texture = get_ui_texture("button_hover" if self.hovered else "button_normal")

    def _rgba(t):
        return color.rgba(t[0], t[1], t[2], t[3] if len(t) > 3 else 1.0)

    class Panorama(Entity):
        """Slowly drifting backdrop image."""

        def __init__(self, parent, **kwargs):
            super().__init__(parent=parent, model="quad", texture=get_ui_texture("panorama"),
                             scale=(2.25, 1.266), z=0.3, **kwargs)
            self._t = random.uniform(0, 6.28)

        def update(self):
            self._t += time.dt * 0.12
            self.x = math.sin(self._t) * 0.11
            self.y = math.sin(self._t * 0.7) * 0.012

    class Bobber(Entity):
        """Entity that gently bobs vertically (logo, floating icons)."""

        def __init__(self, base_y: float, amp: float = 0.006, speed: float = 1.4, phase: float = 0.0, **kwargs):
            super().__init__(**kwargs)
            self._base_y = base_y
            self._amp, self._speed, self._phase = amp, speed, phase
            self.y = base_y
            self._t = 0.0

        def update(self):
            self._t += time.dt
            self.y = self._base_y + math.sin(self._t * self._speed + self._phase) * self._amp

    class Splash(Text):
        """Yellow tilted splash text with a soft pulse."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._t = 0.0
            self._base = float(self.scale_x) if hasattr(self, "scale_x") else 1.0

        def update(self):
            self._t += time.dt
            k = 1.0 + 0.045 * math.sin(self._t * 5.0)
            self.scale = self._base * k

    _CLASSES.update(MenuButton=MenuButton, Panorama=Panorama, Bobber=Bobber, Splash=Splash, rgba=_rgba)
    return _CLASSES


def menu_button_class():
    return _classes()["MenuButton"]


def build_backdrop(parent, dim: float = 0.0, vignette: bool = True) -> None:
    """Add the panorama backdrop (with optional dimming) under `parent`."""
    from ursina import Entity, color

    c = _classes()
    c["Panorama"](parent)
    if dim > 0.0:
        Entity(parent=parent, model="quad", scale=(2.4, 1.4), z=0.25, color=color.rgba(0.02, 0.03, 0.06, dim))


def build_panel(parent, position, scale, z: float = 0.1) -> None:
    """Dark bordered panel used behind sub-menu content."""
    from ursina import Entity, color

    px, py = position
    sx, sy = scale
    Entity(parent=parent, model="quad", position=(px, py), scale=(sx + 0.012, sy + 0.016), color=color.rgba(0.02, 0.02, 0.03, 0.95), z=z + 0.02)
    Entity(parent=parent, model="quad", position=(px, py), scale=(sx, sy), color=color.rgba(0.10, 0.12, 0.17, 0.90), z=z + 0.01)
    Entity(parent=parent, model="quad", position=(px, py + sy / 2 - 0.004), scale=(sx, 0.006), color=color.rgba(0.62, 0.70, 0.86, 0.35), z=z)


def build_main_menu(parent, ctrl_actions) -> None:
    """Compose the full title screen. ctrl_actions: dict of callables new/load/settings/quit."""
    from ursina import Entity, Text, color

    c = _classes()
    build_backdrop(parent, dim=0.0)

    # Logo with bobbing + faint glow
    logo_tex = get_ui_texture("logo")
    if logo_tex is not None:
        c["Bobber"](base_y=0.285, amp=0.007, parent=parent, model="quad", texture=logo_tex,
                    scale=(0.92, 0.92 * 160 / 704), z=0.0)

    # Floating item icons flanking the logo
    for key, x, ph in (("grass", -0.56, 0.0), ("diamond", 0.56, 1.7)):
        tex = get_item_icon_texture(key)
        if tex is not None:
            c["Bobber"](base_y=0.285, amp=0.012, speed=1.8, phase=ph, parent=parent, model="quad",
                        texture=tex, x=x, scale=0.115, z=0.0)

    # Splash text
    c["Splash"](parent=parent, text=random.choice(SPLASHES), origin=(0, 0), position=(0.27, 0.19),
                scale=1.2, rotation_z=-14, color=color.rgb(1.0, 0.92, 0.18), z=-0.05)

    MB = c["MenuButton"]
    w, h = 0.52, 0.052
    specs = [
        ("NEW WORLD", 0.05, ctrl_actions["new"], color.rgb(0.20, 0.62, 0.34), w, 0.0),
        ("LOAD WORLD", -0.02, ctrl_actions["load"], color.rgb(0.22, 0.48, 0.72), w, 0.0),
    ]
    for label, y, fn, col, bw, x in specs:
        b = MB(parent=parent, text=label, position=(x, y), scale=(bw, h), color=col)
        b.on_click = fn
    half = (w - 0.012) / 2
    b = MB(parent=parent, text="SETTINGS", position=(-(half + 0.012) / 2 - 0.0, -0.09), scale=(half, h))
    b.x = -(w / 2) + half / 2
    b.on_click = ctrl_actions["settings"]
    b = MB(parent=parent, text="QUIT", position=(0, -0.09), scale=(half, h), color=color.rgb(0.75, 0.30, 0.30))
    b.x = (w / 2) - half / 2
    b.on_click = ctrl_actions["quit"]

    # Footer
    Text(parent=parent, text="PyCraft  |  procedural voxel survival", origin=(-0.5, 0), position=(-0.86, -0.47),
         scale=0.75, color=color.rgba(1, 1, 1, 0.75), z=-0.05)
    Text(parent=parent, text="WASD move  -  E inventory  -  Esc pause", origin=(0.5, 0), position=(0.86, -0.47),
         scale=0.75, color=color.rgba(1, 1, 1, 0.75), z=-0.05)
