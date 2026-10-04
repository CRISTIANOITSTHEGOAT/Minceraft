# PyCraft — Voxel Survival Sandbox in Python

An original, playable 3D Minecraft-inspired voxel survival sandbox game written in Python using the **Ursina Engine (Panda3D)**, **NumPy**, and **Pillow**.

All textures, icons, sound effects, and 3D models are generated procedurally—no external or proprietary assets are required.

---

## 1. Python Version

- **Python 3.10+** (Tested on **Python 3.10 – 3.13**)
- Cross-platform: runs on Windows, macOS, and Linux.

---

## 2. Installation Command

Unpack `minecraft_python_game.zip` (or clone/open the project directory) and navigate into the project folder:

```bash
unzip minecraft_python_game.zip -d pycraft
cd pycraft
```

---

## 3. How to Install Dependencies

Create an optional virtual environment and install the required packages from `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## 4. How to Launch the Game

Run `main.py` with Python:

```bash
python3 main.py
```

*(Note: If running in a headless CI/container environment without an X11/Wayland display, you can run `python3 main.py --headless` or `xvfb-run -a python3 main.py`.)*

---

## 5. Controls

| Input | Action |
| :--- | :--- |
| **W / S / A / D** | Walk Forward / Backward / Strafe Left / Strafe Right |
| **Shift** (hold) | Sprint (moves faster, consumes slightly more hunger) |
| **Space** | Jump (or Swim Upward while in water) |
| **Mouse** | First-person camera look |
| **Left Mouse** (hold / click) | Break targeted block (with mining progress bar) or Melee Attack targeted mob |
| **Right Mouse** | Place selected block, open targeted Crafting Table / Furnace, or eat held food |
| **1 – 9** | Select Hotbar slot (1–9) |
| **Mouse Wheel** | Cycle Hotbar slot selection |
| **E** | Open / Close Inventory, Crafting, and Furnace screen |
| **F** | Eat currently selected food item |
| **Esc** | Open Pause Menu or close open Inventory/Settings screen |

---

## 6. Save Location

All world saves and persistent user settings are stored locally in the `saves/` directory at the project root:

- **World Saves**: `saves/<world_name>.json` (with automatic `.json.bak` recovery backup)
  - Stores world name, deterministic seed, difficulty, world time & day count, player position/orientation, health, hunger, 36-slot inventory, hotbar selection, broken & placed blocks, chests, and furnace state.
- **Game Settings**: `saves/settings.json`
  - Stores mouse sensitivity, FOV, render distance, master volume, music toggle, SFX toggle, graphics quality, fullscreen mode, and keep-inventory preference.

---

## 7. Project Structure

```text
minecraft_python/
│
├── main.py                  # Game entry point, main loop, and input bindings
├── requirements.txt         # Python package dependencies
├── README.md                # Setup, controls, and architecture guide
│
├── game/
│   ├── __init__.py          # Package metadata
│   ├── assets_gen.py        # Procedural pixel-art texture atlas, icons, WAV sounds, OBJ models
│   ├── blocks.py            # Block & Item definitions, hardness, tool tiers, UVs
│   ├── terrain.py           # Seeded multi-octave 2D & 3D noise terrain, biomes, caves, trees, ores
│   ├── chunk.py             # 16x64x16 chunk storage & hidden-face culled mesh builder
│   ├── world.py             # Dynamic chunk loading/unloading, 3D DDA voxel raycast, day/night sky
│   ├── player.py            # First-person controller, 3D AABB collision, swimming, mining, survival
│   ├── inventory.py         # 36-slot inventory (9 hotbar + 27 backpack), stacking, durability
│   ├── crafting.py          # Data-driven crafting recipes for planks, tools, swords, torches, furnace
│   ├── furnace.py           # Ore smelting & food cooking system (input, fuel, output, progress)
│   ├── combat.py            # Melee combat, weapon damage, cooldowns, ray hit detection, knockback
│   ├── mobs.py              # Passive (Pig, Cow) & Hostile (Zombie, Skeleton) AI mobs & drops
│   ├── save.py              # Atomic JSON world saving, loading, listing, deletion, and recovery
│   ├── settings.py          # Persistent game settings manager
│   └── ui.py                # HUD, Main Menu, World Menu, Settings, Pause, Inventory/Crafting/Furnace, Death UI
│
├── assets/
│   ├── textures/            # Procedurally generated block atlas.png and 32x32 item icons
│   ├── sounds/              # Procedurally synthesized WAV sound effects
│   └── models/              # Wavefront OBJ voxel meshes
│
└── saves/                   # Persistent world saves (*.json) and settings.json
```

---

## Visual Art Pipeline

All art is still generated procedurally (no external assets):

- `game/pixelart.py` – block tiles, isometric block icons, item sprites, mob skins, menu panorama/logo/buttons.
- `game/mob_models.py` – textured, articulated box models for pig, cow, zombie and skeleton.
- `game/ui_widgets.py` – title-screen widgets (animated panorama, bobbing logo, splash text, stone buttons).

Generated PNGs are cached in `assets/textures/`. Bump `ART_VERSION` in `game/pixelart.py` after editing any
generator and they are rebuilt automatically on the next launch.
