"""
Persistent game settings manager.
Handles mouse sensitivity, FOV, render distance, volume, music, sound effects,
graphics quality, fullscreen/windowed mode, and keep_inventory on death.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict

ROOT_DIR = Path(__file__).resolve().parent.parent
SAVES_DIR = ROOT_DIR / "saves"
SETTINGS_FILE = SAVES_DIR / "settings.json"


@dataclass
class GameSettings:
    mouse_sensitivity: float = 45.0
    fov: int = 90
    render_distance: int = 3
    volume: float = 0.7
    music: bool = True
    sound_effects: bool = True
    graphics_quality: str = "High"  # 'Low', 'Medium', 'High'
    fullscreen: bool = False
    keep_inventory: bool = True

    def validate(self) -> None:
        """Clamp and sanitize all settings values."""
        try:
            self.mouse_sensitivity = max(10.0, min(150.0, float(self.mouse_sensitivity)))
        except (TypeError, ValueError):
            self.mouse_sensitivity = 45.0

        try:
            self.fov = max(60, min(120, int(self.fov)))
        except (TypeError, ValueError):
            self.fov = 90

        try:
            self.render_distance = max(2, min(6, int(self.render_distance)))
        except (TypeError, ValueError):
            self.render_distance = 3

        try:
            self.volume = max(0.0, min(1.0, float(self.volume)))
        except (TypeError, ValueError):
            self.volume = 0.7

        self.music = bool(self.music)
        self.sound_effects = bool(self.sound_effects)
        if self.graphics_quality not in ("Low", "Medium", "High"):
            self.graphics_quality = "High"
        self.fullscreen = bool(self.fullscreen)
        self.keep_inventory = bool(self.keep_inventory)

    def save(self, filepath: Path = SETTINGS_FILE) -> bool:
        """Persist settings to disk atomically."""
        self.validate()
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = filepath.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
            tmp_path.replace(filepath)
            return True
        except Exception as exc:
            print(f"[Settings] Could not save settings: {exc}")
            return False

    @classmethod
    def load(cls, filepath: Path = SETTINGS_FILE) -> "GameSettings":
        """Load settings from disk, falling back to safe defaults if missing or corrupted."""
        settings = cls()
        if not filepath.exists():
            settings.save(filepath)
            return settings

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data: Dict[str, Any] = json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if hasattr(settings, k):
                        setattr(settings, k, v)
            settings.validate()
        except Exception as exc:
            print(f"[Settings] Corrupted or unreadable settings file ({exc}); resetting to defaults.")
            settings = cls()
            settings.save(filepath)

        return settings

    def apply_to_engine(self) -> None:
        """Apply camera FOV and window settings to the active Ursina engine instance safely."""
        self.validate()
        try:
            from ursina import camera, window
            if hasattr(camera, "fov"):
                camera.fov = self.fov
            if hasattr(window, "fullscreen") and window.fullscreen != self.fullscreen:
                try:
                    window.fullscreen = self.fullscreen
                except Exception:
                    pass
        except Exception:
            pass
