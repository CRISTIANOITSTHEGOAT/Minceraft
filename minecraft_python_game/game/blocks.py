"""
Block and Item definitions, properties, mining speeds, and atlas UV mappings.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# Block numeric IDs (stored in uint8 chunk arrays)
AIR = 0
GRASS = 1
DIRT = 2
STONE = 3
SAND = 4
GRAVEL = 5
WOOD = 6
LEAVES = 7
GLASS = 8
COAL_ORE = 9
IRON_ORE = 10
GOLD_ORE = 11
DIAMOND_ORE = 12
WATER = 13
BEDROCK = 14
PLANKS = 15
CRAFTING_TABLE = 16
FURNACE = 17
TORCH = 18
CHEST = 19
COBBLESTONE = 20

# Atlas grid size (16x16 tiles, each 16x16 pixels -> 256x256 image)
ATLAS_COLS = 16
ATLAS_ROWS = 16
TILE_PIXEL_SIZE = 16

# Tile coordinates (col, row) in the texture atlas (row 0 is top of image)
TILE_COORDS: Dict[str, Tuple[int, int]] = {
    "grass_top": (0, 0),
    "grass_side": (1, 0),
    "dirt": (2, 0),
    "stone": (3, 0),
    "sand": (4, 0),
    "gravel": (5, 0),
    "wood_side": (6, 0),
    "wood_top": (7, 0),
    "leaves": (8, 0),
    "glass": (9, 0),
    "coal_ore": (10, 0),
    "iron_ore": (11, 0),
    "gold_ore": (12, 0),
    "diamond_ore": (13, 0),
    "water": (14, 0),
    "bedrock": (15, 0),
    "planks": (0, 1),
    "crafting_top": (1, 1),
    "crafting_side": (2, 1),
    "furnace_front": (3, 1),
    "furnace_side": (4, 1),
    "furnace_top": (5, 1),
    "torch": (6, 1),
    "chest_front": (7, 1),
    "chest_side": (8, 1),
    "chest_top": (9, 1),
    "cobblestone": (10, 1),
}


@dataclass(frozen=True)
class BlockDef:
    id: int
    key: str
    name: str
    solid: bool = True
    transparent: bool = False
    liquid: bool = False
    unbreakable: bool = False
    hardness: float = 1.0  # Base time in seconds to mine by hand
    preferred_tool: Optional[str] = None  # 'pickaxe', 'axe', 'shovel', or None
    drop_item: Optional[str] = None
    drop_count: int = 1
    faces: Dict[str, str] = field(default_factory=dict)  # 'top','bottom','side','front' -> tile name
    base_color: Tuple[int, int, int] = (180, 180, 180)
    light_emission: int = 0

    def get_tile(self, face: str) -> Tuple[int, int]:
        if face in self.faces:
            tname = self.faces[face]
        elif face in ("north", "south", "east", "west") and "side" in self.faces:
            tname = self.faces["side"]
        else:
            tname = next(iter(self.faces.values()), "stone")
        return TILE_COORDS.get(tname, (3, 0))


@dataclass(frozen=True)
class ItemDef:
    key: str
    name: str
    category: str  # 'block', 'tool', 'weapon', 'material', 'food'
    max_stack: int = 64
    block_id: Optional[int] = None
    tool_type: Optional[str] = None  # 'pickaxe', 'axe', 'sword'
    tool_tier: int = 0  # 1=wood, 2=stone, 3=iron, 4=diamond
    mining_speed: float = 1.0
    attack_damage: float = 2.0
    max_durability: Optional[int] = None
    food_restore: int = 0
    fuel_time: float = 0.0  # Seconds of burn time in furnace
    icon_color: Tuple[int, int, int] = (200, 200, 200)


# Registry of all blocks
BLOCKS_BY_ID: Dict[int, BlockDef] = {
    AIR: BlockDef(
        id=AIR,
        key="air",
        name="Air",
        solid=False,
        transparent=True,
        hardness=0.0,
        drop_item=None,
        faces={},
        base_color=(0, 0, 0),
    ),
    GRASS: BlockDef(
        id=GRASS,
        key="grass",
        name="Grass Block",
        solid=True,
        transparent=False,
        hardness=0.5,
        preferred_tool="shovel",
        drop_item="grass",
        faces={"top": "grass_top", "bottom": "dirt", "side": "grass_side"},
        base_color=(95, 168, 62),
    ),
    DIRT: BlockDef(
        id=DIRT,
        key="dirt",
        name="Dirt",
        solid=True,
        transparent=False,
        hardness=0.45,
        preferred_tool="shovel",
        drop_item="dirt",
        faces={"top": "dirt", "bottom": "dirt", "side": "dirt"},
        base_color=(134, 96, 67),
    ),
    STONE: BlockDef(
        id=STONE,
        key="stone",
        name="Stone",
        solid=True,
        transparent=False,
        hardness=1.8,
        preferred_tool="pickaxe",
        drop_item="stone",
        faces={"top": "stone", "bottom": "stone", "side": "stone"},
        base_color=(128, 128, 132),
    ),
    SAND: BlockDef(
        id=SAND,
        key="sand",
        name="Sand",
        solid=True,
        transparent=False,
        hardness=0.45,
        preferred_tool="shovel",
        drop_item="sand",
        faces={"top": "sand", "bottom": "sand", "side": "sand"},
        base_color=(222, 208, 148),
    ),
    GRAVEL: BlockDef(
        id=GRAVEL,
        key="gravel",
        name="Gravel",
        solid=True,
        transparent=False,
        hardness=0.55,
        preferred_tool="shovel",
        drop_item="gravel",
        faces={"top": "gravel", "bottom": "gravel", "side": "gravel"},
        base_color=(138, 132, 128),
    ),
    WOOD: BlockDef(
        id=WOOD,
        key="wood",
        name="Wood Log",
        solid=True,
        transparent=False,
        hardness=1.0,
        preferred_tool="axe",
        drop_item="wood",
        faces={"top": "wood_top", "bottom": "wood_top", "side": "wood_side"},
        base_color=(112, 82, 48),
    ),
    LEAVES: BlockDef(
        id=LEAVES,
        key="leaves",
        name="Leaves",
        solid=True,
        transparent=True,
        hardness=0.25,
        preferred_tool="axe",
        drop_item="leaves",
        faces={"top": "leaves", "bottom": "leaves", "side": "leaves"},
        base_color=(58, 132, 44),
    ),
    GLASS: BlockDef(
        id=GLASS,
        key="glass",
        name="Glass",
        solid=True,
        transparent=True,
        hardness=0.35,
        preferred_tool="pickaxe",
        drop_item="glass",
        faces={"top": "glass", "bottom": "glass", "side": "glass"},
        base_color=(190, 235, 245),
    ),
    COAL_ORE: BlockDef(
        id=COAL_ORE,
        key="coal_ore",
        name="Coal Ore",
        solid=True,
        transparent=False,
        hardness=2.0,
        preferred_tool="pickaxe",
        drop_item="coal",
        faces={"top": "coal_ore", "bottom": "coal_ore", "side": "coal_ore"},
        base_color=(70, 70, 75),
    ),
    IRON_ORE: BlockDef(
        id=IRON_ORE,
        key="iron_ore",
        name="Iron Ore",
        solid=True,
        transparent=False,
        hardness=2.3,
        preferred_tool="pickaxe",
        drop_item="iron_ore",
        faces={"top": "iron_ore", "bottom": "iron_ore", "side": "iron_ore"},
        base_color=(182, 145, 122),
    ),
    GOLD_ORE: BlockDef(
        id=GOLD_ORE,
        key="gold_ore",
        name="Gold Ore",
        solid=True,
        transparent=False,
        hardness=2.7,
        preferred_tool="pickaxe",
        drop_item="gold_ore",
        faces={"top": "gold_ore", "bottom": "gold_ore", "side": "gold_ore"},
        base_color=(235, 200, 65),
    ),
    DIAMOND_ORE: BlockDef(
        id=DIAMOND_ORE,
        key="diamond_ore",
        name="Diamond Ore",
        solid=True,
        transparent=False,
        hardness=3.2,
        preferred_tool="pickaxe",
        drop_item="diamond",
        faces={"top": "diamond_ore", "bottom": "diamond_ore", "side": "diamond_ore"},
        base_color=(80, 225, 235),
    ),
    WATER: BlockDef(
        id=WATER,
        key="water",
        name="Water",
        solid=False,
        transparent=True,
        liquid=True,
        unbreakable=True,
        hardness=999.0,
        drop_item=None,
        faces={"top": "water", "bottom": "water", "side": "water"},
        base_color=(42, 118, 212),
    ),
    BEDROCK: BlockDef(
        id=BEDROCK,
        key="bedrock",
        name="Bedrock",
        solid=True,
        transparent=False,
        unbreakable=True,
        hardness=float("inf"),
        drop_item=None,
        faces={"top": "bedrock", "bottom": "bedrock", "side": "bedrock"},
        base_color=(45, 45, 50),
    ),
    PLANKS: BlockDef(
        id=PLANKS,
        key="planks",
        name="Wooden Planks",
        solid=True,
        transparent=False,
        hardness=0.9,
        preferred_tool="axe",
        drop_item="planks",
        faces={"top": "planks", "bottom": "planks", "side": "planks"},
        base_color=(172, 134, 82),
    ),
    CRAFTING_TABLE: BlockDef(
        id=CRAFTING_TABLE,
        key="crafting_table",
        name="Crafting Table",
        solid=True,
        transparent=False,
        hardness=1.1,
        preferred_tool="axe",
        drop_item="crafting_table",
        faces={"top": "crafting_top", "bottom": "planks", "side": "crafting_side"},
        base_color=(158, 110, 64),
    ),
    FURNACE: BlockDef(
        id=FURNACE,
        key="furnace",
        name="Furnace",
        solid=True,
        transparent=False,
        hardness=2.0,
        preferred_tool="pickaxe",
        drop_item="furnace",
        faces={"top": "furnace_top", "bottom": "furnace_top", "north": "furnace_front", "side": "furnace_side"},
        base_color=(112, 112, 118),
    ),
    TORCH: BlockDef(
        id=TORCH,
        key="torch",
        name="Torch",
        solid=False,
        transparent=True,
        hardness=0.1,
        drop_item="torch",
        faces={"top": "torch", "bottom": "torch", "side": "torch"},
        base_color=(255, 210, 80),
        light_emission=14,
    ),
    CHEST: BlockDef(
        id=CHEST,
        key="chest",
        name="Chest",
        solid=True,
        transparent=False,
        hardness=1.1,
        preferred_tool="axe",
        drop_item="chest",
        faces={"top": "chest_top", "bottom": "chest_top", "north": "chest_front", "side": "chest_side"},
        base_color=(168, 118, 52),
    ),
    COBBLESTONE: BlockDef(
        id=COBBLESTONE,
        key="cobblestone",
        name="Cobblestone",
        solid=True,
        transparent=False,
        hardness=1.8,
        preferred_tool="pickaxe",
        drop_item="cobblestone",
        faces={"top": "cobblestone", "bottom": "cobblestone", "side": "cobblestone"},
        base_color=(115, 115, 118),
    ),
}

BLOCKS_BY_KEY: Dict[str, BlockDef] = {b.key: b for b in BLOCKS_BY_ID.values()}


# Build Item Registry (includes all placeable blocks + tools + weapons + materials + foods)
ITEMS: Dict[str, ItemDef] = {}

# 1. Register placeable block items
for b_id, b_def in BLOCKS_BY_ID.items():
    if b_id in (AIR, WATER):
        continue
    fuel = 0.0
    if b_def.key == "wood":
        fuel = 6.0
    elif b_def.key == "planks":
        fuel = 4.5
    ITEMS[b_def.key] = ItemDef(
        key=b_def.key,
        name=b_def.name,
        category="block",
        max_stack=64,
        block_id=b_id,
        attack_damage=2.0,
        fuel_time=fuel,
        icon_color=b_def.base_color,
    )

# 2. Register Materials & Resources
_MATERIALS = [
    ItemDef("stick", "Stick", "material", max_stack=64, fuel_time=2.0, icon_color=(160, 122, 72)),
    ItemDef("coal", "Coal", "material", max_stack=64, fuel_time=24.0, icon_color=(42, 42, 48)),
    ItemDef("iron_ingot", "Iron Ingot", "material", max_stack=64, icon_color=(215, 218, 224)),
    ItemDef("gold_ingot", "Gold Ingot", "material", max_stack=64, icon_color=(248, 212, 62)),
    ItemDef("diamond", "Diamond", "material", max_stack=64, icon_color=(82, 236, 245)),
    ItemDef("bone", "Bone", "material", max_stack=64, icon_color=(235, 232, 220)),
]

# 3. Register Foods
_FOODS = [
    ItemDef("raw_pork", "Raw Porkchop", "food", max_stack=64, food_restore=3, icon_color=(235, 145, 145)),
    ItemDef("cooked_pork", "Cooked Porkchop", "food", max_stack=64, food_restore=8, icon_color=(185, 108, 72)),
    ItemDef("raw_beef", "Raw Beef", "food", max_stack=64, food_restore=3, icon_color=(205, 78, 78)),
    ItemDef("cooked_beef", "Steak", "food", max_stack=64, food_restore=8, icon_color=(142, 76, 48)),
    ItemDef("apple", "Apple", "food", max_stack=64, food_restore=4, icon_color=(225, 52, 52)),
    ItemDef("rotten_flesh", "Rotten Flesh", "food", max_stack=64, food_restore=2, icon_color=(142, 88, 64)),
]

# 4. Register Tools & Weapons (All 12 required tools with durability, speed, and damage)
_TOOLS = [
    # Pickaxes
    ItemDef(
        "wooden_pickaxe", "Wooden Pickaxe", "tool", max_stack=1,
        tool_type="pickaxe", tool_tier=1, mining_speed=2.4, attack_damage=3.0,
        max_durability=60, fuel_time=4.0, icon_color=(168, 128, 76),
    ),
    ItemDef(
        "stone_pickaxe", "Stone Pickaxe", "tool", max_stack=1,
        tool_type="pickaxe", tool_tier=2, mining_speed=3.8, attack_damage=4.0,
        max_durability=132, icon_color=(138, 140, 145),
    ),
    ItemDef(
        "iron_pickaxe", "Iron Pickaxe", "tool", max_stack=1,
        tool_type="pickaxe", tool_tier=3, mining_speed=6.0, attack_damage=5.0,
        max_durability=250, icon_color=(215, 220, 228),
    ),
    ItemDef(
        "diamond_pickaxe", "Diamond Pickaxe", "tool", max_stack=1,
        tool_type="pickaxe", tool_tier=4, mining_speed=8.5, attack_damage=6.0,
        max_durability=1561, icon_color=(78, 232, 242),
    ),
    # Axes
    ItemDef(
        "wooden_axe", "Wooden Axe", "tool", max_stack=1,
        tool_type="axe", tool_tier=1, mining_speed=2.4, attack_damage=4.0,
        max_durability=60, fuel_time=4.0, icon_color=(168, 128, 76),
    ),
    ItemDef(
        "stone_axe", "Stone Axe", "tool", max_stack=1,
        tool_type="axe", tool_tier=2, mining_speed=3.8, attack_damage=5.0,
        max_durability=132, icon_color=(138, 140, 145),
    ),
    ItemDef(
        "iron_axe", "Iron Axe", "tool", max_stack=1,
        tool_type="axe", tool_tier=3, mining_speed=6.0, attack_damage=6.0,
        max_durability=250, icon_color=(215, 220, 228),
    ),
    ItemDef(
        "diamond_axe", "Diamond Axe", "tool", max_stack=1,
        tool_type="axe", tool_tier=4, mining_speed=8.5, attack_damage=7.0,
        max_durability=1561, icon_color=(78, 232, 242),
    ),
    # Swords
    ItemDef(
        "wooden_sword", "Wooden Sword", "weapon", max_stack=1,
        tool_type="sword", tool_tier=1, mining_speed=1.5, attack_damage=6.0,
        max_durability=60, fuel_time=4.0, icon_color=(168, 128, 76),
    ),
    ItemDef(
        "stone_sword", "Stone Sword", "weapon", max_stack=1,
        tool_type="sword", tool_tier=2, mining_speed=1.5, attack_damage=8.0,
        max_durability=132, icon_color=(138, 140, 145),
    ),
    ItemDef(
        "iron_sword", "Iron Sword", "weapon", max_stack=1,
        tool_type="sword", tool_tier=3, mining_speed=1.5, attack_damage=10.0,
        max_durability=250, icon_color=(215, 220, 228),
    ),
    ItemDef(
        "diamond_sword", "Diamond Sword", "weapon", max_stack=1,
        tool_type="sword", tool_tier=4, mining_speed=1.5, attack_damage=14.0,
        max_durability=1561, icon_color=(78, 232, 242),
    ),
]

for _item in _MATERIALS + _FOODS + _TOOLS:
    ITEMS[_item.key] = _item


def get_block_by_id(block_id: int) -> BlockDef:
    return BLOCKS_BY_ID.get(int(block_id), BLOCKS_BY_ID[AIR])


def get_block_by_key(key: str) -> Optional[BlockDef]:
    return BLOCKS_BY_KEY.get(key)


def get_item_def(key: Optional[str]) -> Optional[ItemDef]:
    if not key:
        return None
    return ITEMS.get(key)


def calculate_mining_time(block_id: int, held_item_key: Optional[str] = None) -> float:
    """
    Calculate the time in seconds required to mine a block with the given held item.
    Returns float('inf') for unbreakable blocks (e.g. Bedrock, Water).
    """
    block = get_block_by_id(block_id)
    if block.unbreakable or block.id == AIR:
        return float("inf")

    base_time = max(0.08, block.hardness)
    item = get_item_def(held_item_key)
    if item is None:
        return base_time

    # Check if held tool matches the block's preferred tool
    if block.preferred_tool and item.tool_type == block.preferred_tool:
        return max(0.06, base_time / item.mining_speed)

    # Swords slice leaves slightly faster
    if item.tool_type == "sword" and block.id == LEAVES:
        return max(0.05, base_time / 2.0)

    return base_time


def get_attack_damage(held_item_key: Optional[str] = None) -> float:
    """Return melee attack damage when holding the given item (default 2.0 for fist)."""
    item = get_item_def(held_item_key)
    if item is None:
        return 2.0
    return float(item.attack_damage)


def get_tile_uvs(col: int, row: int) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
    """
    Compute the 4 UV coordinates (bottom-left, bottom-right, top-right, top-left)
    in Ursina/Panda3D UV space (where V=0 is bottom of image, V=1 is top of image)
    with a small inset padding to prevent texture bleeding at tile edges.
    """
    pad = 0.0015
    u0 = (col / ATLAS_COLS) + pad
    u1 = ((col + 1) / ATLAS_COLS) - pad
    # In PIL image, row 0 is at the top, which corresponds to V near 1.0 in OpenGL/Panda3D
    v_top = 1.0 - (row / ATLAS_ROWS) - pad
    v_bot = 1.0 - ((row + 1) / ATLAS_ROWS) + pad
    return ((u0, v_bot), (u1, v_bot), (u1, v_top), (u0, v_top))
