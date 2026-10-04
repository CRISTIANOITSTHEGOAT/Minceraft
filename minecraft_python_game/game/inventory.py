"""
Player Inventory and Hotbar system.
Supports 9 hotbar slots + 27 main inventory slots (36 total), stack limits,
tool durability tracking, item selection, and slot-to-slot movement.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from game.blocks import ItemDef, get_item_def

HOTBAR_SIZE = 9
MAIN_INV_SIZE = 27
TOTAL_SLOTS = HOTBAR_SIZE + MAIN_INV_SIZE


@dataclass
class ItemStack:
    item_id: str
    count: int = 1
    durability: Optional[int] = None

    def __post_init__(self):
        idef = get_item_def(self.item_id)
        if idef is not None and self.durability is None and idef.max_durability is not None:
            self.durability = idef.max_durability

    @property
    def item_def(self) -> Optional[ItemDef]:
        return get_item_def(self.item_id)

    @property
    def max_stack(self) -> int:
        idef = self.item_def
        return idef.max_stack if idef is not None else 64

    @property
    def max_durability(self) -> Optional[int]:
        idef = self.item_def
        return idef.max_durability if idef is not None else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "count": int(self.count),
            "durability": self.durability,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["ItemStack"]:
        if not data or not isinstance(data, dict):
            return None
        item_id = data.get("item_id")
        count = int(data.get("count", 0))
        if not item_id or count <= 0 or get_item_def(item_id) is None:
            return None
        dur = data.get("durability")
        return cls(item_id=str(item_id), count=count, durability=int(dur) if dur is not None else None)


class Inventory:
    """Manages 36 inventory slots (0..8 hotbar, 9..35 main backpack) and cursor item movement."""

    def __init__(self):
        self.slots: List[Optional[ItemStack]] = [None] * TOTAL_SLOTS
        self.selected_slot: int = 0
        self.cursor_stack: Optional[ItemStack] = None

    def clear(self) -> None:
        self.slots = [None] * TOTAL_SLOTS
        self.cursor_stack = None

    def select_slot(self, index: int) -> None:
        if 0 <= index < HOTBAR_SIZE:
            self.selected_slot = int(index)

    def scroll_hotbar(self, delta: int) -> None:
        self.selected_slot = (self.selected_slot + int(delta)) % HOTBAR_SIZE

    def get_selected_stack(self) -> Optional[ItemStack]:
        return self.slots[self.selected_slot]

    def get_selected_item_key(self) -> Optional[str]:
        st = self.get_selected_stack()
        return st.item_id if st is not None else None

    def count_item(self, item_id: str) -> int:
        total = 0
        for st in self.slots:
            if st is not None and st.item_id == item_id:
                total += st.count
        return total

    def has_items(self, requirements: Dict[str, int]) -> bool:
        for item_id, req_count in requirements.items():
            if self.count_item(item_id) < req_count:
                return False
        return True

    def add_item(self, item_id: str, count: int = 1, durability: Optional[int] = None) -> int:
        """
        Add `count` of `item_id` into inventory, respecting stack limits.
        Returns the number of items that could NOT fit (0 if all added).
        """
        idef = get_item_def(item_id)
        if idef is None or count <= 0:
            return count

        remaining = int(count)
        max_st = idef.max_stack

        # 1. Merge into existing non-full stacks first (if stackable)
        if max_st > 1:
            for i in range(TOTAL_SLOTS):
                st = self.slots[i]
                if st is not None and st.item_id == item_id and st.count < max_st:
                    space = max_st - st.count
                    to_add = min(remaining, space)
                    st.count += to_add
                    remaining -= to_add
                    if remaining <= 0:
                        return 0

        # 2. Place into empty slots
        for i in range(TOTAL_SLOTS):
            if self.slots[i] is None:
                to_add = min(remaining, max_st)
                self.slots[i] = ItemStack(item_id=item_id, count=to_add, durability=durability)
                remaining -= to_add
                if remaining <= 0:
                    return 0

        return remaining

    def remove_item(self, item_id: str, count: int = 1) -> bool:
        """Remove `count` of `item_id` across the inventory. Returns False if insufficient."""
        if count <= 0:
            return True
        if self.count_item(item_id) < count:
            return False

        remaining = int(count)
        for i in range(TOTAL_SLOTS):
            st = self.slots[i]
            if st is not None and st.item_id == item_id:
                take = min(remaining, st.count)
                st.count -= take
                remaining -= take
                if st.count <= 0:
                    self.slots[i] = None
                if remaining <= 0:
                    break
        return True

    def consume_selected(self, count: int = 1) -> bool:
        """Consume `count` items from the currently selected hotbar slot."""
        st = self.slots[self.selected_slot]
        if st is None or st.count < count:
            return False
        st.count -= count
        if st.count <= 0:
            self.slots[self.selected_slot] = None
        return True

    def damage_selected_tool(self, amount: int = 1) -> bool:
        """
        Reduce durability of the currently selected tool/weapon.
        Returns True if the tool broke and was removed.
        """
        st = self.slots[self.selected_slot]
        if st is None or st.durability is None:
            return False
        st.durability -= int(amount)
        if st.durability <= 0:
            self.slots[self.selected_slot] = None
            return True
        return False

    def move_slot(self, from_idx: int, to_idx: int) -> bool:
        """Move or merge items from `from_idx` to `to_idx`."""
        if not (0 <= from_idx < TOTAL_SLOTS and 0 <= to_idx < TOTAL_SLOTS):
            return False
        if from_idx == to_idx:
            return True

        src = self.slots[from_idx]
        dst = self.slots[to_idx]
        if src is None:
            return False

        if dst is None:
            self.slots[to_idx] = src
            self.slots[from_idx] = None
            return True

        if src.item_id == dst.item_id and dst.max_stack > 1 and dst.count < dst.max_stack:
            space = dst.max_stack - dst.count
            transfer = min(space, src.count)
            dst.count += transfer
            src.count -= transfer
            if src.count <= 0:
                self.slots[from_idx] = None
            return True

        # Otherwise swap the two slots
        self.slots[from_idx], self.slots[to_idx] = dst, src
        return True

    def click_slot(self, slot_idx: int, right_click: bool = False) -> None:
        """
        Interactive slot click handler for Inventory UI:
        - Left click picks up stack, places stack, merges stacks, or swaps with cursor.
        - Right click splits half a stack when cursor is empty, or places 1 item when cursor holds a stack.
        """
        if not (0 <= slot_idx < TOTAL_SLOTS):
            return

        slot_stack = self.slots[slot_idx]

        if not right_click:
            if self.cursor_stack is None:
                self.cursor_stack = slot_stack
                self.slots[slot_idx] = None
            else:
                if slot_stack is None:
                    self.slots[slot_idx] = self.cursor_stack
                    self.cursor_stack = None
                elif (
                    slot_stack.item_id == self.cursor_stack.item_id
                    and slot_stack.max_stack > 1
                    and slot_stack.count < slot_stack.max_stack
                ):
                    space = slot_stack.max_stack - slot_stack.count
                    move = min(space, self.cursor_stack.count)
                    slot_stack.count += move
                    self.cursor_stack.count -= move
                    if self.cursor_stack.count <= 0:
                        self.cursor_stack = None
                else:
                    self.slots[slot_idx], self.cursor_stack = self.cursor_stack, slot_stack
        else:
            # Right click: split half or place 1
            if self.cursor_stack is None and slot_stack is not None:
                half = (slot_stack.count + 1) // 2
                self.cursor_stack = ItemStack(
                    item_id=slot_stack.item_id,
                    count=half,
                    durability=slot_stack.durability,
                )
                slot_stack.count -= half
                if slot_stack.count <= 0:
                    self.slots[slot_idx] = None
            elif self.cursor_stack is not None:
                if slot_stack is None:
                    self.slots[slot_idx] = ItemStack(
                        item_id=self.cursor_stack.item_id,
                        count=1,
                        durability=self.cursor_stack.durability,
                    )
                    self.cursor_stack.count -= 1
                    if self.cursor_stack.count <= 0:
                        self.cursor_stack = None
                elif (
                    slot_stack.item_id == self.cursor_stack.item_id
                    and slot_stack.max_stack > 1
                    and slot_stack.count < slot_stack.max_stack
                ):
                    slot_stack.count += 1
                    self.cursor_stack.count -= 1
                    if self.cursor_stack.count <= 0:
                        self.cursor_stack = None

    def return_cursor_to_inventory(self) -> None:
        """If the UI closes while holding an item on the cursor, return it to the inventory."""
        if self.cursor_stack is not None:
            self.add_item(
                self.cursor_stack.item_id,
                self.cursor_stack.count,
                self.cursor_stack.durability,
            )
            self.cursor_stack = None

    def to_list(self) -> List[Optional[Dict[str, Any]]]:
        self.return_cursor_to_inventory()
        return [st.to_dict() if st is not None else None for st in self.slots]

    def load_from_list(self, data: Any) -> None:
        self.clear()
        if not isinstance(data, list):
            return
        for i in range(min(TOTAL_SLOTS, len(data))):
            self.slots[i] = ItemStack.from_dict(data[i])
