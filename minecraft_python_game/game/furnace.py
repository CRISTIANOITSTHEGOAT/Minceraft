"""
Furnace system: supports Input slot, Fuel slot, Output slot, and Smelting progress.
Smelts iron ore -> iron ingot, gold ore -> gold ingot, sand -> glass, and cooks raw food.
"""

from typing import Any, Dict, Optional

from game.blocks import get_item_def
from game.inventory import Inventory, ItemStack

# Smelting mapping: input_item_key -> output_item_key
SMELT_RECIPES: Dict[str, str] = {
    "iron_ore": "iron_ingot",
    "gold_ore": "gold_ingot",
    "raw_pork": "cooked_pork",
    "raw_beef": "cooked_beef",
    "sand": "glass",
    "wood": "coal",
}

# Fuel burn durations in seconds
FUEL_VALUES: Dict[str, float] = {
    "coal": 24.0,
    "wood": 6.0,
    "planks": 4.5,
    "stick": 2.0,
}


class FurnaceSystem:
    """Represents a functional furnace with input, fuel, output slots, and smelting progress."""

    SMELT_DURATION: float = 3.0  # Seconds required to smelt 1 item

    def __init__(self):
        self.input_slot: Optional[ItemStack] = None
        self.fuel_slot: Optional[ItemStack] = None
        self.output_slot: Optional[ItemStack] = None
        self.burn_time: float = 0.0
        self.max_burn_time: float = 1.0
        self.smelt_time: float = 0.0

    @property
    def progress(self) -> float:
        """Smelting progress in [0.0, 1.0]."""
        return min(1.0, max(0.0, self.smelt_time / self.SMELT_DURATION))

    @property
    def fuel_progress(self) -> float:
        """Remaining fuel burn fraction in [0.0, 1.0]."""
        if self.max_burn_time <= 0:
            return 0.0
        return min(1.0, max(0.0, self.burn_time / self.max_burn_time))

    def can_smelt_current(self) -> bool:
        if self.input_slot is None or self.input_slot.count <= 0:
            return False
        result_key = SMELT_RECIPES.get(self.input_slot.item_id)
        if not result_key:
            return False
        if self.output_slot is None:
            return True
        if self.output_slot.item_id != result_key:
            return False
        return self.output_slot.count < self.output_slot.max_stack

    def update(self, dt: float) -> None:
        """Advance fuel burning and smelting progress by `dt` seconds."""
        dt = max(0.0, float(dt))
        if self.burn_time > 0.0:
            self.burn_time = max(0.0, self.burn_time - dt)

        if self.can_smelt_current():
            # Consume 1 fuel item if fire is out and fuel is available
            if self.burn_time <= 0.0 and self.fuel_slot is not None and self.fuel_slot.count > 0:
                f_val = FUEL_VALUES.get(self.fuel_slot.item_id, 0.0)
                if f_val > 0.0:
                    self.burn_time = f_val
                    self.max_burn_time = f_val
                    self.fuel_slot.count -= 1
                    if self.fuel_slot.count <= 0:
                        self.fuel_slot = None

            if self.burn_time > 0.0:
                self.smelt_time += dt
                while self.smelt_time >= self.SMELT_DURATION and self.can_smelt_current():
                    self.smelt_time -= self.SMELT_DURATION
                    self._complete_one_smelt()
            else:
                self.smelt_time = max(0.0, self.smelt_time - dt * 0.5)
        else:
            self.smelt_time = 0.0

    def _complete_one_smelt(self) -> None:
        if self.input_slot is None:
            return
        result_key = SMELT_RECIPES.get(self.input_slot.item_id)
        if not result_key:
            return
        self.input_slot.count -= 1
        if self.input_slot.count <= 0:
            self.input_slot = None

        if self.output_slot is None:
            self.output_slot = ItemStack(item_id=result_key, count=1)
        else:
            self.output_slot.count += 1

    def add_input_from_inventory(self, inventory: Inventory, item_key: Optional[str] = None, count: int = 1) -> bool:
        """Move smeltable items from player inventory into the furnace input slot."""
        candidates = [item_key] if item_key else list(SMELT_RECIPES.keys())
        for cand in candidates:
            if not cand or cand not in SMELT_RECIPES:
                continue
            if self.input_slot is not None and self.input_slot.item_id != cand:
                continue
            avail = inventory.count_item(cand)
            if avail <= 0:
                continue
            to_move = min(count, avail)
            if self.input_slot is not None:
                to_move = min(to_move, self.input_slot.max_stack - self.input_slot.count)
            if to_move <= 0:
                continue
            inventory.remove_item(cand, to_move)
            if self.input_slot is None:
                self.input_slot = ItemStack(item_id=cand, count=to_move)
            else:
                self.input_slot.count += to_move
            return True
        return False

    def add_fuel_from_inventory(self, inventory: Inventory, item_key: Optional[str] = None, count: int = 1) -> bool:
        """Move fuel items from player inventory into the furnace fuel slot."""
        candidates = [item_key] if item_key else list(FUEL_VALUES.keys())
        for cand in candidates:
            if not cand or cand not in FUEL_VALUES:
                continue
            if self.fuel_slot is not None and self.fuel_slot.item_id != cand:
                continue
            avail = inventory.count_item(cand)
            if avail <= 0:
                continue
            to_move = min(count, avail)
            if self.fuel_slot is not None:
                to_move = min(to_move, self.fuel_slot.max_stack - self.fuel_slot.count)
            if to_move <= 0:
                continue
            inventory.remove_item(cand, to_move)
            if self.fuel_slot is None:
                self.fuel_slot = ItemStack(item_id=cand, count=to_move)
            else:
                self.fuel_slot.count += to_move
            return True
        return False

    def collect_output(self, inventory: Inventory) -> int:
        """Move smelted output items into the player's inventory. Returns count collected."""
        if self.output_slot is None or self.output_slot.count <= 0:
            return 0
        total = self.output_slot.count
        leftover = inventory.add_item(self.output_slot.item_id, total)
        collected = total - leftover
        if leftover <= 0:
            self.output_slot = None
        else:
            self.output_slot.count = leftover
        return collected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_slot": self.input_slot.to_dict() if self.input_slot else None,
            "fuel_slot": self.fuel_slot.to_dict() if self.fuel_slot else None,
            "output_slot": self.output_slot.to_dict() if self.output_slot else None,
            "burn_time": float(self.burn_time),
            "max_burn_time": float(self.max_burn_time),
            "smelt_time": float(self.smelt_time),
        }

    def load_from_dict(self, data: Optional[Dict[str, Any]]) -> None:
        if not data or not isinstance(data, dict):
            return
        self.input_slot = ItemStack.from_dict(data.get("input_slot"))
        self.fuel_slot = ItemStack.from_dict(data.get("fuel_slot"))
        self.output_slot = ItemStack.from_dict(data.get("output_slot"))
        self.burn_time = float(data.get("burn_time", 0.0))
        self.max_burn_time = float(data.get("max_burn_time", 1.0))
        self.smelt_time = float(data.get("smelt_time", 0.0))
