"""
Persistent World Save & Load system.
Saves world seed, difficulty, world time, player state, inventory, hotbar,
broken/placed blocks, chests, and furnace state to JSON files in saves/.
Includes atomic writes, backup fallback, and corrupted-file recovery.
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from game.furnace import FurnaceSystem
from game.player import Player
from game.world import World

ROOT_DIR = Path(__file__).resolve().parent.parent
SAVES_DIR = ROOT_DIR / "saves"


def slugify_world_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(name).strip()).strip("_")
    return cleaned.lower() if cleaned else "world_1"


class SaveManager:
    """Handles saving, loading, listing, and deleting worlds in `saves/`."""

    def __init__(self, saves_dir: Path = SAVES_DIR):
        self.saves_dir = Path(saves_dir)
        self.saves_dir.mkdir(parents=True, exist_ok=True)

    def get_save_path(self, world_name_or_id: str) -> Path:
        slug = slugify_world_name(world_name_or_id)
        return self.saves_dir / f"{slug}.json"

    def save_game(
        self,
        world: World,
        player: Player,
        furnace: Optional[FurnaceSystem] = None,
    ) -> bool:
        """Persist the complete world, player, inventory, chests, and furnace state."""
        try:
            self.saves_dir.mkdir(parents=True, exist_ok=True)
            save_path = self.get_save_path(world.world_name)

            # Serialize modified blocks (both broken=0 and placed=block_id)
            mod_blocks_dict: Dict[str, int] = {
                f"{wx},{wy},{wz}": int(bid)
                for (wx, wy, wz), bid in world.modified_blocks.items()
            }

            chests_dict: Dict[str, Any] = {
                f"{wx},{wy},{wz}": slots
                for (wx, wy, wz), slots in world.chests.items()
            }

            payload: Dict[str, Any] = {
                "version": 1,
                "world_name": world.world_name,
                "seed": world.seed,
                "difficulty": world.difficulty,
                "world_time": float(world.world_time),
                "day_count": int(world.day_count),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "player": player.to_dict(),
                "modified_blocks": mod_blocks_dict,
                "chests": chests_dict,
                "furnace": furnace.to_dict() if furnace is not None else {},
            }

            # Keep a backup of the previous valid save before overwriting
            if save_path.exists():
                try:
                    bak_path = save_path.with_suffix(".json.bak")
                    bak_path.write_bytes(save_path.read_bytes())
                except Exception:
                    pass

            tmp_path = save_path.with_suffix(".json.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            tmp_path.replace(save_path)
            return True
        except Exception as exc:
            print(f"[SaveManager] Error saving world '{world.world_name}': {exc}")
            return False

    def load_raw_data(self, world_name_or_id: str) -> Optional[Dict[str, Any]]:
        """
        Read and parse a world save file, falling back to `.json.bak` if corrupted.
        Returns None if missing or unrecoverable.
        """
        save_path = self.get_save_path(world_name_or_id)
        candidates = [save_path, save_path.with_suffix(".json.bak")]

        for path in candidates:
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "seed" in data and "player" in data:
                    return data
            except Exception as exc:
                print(f"[SaveManager] Warning: Corrupted save file '{path.name}' ({exc}).")
                continue

        return None

    def apply_loaded_data(
        self,
        data: Dict[str, Any],
        world: World,
        player: Player,
        furnace: Optional[FurnaceSystem] = None,
    ) -> bool:
        """Restore world modifications, time, chests, furnace, and player state from loaded save dict."""
        try:
            world.world_name = str(data.get("world_name", world.world_name))
            world.difficulty = str(data.get("difficulty", world.difficulty))
            world.world_time = float(data.get("world_time", 8.0)) % 24.0
            world.day_count = max(1, int(data.get("day_count", 1)))

            # Restore modified blocks
            world.modified_blocks.clear()
            raw_mods = data.get("modified_blocks", {})
            if isinstance(raw_mods, dict):
                for coord_str, bid in raw_mods.items():
                    parts = str(coord_str).split(",")
                    if len(parts) == 3:
                        wx, wy, wz = int(parts[0]), int(parts[1]), int(parts[2])
                        world.modified_blocks[(wx, wy, wz)] = int(bid)

            # Restore chests
            world.chests.clear()
            raw_chests = data.get("chests", {})
            if isinstance(raw_chests, dict):
                for coord_str, slots in raw_chests.items():
                    parts = str(coord_str).split(",")
                    if len(parts) == 3 and isinstance(slots, list):
                        wx, wy, wz = int(parts[0]), int(parts[1]), int(parts[2])
                        world.chests[(wx, wy, wz)] = slots

            # Restore furnace
            if furnace is not None and isinstance(data.get("furnace"), dict):
                furnace.load_from_dict(data["furnace"])

            # Restore player & inventory
            player.load_from_dict(data.get("player"))
            return True
        except Exception as exc:
            print(f"[SaveManager] Error applying loaded world data: {exc}")
            return False

    def list_saved_worlds(self) -> List[Dict[str, Any]]:
        """Return metadata for all valid saved worlds in `saves/`."""
        results: List[Dict[str, Any]] = []
        if not self.saves_dir.exists():
            return results

        for path in sorted(self.saves_dir.glob("*.json")):
            if path.name == "settings.json":
                continue
            data = self.load_raw_data(path.stem)
            if data is not None:
                results.append({
                    "slug": path.stem,
                    "world_name": str(data.get("world_name", path.stem)),
                    "seed": str(data.get("seed", "PyCraft2026")),
                    "difficulty": str(data.get("difficulty", "Normal")),
                    "timestamp": str(data.get("timestamp", "Unknown")),
                    "day_count": int(data.get("day_count", 1)),
                })
        return results

    def delete_world(self, world_name_or_id: str) -> bool:
        """Delete a saved world and its backup file."""
        save_path = self.get_save_path(world_name_or_id)
        bak_path = save_path.with_suffix(".json.bak")
        removed = False
        try:
            if save_path.exists():
                save_path.unlink()
                removed = True
            if bak_path.exists():
                bak_path.unlink()
                removed = True
        except Exception as exc:
            print(f"[SaveManager] Could not delete world '{world_name_or_id}': {exc}")
        return removed
