"""
Data-driven Crafting System.
Defines recipes for blocks, tools, weapons, torches, furnace, and utilities.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from game.blocks import get_item_def
from game.inventory import Inventory


@dataclass(frozen=True)
class CraftingRecipe:
    id: str
    name: str
    result_item: str
    result_count: int
    ingredients: Dict[str, int]
    requires_table: bool = False

    def format_ingredients(self) -> str:
        parts = []
        for item_key, cnt in self.ingredients.items():
            idef = get_item_def(item_key)
            label = idef.name if idef else item_key
            parts.append(f"{cnt}x {label}")
        return " + ".join(parts)


# Data-driven list of crafting recipes (easily extensible)
RECIPES: List[CraftingRecipe] = [
    CraftingRecipe(
        id="planks",
        name="Wooden Planks (x4)",
        result_item="planks",
        result_count=4,
        ingredients={"wood": 1},
        requires_table=False,
    ),
    CraftingRecipe(
        id="stick",
        name="Sticks (x4)",
        result_item="stick",
        result_count=4,
        ingredients={"planks": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="crafting_table",
        name="Crafting Table",
        result_item="crafting_table",
        result_count=1,
        ingredients={"planks": 4},
        requires_table=False,
    ),
    CraftingRecipe(
        id="torch",
        name="Torches (x4)",
        result_item="torch",
        result_count=4,
        ingredients={"coal": 1, "stick": 1},
        requires_table=False,
    ),
    CraftingRecipe(
        id="furnace",
        name="Furnace",
        result_item="furnace",
        result_count=1,
        ingredients={"stone": 8},
        requires_table=False,
    ),
    CraftingRecipe(
        id="chest",
        name="Chest",
        result_item="chest",
        result_count=1,
        ingredients={"planks": 8},
        requires_table=False,
    ),
    CraftingRecipe(
        id="wooden_pickaxe",
        name="Wooden Pickaxe",
        result_item="wooden_pickaxe",
        result_count=1,
        ingredients={"planks": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="stone_pickaxe",
        name="Stone Pickaxe",
        result_item="stone_pickaxe",
        result_count=1,
        ingredients={"stone": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="iron_pickaxe",
        name="Iron Pickaxe",
        result_item="iron_pickaxe",
        result_count=1,
        ingredients={"iron_ingot": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="diamond_pickaxe",
        name="Diamond Pickaxe",
        result_item="diamond_pickaxe",
        result_count=1,
        ingredients={"diamond": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="wooden_axe",
        name="Wooden Axe",
        result_item="wooden_axe",
        result_count=1,
        ingredients={"planks": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="stone_axe",
        name="Stone Axe",
        result_item="stone_axe",
        result_count=1,
        ingredients={"stone": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="iron_axe",
        name="Iron Axe",
        result_item="iron_axe",
        result_count=1,
        ingredients={"iron_ingot": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="diamond_axe",
        name="Diamond Axe",
        result_item="diamond_axe",
        result_count=1,
        ingredients={"diamond": 3, "stick": 2},
        requires_table=False,
    ),
    CraftingRecipe(
        id="wooden_sword",
        name="Wooden Sword",
        result_item="wooden_sword",
        result_count=1,
        ingredients={"planks": 2, "stick": 1},
        requires_table=False,
    ),
    CraftingRecipe(
        id="stone_sword",
        name="Stone Sword",
        result_item="stone_sword",
        result_count=1,
        ingredients={"stone": 2, "stick": 1},
        requires_table=False,
    ),
    CraftingRecipe(
        id="iron_sword",
        name="Iron Sword",
        result_item="iron_sword",
        result_count=1,
        ingredients={"iron_ingot": 2, "stick": 1},
        requires_table=False,
    ),
    CraftingRecipe(
        id="diamond_sword",
        name="Diamond Sword",
        result_item="diamond_sword",
        result_count=1,
        ingredients={"diamond": 2, "stick": 1},
        requires_table=False,
    ),
    CraftingRecipe(
        id="glass_craft",
        name="Glass (x2)",
        result_item="glass",
        result_count=2,
        ingredients={"sand": 2, "coal": 1},
        requires_table=False,
    ),
]

RECIPES_BY_ID: Dict[str, CraftingRecipe] = {r.id: r for r in RECIPES}


class CraftingSystem:
    """Provides recipe lookup, craftability checks, and item crafting execution."""

    def __init__(self, recipes: Optional[List[CraftingRecipe]] = None):
        self.recipes: List[CraftingRecipe] = list(recipes) if recipes is not None else list(RECIPES)
        self.by_id: Dict[str, CraftingRecipe] = {r.id: r for r in self.recipes}

    def add_recipe(self, recipe: CraftingRecipe) -> None:
        self.recipes.append(recipe)
        self.by_id[recipe.id] = recipe

    def can_craft(self, recipe_or_id, inventory: Inventory) -> bool:
        recipe = self.by_id.get(recipe_or_id) if isinstance(recipe_or_id, str) else recipe_or_id
        if recipe is None:
            return False
        return inventory.has_items(recipe.ingredients)

    def craft(self, recipe_or_id, inventory: Inventory) -> bool:
        """
        Consume recipe ingredients from `inventory` and add the crafted result.
        Returns True if successful, False if ingredients are missing or inventory is full.
        """
        recipe = self.by_id.get(recipe_or_id) if isinstance(recipe_or_id, str) else recipe_or_id
        if recipe is None:
            return False
        if not self.can_craft(recipe, inventory):
            return False

        # Consume ingredients
        for item_key, cnt in recipe.ingredients.items():
            inventory.remove_item(item_key, cnt)

        # Add crafted output
        leftover = inventory.add_item(recipe.result_item, recipe.result_count)
        if leftover > 0:
            # Refund if inventory had no space
            for item_key, cnt in recipe.ingredients.items():
                inventory.add_item(item_key, cnt)
            return False

        return True
