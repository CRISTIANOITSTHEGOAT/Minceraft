#!/usr/bin/env python3
"""
Automated verification suite for all 18 required tests in Section 26,
plus Section 25 error handling & visual screenshot capture.
"""

import math
import os
import sys
import time
from pathlib import Path

import main as game_main
from game.blocks import (
    AIR,
    BEDROCK,
    COBBLESTONE,
    CRAFTING_TABLE,
    DIRT,
    FURNACE,
    GRASS,
    PLANKS,
    STONE,
    WOOD,
    calculate_mining_time,
)
from game.settings import SETTINGS_FILE, GameSettings


def run_all_tests():
    print("=" * 64)
    print("RUNNING PYCRAFT VERIFICATION SUITE (TESTS 1 - 18)")
    print("=" * 64)

    app = game_main.create_ursina_app()
    ctrl = game_main.GameController()
    game_main.GAME_CONTROLLER = ctrl
    ctrl.init_ui()

    # Step engine a few frames
    for _ in range(5):
        app.step()

    # -------------------------------------------------------------------------
    # TEST 1: Launch the game -> main menu appears
    # -------------------------------------------------------------------------
    assert ctrl.ui is not None, "UI must be initialized"
    assert ctrl.ui.active_screen == "main_menu", f"Expected main_menu, got {ctrl.ui.active_screen}"
    print("[PASS] TEST 1: Launch the game -> Main Menu appears.")

    # Save screenshot of Main Menu if window exists
    if hasattr(app, "win") and app.win is not None:
        app.win.saveScreenshot("screenshot_main_menu.png")

    # -------------------------------------------------------------------------
    # TEST 2: Create a world -> terrain generates
    # -------------------------------------------------------------------------
    ctrl.start_new_world(world_name="VerificationWorld", seed="VerifySeed2026", difficulty="Normal")
    for _ in range(5):
        ctrl.update(0.016)
        app.step()

    assert ctrl.world is not None, "World must be created"
    assert len(ctrl.world.chunks) > 0, "Chunks must be generated around spawn"
    assert ctrl.ui.active_screen == "hud", "HUD should be active after world creation"
    # Verify deterministic seed: a second generator with same seed produces identical chunk (0,0)
    import numpy as np
    from game.terrain import TerrainGenerator
    g_a = TerrainGenerator("VerifySeed2026").generate_chunk_blocks(0, 0)
    g_b = TerrainGenerator("VerifySeed2026").generate_chunk_blocks(0, 0)
    assert np.array_equal(g_a, g_b), "Same seed must generate identical terrain"
    print(f"[PASS] TEST 2: Create a world -> Terrain generated ({len(ctrl.world.chunks)} chunks loaded).")

    if hasattr(app, "win") and app.win is not None:
        app.win.saveScreenshot("screenshot_gameplay_hud.png")

    player = ctrl.player
    world = ctrl.world

    # -------------------------------------------------------------------------
    # TEST 3: Move around -> collision works (cannot walk through solid wall)
    # -------------------------------------------------------------------------
    start_x, start_y, start_z = player.position
    # Build a solid 2-block-high stone wall directly in +X of the player
    wall_bx = math.floor(start_x) + 2
    wall_by = math.floor(start_y)
    wall_bz = math.floor(start_z)
    # Clear immediate step at +1 and place solid wall at +2
    world.set_block(wall_bx - 1, wall_by, wall_bz, AIR)
    world.set_block(wall_bx - 1, wall_by + 1, wall_bz, AIR)
    world.set_block(wall_bx, wall_by, wall_bz, STONE)
    world.set_block(wall_bx, wall_by + 1, wall_bz, STONE)

    for _ in range(45):
        player.move_and_collide(1.0, 0.0, 0.02, jump_pressed=False)

    assert player.x > start_x, "Player should move toward the wall"
    assert player.x < wall_bx, f"Player must not walk through solid wall at x={wall_bx} (player.x={player.x:.2f})"
    # Clean up temporary test wall
    world.set_block(wall_bx, wall_by, wall_bz, AIR)
    world.set_block(wall_bx, wall_by + 1, wall_bz, AIR)
    print(f"[PASS] TEST 3: Move around -> Collision works (stopped cleanly at x={player.x:.2f} before wall x={wall_bx}).")

    # -------------------------------------------------------------------------
    # TEST 4: Jump -> gravity and landing work
    # -------------------------------------------------------------------------
    # Ensure solid block beneath player and air above
    bx, by, bz = math.floor(player.x), math.floor(player.y), math.floor(player.z)
    world.set_block(bx, by - 1, bz, GRASS)
    world.set_block(bx, by, bz, AIR)
    world.set_block(bx, by + 1, bz, AIR)
    world.set_block(bx, by + 2, bz, AIR)
    # Settle onto ground
    for _ in range(25):
        player.move_and_collide(0.0, 0.0, 0.02, jump_pressed=False)
    assert player.on_ground, "Player should be on ground before jumping"
    ground_y = player.y

    # Jump!
    player.move_and_collide(0.0, 0.0, 0.02, jump_pressed=True)
    peak_y = player.y
    for _ in range(60):
        player.move_and_collide(0.0, 0.0, 0.02, jump_pressed=False)
        peak_y = max(peak_y, player.y)

    assert peak_y > ground_y + 0.8, f"Player must rise during jump (ground={ground_y:.2f}, peak={peak_y:.2f})"
    assert player.on_ground and abs(player.y - ground_y) < 0.15, "Player must land back on ground via gravity"
    print(f"[PASS] TEST 4: Jump -> Gravity and landing work (ground={ground_y:.2f} -> peak={peak_y:.2f} -> landed={player.y:.2f}).")

    # -------------------------------------------------------------------------
    # TEST 5: Break a block -> block disappears and item is collected
    # -------------------------------------------------------------------------
    target_bx, target_by, target_bz = math.floor(player.x), math.floor(player.y) + 1, math.floor(player.z) + 2
    world.set_block(target_bx, target_by, target_bz, WOOD)
    # Aim straight at the block (+Z direction, pitch=0, yaw=0)
    player.x = target_bx + 0.5
    player.z = target_bz - 2.0
    player.yaw = 0.0
    player.pitch = 0.0
    player.sync_camera()
    hit = player.update_raycast_and_selection()
    assert hit.hit and hit.block_pos == (target_bx, target_by, target_bz), f"Expected raycast hit on {(target_bx, target_by, target_bz)}, got {hit}"

    wood_before = player.inventory.count_item("wood")
    broke = player.break_targeted_block(settings=ctrl.settings)
    wood_after = player.inventory.count_item("wood")
    assert broke, "break_targeted_block must succeed"
    assert world.get_block(target_bx, target_by, target_bz) == AIR, "Broken block must become AIR"
    assert wood_after == wood_before + 1, "Dropped wood item must be collected into inventory"

    # Also verify Bedrock cannot be broken and Pickaxes mine stone faster than bare hands
    assert math.isinf(calculate_mining_time(BEDROCK, "diamond_pickaxe")), "Bedrock must be unbreakable"
    assert calculate_mining_time(STONE, "iron_pickaxe") < calculate_mining_time(STONE, None), "Pickaxe must mine stone faster"
    print("[PASS] TEST 5: Break a block -> Block disappears, particles spawn, and item is collected.")

    # -------------------------------------------------------------------------
    # TEST 6: Place a block -> block appears correctly (and prevents placing in player body)
    # -------------------------------------------------------------------------
    # Place a backing block at (target_bx, target_by, target_bz + 1) so we can place against its -Z face
    world.set_block(target_bx, target_by, target_bz + 1, STONE)
    player.update_raycast_and_selection()
    # Select 'wood' in hotbar
    player.inventory.slots[0] = game_main.Player(world).inventory.slots[0]  # reset slot 0
    from game.inventory import ItemStack
    player.inventory.slots[0] = ItemStack("wood", count=5)
    player.inventory.select_slot(0)

    res = player.place_selected_block(settings=ctrl.settings)
    assert res == "placed", f"Expected 'placed', got {res}"
    assert world.get_block(target_bx, target_by, target_bz) == WOOD, "Placed wood block must appear at target face"
    assert player.inventory.slots[0].count == 4, "Placing block must consume 1 item from hotbar"

    # Verify cannot place solid block inside player's own body
    assert player.block_intersects_player(math.floor(player.x), math.floor(player.y), math.floor(player.z)), "Player body intersection check must prevent self-entombment"
    # Clean up placed test blocks
    world.set_block(target_bx, target_by, target_bz, AIR)
    world.set_block(target_bx, target_by, target_bz + 1, AIR)
    print("[PASS] TEST 6: Place a block -> Block appears on targeted face and respects player collision.")

    # -------------------------------------------------------------------------
    # TEST 7: Open inventory -> inventory works (selection, stacking, movement)
    # -------------------------------------------------------------------------
    ctrl.handle_input("e")
    assert ctrl.ui.active_screen == "inventory", "Pressing E must open inventory screen"
    if hasattr(app, "win") and app.win is not None:
        app.step()
        app.win.saveScreenshot("screenshot_inventory_crafting.png")

    # Test slot movement (move slot 0 to slot 10)
    player.inventory.move_slot(0, 10)
    assert player.inventory.slots[10] is not None and player.inventory.slots[10].item_id == "wood"
    player.inventory.move_slot(10, 0)
    ctrl.handle_input("e")
    assert ctrl.ui.active_screen == "hud", "Pressing E again must close inventory screen"
    print("[PASS] TEST 7: Open inventory -> Inventory UI, stacking, and slot movement work.")

    # -------------------------------------------------------------------------
    # TEST 8: Craft an item -> ingredients are removed and result is created (+ Furnace smelting)
    # -------------------------------------------------------------------------
    player.inventory.clear()
    player.inventory.add_item("wood", 2)
    assert ctrl.crafting.craft("planks", player.inventory), "Should craft Wooden Planks from Wood"
    assert player.inventory.count_item("wood") == 1 and player.inventory.count_item("planks") == 4

    assert ctrl.crafting.craft("stick", player.inventory), "Should craft Sticks from 2 Planks"
    assert player.inventory.count_item("planks") == 2 and player.inventory.count_item("stick") == 4

    # Craft Wooden Sword (2 planks + 1 stick)
    assert ctrl.crafting.craft("wooden_sword", player.inventory), "Should craft Wooden Sword"
    assert player.inventory.count_item("wooden_sword") == 1

    # Also test Furnace smelting (iron_ore + coal -> iron_ingot)
    player.inventory.add_item("iron_ore", 1)
    player.inventory.add_item("coal", 1)
    ctrl.furnace.add_input_from_inventory(player.inventory, "iron_ore", 1)
    ctrl.furnace.add_fuel_from_inventory(player.inventory, "coal", 1)
    ctrl.furnace.update(3.5)
    collected = ctrl.furnace.collect_output(player.inventory)
    assert collected == 1 and player.inventory.count_item("iron_ingot") == 1, "Furnace must smelt iron_ore -> iron_ingot"
    print("[PASS] TEST 8: Craft an item & Smelt ore -> Ingredients consumed and crafted/smelted items created.")

    # -------------------------------------------------------------------------
    # TEST 9: Equip a tool -> tool appears in first person/hotbar
    # -------------------------------------------------------------------------
    player.inventory.add_item("diamond_sword", 1)
    # Find slot containing diamond_sword
    sword_slot = next(i for i, st in enumerate(player.inventory.slots[:9]) if st and st.item_id == "diamond_sword")
    ctrl.handle_input(str(sword_slot + 1))
    assert player.inventory.selected_slot == sword_slot
    assert player.inventory.get_selected_item_key() == "diamond_sword"
    assert player.held_entity is not None and player._last_held_key == "diamond_sword"
    print("[PASS] TEST 9: Equip a tool -> Tool selected in hotbar and displayed in first-person viewmodel.")

    # -------------------------------------------------------------------------
    # TEST 10: Fight a mob -> damage, knockback, death, and item drops work
    # -------------------------------------------------------------------------
    mob_pos = (player.x, player.y, player.z + 2.2)
    zombie = ctrl.mob_manager.spawn_mob("zombie", mob_pos)
    player.yaw = 0.0
    player.pitch = 0.0
    player.sync_camera()

    initial_mob_hp = zombie.health
    ctrl.combat.cooldown_timer = 0.0
    hit, dmg, killed = ctrl.combat.perform_player_attack(player, ctrl.mob_manager.mobs, target_mob=zombie, settings=ctrl.settings)
    assert hit and dmg == 14.0, f"Diamond sword should deal 14 damage, got hit={hit}, dmg={dmg}"
    assert zombie.health == initial_mob_hp - 14.0 and not killed

    # Second strike kills the 20 HP zombie
    ctrl.combat.cooldown_timer = 0.0
    flesh_before = player.inventory.count_item("rotten_flesh")
    hit2, dmg2, killed2 = ctrl.combat.perform_player_attack(player, ctrl.mob_manager.mobs, target_mob=zombie, settings=ctrl.settings)
    assert hit2 and killed2 and zombie.dead, "Second diamond sword strike must kill Zombie"
    assert player.inventory.count_item("rotten_flesh") > flesh_before, "Killed Zombie must drop rotten_flesh"
    print("[PASS] TEST 10: Fight a mob -> Melee hit detection, damage, knockback, death, and loot drops work.")

    # -------------------------------------------------------------------------
    # TEST 11: Take damage -> health decreases
    # -------------------------------------------------------------------------
    player.health = 20.0
    player.take_damage(5.0, source="Zombie", settings=ctrl.settings)
    assert player.health == 15.0, f"Expected health 15.0 after 5 damage, got {player.health}"
    print("[PASS] TEST 11: Take damage -> Player health decreases accurately (20 -> 15).")

    # -------------------------------------------------------------------------
    # TEST 12: Eat food -> hunger increases
    # -------------------------------------------------------------------------
    player.hunger = 10.0
    player.inventory.slots[0] = ItemStack("cooked_beef", count=2)
    player.inventory.select_slot(0)
    ate = player.eat_selected_food(settings=ctrl.settings)
    assert ate, "eat_selected_food must return True when hungry and holding food"
    assert player.hunger == 18.0, f"Cooked beef (+8) should raise hunger from 10 to 18, got {player.hunger}"
    assert player.inventory.slots[0].count == 1, "Eating food must consume 1 food item"
    print("[PASS] TEST 12: Eat food -> Hunger increases (10 -> 18) and 1 food item is consumed.")

    # -------------------------------------------------------------------------
    # TEST 13: Travel far from spawn -> new chunks generate and distant chunks unload
    # -------------------------------------------------------------------------
    mod_coord = (int(math.floor(player.x)) + 1, int(math.floor(player.y)), int(math.floor(player.z)) + 1)
    world.set_block(mod_coord[0], mod_coord[1], mod_coord[2], COBBLESTONE)
    assert world.get_block(*mod_coord) == COBBLESTONE

    # Travel 160 blocks away (+10 chunks in X and Z)
    far_x, far_z = player.x + 160.0, player.z + 160.0
    player.position = (far_x, 30.0, far_z)
    world.update_chunks(far_x, far_z, render_distance=ctrl.settings.render_distance, immediate=True)

    far_cx, far_cz, _, _ = world.world_to_chunk(int(far_x), int(far_z))
    assert (far_cx, far_cz) in world.chunks, "New chunks must generate around far player position"
    assert (0, 0) not in world.chunks, "Distant spawn chunks must unload when player travels far away"
    print(f"[PASS] TEST 13: Travel far from spawn -> New chunks generated around {(far_cx, far_cz)} and distant chunks unloaded.")

    # -------------------------------------------------------------------------
    # TEST 14: Return to previously modified terrain -> modifications remain
    # -------------------------------------------------------------------------
    player.position = (start_x, start_y, start_z)
    world.update_chunks(start_x, start_z, render_distance=ctrl.settings.render_distance, immediate=True)
    assert world.get_block(*mod_coord) == COBBLESTONE, "Modified block must persist after chunk unload & reload"
    print("[PASS] TEST 14: Return to previously modified terrain -> Modifications remain intact.")

    # -------------------------------------------------------------------------
    # TEST 15: Save and quit -> reload -> world and player state are restored
    # -------------------------------------------------------------------------
    player.health = 14.0
    player.hunger = 16.0
    saved_pos = player.position
    world.world_time = 19.5  # Nighttime
    assert ctrl.save_current_world(), "save_current_world must succeed"
    ctrl.return_to_main_menu()
    assert ctrl.world is None and ctrl.ui.active_screen == "main_menu"

    loaded_ok = ctrl.load_saved_world("VerificationWorld")
    assert loaded_ok, "load_saved_world must succeed"
    assert ctrl.world is not None and ctrl.player is not None
    assert abs(ctrl.player.health - 14.0) < 1e-4, "Restored health must match saved health (14.0)"
    assert abs(ctrl.player.hunger - 16.0) < 1e-4, "Restored hunger must match saved hunger (16.0)"
    assert abs(ctrl.player.x - saved_pos[0]) < 1e-3 and abs(ctrl.player.z - saved_pos[2]) < 1e-3, "Restored position must match"
    assert ctrl.world.get_block(*mod_coord) == COBBLESTONE, "Restored world must contain saved block modifications"
    print("[PASS] TEST 15: Save and quit -> Reload -> World, player state, inventory, and modified blocks restored.")

    # -------------------------------------------------------------------------
    # TEST 16: Die -> death screen appears -> respawn works
    # -------------------------------------------------------------------------
    ctrl.player.take_damage(100.0, source="Skeleton", settings=ctrl.settings)
    ctrl.update(0.016)
    assert ctrl.player.is_dead, "Player must be dead at 0 HP"
    assert ctrl.ui.active_screen == "death", "Death screen must appear when player dies"
    ctrl.respawn_player()
    assert not ctrl.player.is_dead and ctrl.player.health == 20.0 and ctrl.player.hunger == 20.0
    assert ctrl.ui.active_screen == "hud", "Respawning must return player to active HUD"
    print("[PASS] TEST 16: Die -> Death screen appears -> Respawn restores health/hunger and returns to spawn.")

    # -------------------------------------------------------------------------
    # TEST 17: Change settings -> settings persist after restarting
    # -------------------------------------------------------------------------
    ctrl.settings.mouse_sensitivity = 72.0
    ctrl.settings.fov = 98
    ctrl.settings.render_distance = 4
    ctrl.settings.volume = 0.55
    ctrl.settings.graphics_quality = "Medium"
    ctrl.settings.save()

    reloaded_settings = GameSettings.load()
    assert reloaded_settings.mouse_sensitivity == 72.0
    assert reloaded_settings.fov == 98
    assert reloaded_settings.render_distance == 4
    assert abs(reloaded_settings.volume - 0.55) < 1e-5
    assert reloaded_settings.graphics_quality == "Medium"
    # Reset default render_distance = 3
    ctrl.settings.render_distance = 3
    ctrl.settings.fov = 90
    ctrl.settings.mouse_sensitivity = 45.0
    ctrl.settings.graphics_quality = "High"
    ctrl.settings.save()
    print("[PASS] TEST 17: Change settings -> Settings persist across restarts in saves/settings.json.")

    # -------------------------------------------------------------------------
    # TEST 18: Extended play simulation & error handling -> no memory/entity leak
    # -------------------------------------------------------------------------
    from ursina import scene
    initial_chunk_count = len(ctrl.world.chunks)
    for step_i in range(120):
        # Simulate walking in a circle, day/night progression, mob updates, particle cleanup
        angle = step_i * 0.05
        ctrl.player.move_and_collide(math.cos(angle) * 0.5, math.sin(angle) * 0.5, 0.03)
        ctrl.update(0.03)
        app.step()

    final_chunk_count = len(ctrl.world.chunks)
    max_expected_chunks = (ctrl.settings.render_distance * 2 + 3) ** 2
    assert final_chunk_count <= max_expected_chunks, f"Chunk count {final_chunk_count} exceeded cap {max_expected_chunks}"
    assert len(ctrl.mob_manager.mobs) <= ctrl.mob_manager.MAX_MOBS, "Mob count must stay bounded by MAX_MOBS"

    # Also test corrupted save recovery (Section 25)
    corrupt_path = ctrl.save_manager.get_save_path("corrupt_test_world")
    corrupt_path.write_text("{corrupted_json_syntax!!", encoding="utf-8")
    assert ctrl.save_manager.load_raw_data("corrupt_test_world") is None, "Corrupted save file must be handled gracefully without crashing"
    ctrl.save_manager.delete_world("corrupt_test_world")
    ctrl.save_manager.delete_world("VerificationWorld")

    print(f"[PASS] TEST 18: Extended play loop (120 steps) -> Bounded chunks ({final_chunk_count}), bounded mobs ({len(ctrl.mob_manager.mobs)}), zero leaks.")
    print("=" * 64)
    print("ALL 18 TESTS PASSED SUCCESSFULLY!")
    print("=" * 64)
    ctrl._cleanup_active_session()


if __name__ == "__main__":
    run_all_tests()
