"""
Textured, articulated box-model meshes for mobs.

Each mob is built from Minecraft-style boxes (see game/pixelart.py for the skin layout)
parented to pivot entities so limbs and heads can swing, plus a soft blob shadow.
Geometry is expressed in skin pixels and scaled to world units per mob type.
"""

import math
from typing import Dict, List, Optional, Tuple

from game.pixelart import MOB_PARTS, MOB_SKIN_SIZES, box_face_rects

# World units per skin pixel
PIXEL_SCALE: Dict[str, float] = {
    "zombie": 0.0585,
    "skeleton": 0.0585,
    "pig": 0.0625,
    "cow": 0.0600,
}

# Overhead health-bar height (world units) per mob
BAR_HEIGHT: Dict[str, float] = {"zombie": 2.15, "skeleton": 2.15, "pig": 1.2, "cow": 1.75}
SHADOW_SIZE: Dict[str, Tuple[float, float]] = {
    "zombie": (0.62, 0.62), "skeleton": (0.55, 0.55), "pig": (0.78, 1.1), "cow": (0.95, 1.25),
}


def build_box_mesh(size: Tuple[int, int, int], uv: Tuple[int, int], tex_size: Tuple[int, int],
                   center: Tuple[float, float, float] = (0.0, 0.0, 0.0), scale: float = 1.0):
    """Create an Ursina Mesh for a w/h/d pixel box with Minecraft cross-layout UVs.

    The +Z face is the front. `center` is the box centre in pixels relative to the entity origin.
    """
    from ursina import Mesh

    w, h, d = size
    tw, th = tex_size
    rects = box_face_rects(uv[0], uv[1], w, h, d)
    hx, hy, hz = w / 2.0, h / 2.0, d / 2.0
    cx, cy, cz = center

    # corners listed BL, BR, TR, TL as seen from outside the box
    faces = {
        "front": [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)],
        "back": [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)],
        "right": [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)],   # -X
        "left": [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)],        # +X
        "top": [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)],
        "bottom": [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)],
    }
    verts: List[Tuple[float, float, float]] = []
    uvs: List[Tuple[float, float]] = []
    tris: List[Tuple[int, int, int]] = []
    for face, corners in faces.items():
        x, y, rw, rh = rects[face]
        u0, u1 = x / tw, (x + rw) / tw
        v_top, v_bot = 1.0 - y / th, 1.0 - (y + rh) / th
        base = len(verts)
        for (px, py, pz) in corners:
            verts.append(((px + cx) * scale, (py + cy) * scale, (pz + cz) * scale))
        uvs.extend([(u0, v_bot), (u1, v_bot), (u1, v_top), (u0, v_top)])
        tris.append((base, base + 1, base + 2))
        tris.append((base, base + 2, base + 3))
    return Mesh(vertices=verts, triangles=tris, uvs=uvs, static=True)


class MobRig:
    """Container for the entities that make up one mob's visual model."""

    def __init__(self, mob_type: str, root):
        self.mob_type = mob_type
        self.root = root
        self.pivots: Dict[str, object] = {}
        self.meshes: List[object] = []   # entities that carry the skin (tinted on hit)
        self.shadow = None
        self.bar_height = BAR_HEIGHT.get(mob_type, 1.5)

    def tint(self, rgba) -> None:
        from ursina import color
        c = color.rgba(*rgba)
        for e in self.meshes:
            e.color = c


def _add_part(rig: MobRig, part: str, name: str, pivot_px: Tuple[float, float, float],
              center_px: Tuple[float, float, float], texture, tex_size, scale: float,
              parent=None, size=None, uv=None):
    """Create a pivot entity and a skinned box child. center_px is relative to the pivot."""
    from ursina import Entity

    spec = MOB_PARTS[rig.mob_type][part]
    pivot = Entity(parent=parent or rig.root,
                   position=(pivot_px[0] * scale, pivot_px[1] * scale, pivot_px[2] * scale))
    mesh = build_box_mesh(size or spec["size"], uv or spec["uv"], tex_size, center_px, scale)
    body = Entity(parent=pivot, model=mesh, texture=texture, double_sided=True)
    rig.pivots[name] = pivot
    rig.meshes.append(body)
    return pivot


def build_mob_rig(mob_type: str, root, texture) -> MobRig:
    """Assemble the articulated model for `mob_type` under `root`."""
    from ursina import Entity, color

    rig = MobRig(mob_type, root)
    s = PIXEL_SCALE.get(mob_type, 0.0625)
    tex_size = MOB_SKIN_SIZES[mob_type]
    P = MOB_PARTS[mob_type]

    if mob_type in ("zombie", "skeleton"):
        aw = P["arm"]["size"][0]
        lw = P["leg"]["size"][0]
        # legs: pivot at the hip, box hangs down
        _add_part(rig, "leg", "leg_l", (2.0, 12, 0), (0, -6, 0), texture, tex_size, s)
        _add_part(rig, "leg", "leg_r", (-2.0, 12, 0), (0, -6, 0), texture, tex_size, s)
        _add_part(rig, "body", "body", (0, 18, 0), (0, 0, 0), texture, tex_size, s)
        _add_part(rig, "head", "head", (0, 24, 0), (0, 4, 0), texture, tex_size, s)
        arm_x = 4.0 + aw / 2.0
        _add_part(rig, "arm", "arm_l", (arm_x, 22, 0), (0, -4, 0), texture, tex_size, s)
        _add_part(rig, "arm", "arm_r", (-arm_x, 22, 0), (0, -4, 0), texture, tex_size, s)
    elif mob_type == "pig":
        for name, x, z in (("leg_fl", 3.0, 5.0), ("leg_fr", -3.0, 5.0), ("leg_bl", 3.0, -5.0), ("leg_br", -3.0, -5.0)):
            _add_part(rig, "leg", name, (x, 6, z), (0, -3, 0), texture, tex_size, s)
        _add_part(rig, "body", "body", (0, 10, 0), (0, 0, 0), texture, tex_size, s)
        head = _add_part(rig, "head", "head", (0, 11, 8), (0, 0, 3), texture, tex_size, s)
        _add_part(rig, "snout", "snout", (0, 0, 0), (0, -1.5, 7.5), texture, tex_size, s, parent=head)
    elif mob_type == "cow":
        for name, x, z in (("leg_fl", 4.0, 6.5), ("leg_fr", -4.0, 6.5), ("leg_bl", 4.0, -6.5), ("leg_br", -4.0, -6.5)):
            _add_part(rig, "leg", name, (x, 12, z), (0, -6, 0), texture, tex_size, s)
        _add_part(rig, "body", "body", (0, 17, 0), (0, 0, 0), texture, tex_size, s)
        _add_part(rig, "udder", "udder", (0, 0, 0), (0, 11, -3), texture, tex_size, s)
        head = _add_part(rig, "head", "head", (0, 22, 9), (0, 0, 3), texture, tex_size, s)
        _add_part(rig, "snout", "snout", (0, 0, 0), (0, -1.5, 6.5), texture, tex_size, s, parent=head)
        _add_part(rig, "horn", "horn_l", (0, 0, 0), (4.5, 5.5, 2.0), texture, tex_size, s, parent=head)
        _add_part(rig, "horn", "horn_r", (0, 0, 0), (-4.5, 5.5, 2.0), texture, tex_size, s, parent=head)

    # soft blob shadow under the mob
    sw, sd = SHADOW_SIZE.get(mob_type, (0.7, 0.7))
    rig.shadow = Entity(parent=root, model="circle", rotation_x=90, y=0.03,
                        scale=(sw, sd, 1), color=color.rgba(0, 0, 0, 0.30))
    return rig


def animate_rig(rig: MobRig, swing_phase: float, move_amount: float, time_now: float,
                aggressive: bool = False) -> None:
    """Pose limbs. `move_amount` in [0,1] scales leg swing, `swing_phase` is radians."""
    pv = rig.pivots
    mt = rig.mob_type
    swing = math.sin(swing_phase) * 38.0 * move_amount

    def setrot(name: str, rx: float, ry: float = 0.0, rz: float = 0.0) -> None:
        p = pv.get(name)
        if p is not None:
            p.rotation = (rx, ry, rz)

    # Idle head motion: gentle look-around
    head_yaw = math.sin(time_now * 0.9) * 8.0
    head_pitch = math.sin(time_now * 0.6 + 1.0) * 3.0
    setrot("head", head_pitch, head_yaw)

    if mt in ("zombie", "skeleton"):
        setrot("leg_l", swing)
        setrot("leg_r", -swing)
        bob = math.sin(time_now * 1.7) * 2.5
        if mt == "zombie":
            # Arms outstretched, slightly swaying
            setrot("arm_l", -88 + bob + swing * 0.15, 0, -2)
            setrot("arm_r", -88 - bob - swing * 0.15, 0, 2)
        else:
            if aggressive:
                setrot("arm_l", -80 + bob, 0, 0)   # bow arm raised
                setrot("arm_r", -62 - bob, 18, 0)
            else:
                setrot("arm_l", -swing * 0.8, 0, -3)
                setrot("arm_r", swing * 0.8, 0, 3)
    else:
        setrot("leg_fl", swing)
        setrot("leg_br", swing)
        setrot("leg_fr", -swing)
        setrot("leg_bl", -swing)
        # Pigs/cows nod their heads while idle
        setrot("head", head_pitch * 2.0 + math.sin(time_now * 1.3) * 3.0, head_yaw)
