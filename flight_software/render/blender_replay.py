"""
blender_replay.py -- render a simulated flight (track.json) in Blender.

    blender -b -P blender_replay.py -- --track RUN/track.json --out OUTDIR
            [--cut highlight|full] [--cam chase|map|nose|auto]
            [--res 1920x1080] [--engine eevee|cycles] [--frames A:B[:STEP]] [--samples 16]

Builds the scene from the same data the simulation used (layout + trees from
the run's plan.json, CAD mesh of the printed build) and plays the logged
flight back: position, attitude, lift rotors / pusher on-off from the motor
outputs. Nothing is animated by hand, so the video shows what the physics flew.
Writes JPEG (or PNG) frames + schedule.json to OUTDIR; render/make_video.py
encodes them with captions.
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

import bpy
import bmesh
from mathutils import Euler, Vector

HERE = Path(__file__).resolve().parent
FS = HERE.parent
REPO = FS.parent
STL = FS / "gazebo" / "models" / "coconut_quadplane" / "meshes" / "coconut_quadplane.stl"
sys.path.insert(0, str(REPO / "airframe"))
import params as AF  # noqa: E402

H_REF = 14.0          # palm variants are modelled at this height
ASSETS = HERE / "assets"   # user-supplied, git-ignored: Poly Haven dirt_floor_4k + qwantani_morning_puresky_4k
HDRI = ASSETS / "qwantani_morning_puresky_4k.exr"
DIRT = ASSETS / "dirt_floor" / "textures"
MASS = json.loads((REPO / "airframe" / "out" / "mass_properties.json").read_text())["configs"][0]
X_CG, _, Z_CG = MASS["cg_build_mm"]


def args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cut", choices=["highlight", "full"], default="highlight")
    ap.add_argument("--cam", default="auto")
    ap.add_argument("--res", default="1920x1080")
    ap.add_argument("--engine", choices=["eevee", "cycles"], default="eevee")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--frames", default="")
    ap.add_argument("--format", choices=["JPEG", "PNG"], default="JPEG")
    ap.add_argument("--shots", type=Path, help="render the inserted shots listed in this JSON instead of the main cut")
    ap.add_argument("--only", default="", help="with --shots: comma-separated shot names to render")
    return ap.parse_args(argv)


# ---------------------------------------------------------------- materials
def mat(name, rgb, rough=0.8, metal=0.0, alpha=1.0, emit=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
    if emit:
        b.inputs["Emission Color"].default_value = (*rgb, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def noise_mat(name, c1, c2, scale=40.0, rough=0.95, leaflets=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = rough
    if "Specular IOR Level" in b.inputs:            # matte: no blue sky sheen
        b.inputs["Specular IOR Level"].default_value = 0.15
    if leaflets:                                     # pinnate frond: cut-out leaflet stripes
        wave = nt.nodes.new("ShaderNodeTexWave")
        wave.inputs["Scale"].default_value = 9.0
        wave.inputs["Distortion"].default_value = 1.5
        wave.bands_direction = "X"
        thr = nt.nodes.new("ShaderNodeMath")
        thr.operation = "GREATER_THAN"
        thr.inputs[1].default_value = 0.35
        nt.links.new(wave.outputs["Fac"], thr.inputs[0])
        nt.links.new(thr.outputs["Value"], b.inputs["Alpha"])
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "DITHERED"
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------- scene
def world(sun_elev=48.0, sun_rot=135.0):
    """HDRI sky when the asset is present (sun lamp aimed at the HDRI's sun), else Nishita."""
    w = bpy.data.worlds.new("sky")
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes["Background"]
    if HDRI.exists():
        env = nt.nodes.new("ShaderNodeTexEnvironment")
        env.image = bpy.data.images.load(str(HDRI))
        nt.links.new(env.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Strength"].default_value = 0.6
        import numpy as np
        im = env.image
        px = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
        im.pixels.foreach_get(px)
        lum = px.reshape(im.size[1], im.size[0], 4)[..., :3].sum(axis=2)
        y, x = np.unravel_index(int(lum.argmax()), lum.shape)
        sun_elev = (y + 0.5) / im.size[1] * 180.0 - 90.0           # Blender rows run bottom-up
        sun_rot = 270.0 - (x + 0.5) / im.size[0] * 360.0            # equirect u -> world azimuth
        print(f"[world] HDRI sun at elev {sun_elev:.1f} deg, azimuth {sun_rot:.1f} deg", flush=True)
    else:
        sky = nt.nodes.new("ShaderNodeTexSky")
        for k, v in (("sky_type", "NISHITA"), ("sun_elevation", math.radians(sun_elev)),
                     ("sun_rotation", math.radians(sun_rot)), ("altitude", 300.0),
                     ("air_density", 1.0), ("dust_density", 0.6)):
            if hasattr(sky, k):
                try:
                    setattr(sky, k, v)
                except TypeError:
                    pass
        bg.inputs["Strength"].default_value = 0.25
        nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3.5
    sun.angle = math.radians(1.0)
    so = link(bpy.data.objects.new("sun", sun))
    so.rotation_euler = Euler((math.radians(90 - sun_elev), 0, math.radians(sun_rot + 90)), "XYZ")


def ground_mat(scale_m=4.0, tint=(0.62, 0.52, 0.45)):
    """Poly Haven dirt_floor (colour/normal/roughness) tiled every `scale_m` m, with a large-scale
    noise breaking up the repeat; falls back to procedural soil."""
    if not DIRT.exists():
        return noise_mat("soil", (0.17, 0.11, 0.06), (0.30, 0.21, 0.12), 25.0)
    m = bpy.data.materials.new("dirt")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.2
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / scale_m, 1 / scale_m, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def img(name, colour):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(str(DIRT / name), check_existing=True)
        if not colour:
            t.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        return t
    diff = img("dirt_floor_diff_4k.jpg", True)
    big = nt.nodes.new("ShaderNodeTexNoise")              # 30 m blotches: hide the tiling
    big.inputs["Scale"].default_value = 0.03
    nt.links.new(tc.outputs["Object"], big.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    nt.links.new(big.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(diff.outputs["Color"], mix.inputs["A"])
    mix.inputs["B"].default_value = (*tint, 1)
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    nt.links.new(img("dirt_floor_rough_4k.exr", False).outputs["Color"], b.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(img("dirt_floor_nor_gl_4k.exr", False).outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def palm_materials():
    """frond (two-tone green, yellow-green toward the midrib), dry frond, ringed trunk."""
    def frond(name, c1, c2):
        m = noise_mat(name, c1, c2, 18.0, 0.65)
        m.use_backface_culling = False
        b = m.node_tree.nodes["Principled BSDF"]
        if "Subsurface Weight" in b.inputs:                # a little light through the leaves
            b.inputs["Subsurface Weight"].default_value = 0.15
        return m
    green = frond("frond", (0.06, 0.20, 0.03), (0.22, 0.36, 0.06))
    dry = frond("frond_dry", (0.42, 0.33, 0.14), (0.28, 0.22, 0.09))
    trunk = noise_mat("trunk", (0.13, 0.11, 0.09), (0.26, 0.22, 0.18), 40.0)
    nt = trunk.node_tree
    wave = nt.nodes.new("ShaderNodeTexWave")              # leaf-scar rings every ~8 cm
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 1.6
    wave.inputs["Distortion"].default_value = 2.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    nt.links.new(wave.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    return green, dry, trunk


def ground(lay):
    bpy.ops.mesh.primitive_plane_add(size=8000, location=(0, 0, 0))
    g = bpy.context.object
    g.data.materials.append(ground_mat(tint=(0.30, 0.36, 0.17)))     # dry scrub around the field
    fe, fn, fm = lay["field_e0"], lay["field_n0"], lay["field_m"]
    bpy.ops.mesh.primitive_plane_add(size=1, location=(fe + fm / 2, fn + fm / 2, 0.02))
    f = bpy.context.object
    f.scale = (fm + 6, fm + 6, 1)
    f.data.materials.append(ground_mat())
    # dock pad + H
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.05))
    d = bpy.context.object
    d.scale = (1.6, 1.6, 0.1)
    d.data.materials.append(mat("pad", (0.08, 0.08, 0.09), 0.6))
    for sx, sy, x in ((0.12, 0.9, -0.3), (0.12, 0.9, 0.3), (0.6, 0.12, 0.0)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0.105))
        h = bpy.context.object
        h.scale = (sx, sy, 0.01)
        h.data.materials.append(mat("h", (0.9, 0.9, 0.9), 0.5))


def palm_variant(k, frond_mat, trunk_mat, height=H_REF):
    """One coconut palm `height` m tall, built with bmesh: a leaning, tapered trunk and
    ~24 arched pinnate fronds with real leaflet geometry. Returns a collection."""
    rnd = random.Random(100 + k)
    col = bpy.data.collections.new(f"palm_{k}")
    # trunk: 12-sided tube along a gentle lean curve, swollen bole, 0.22 -> 0.14 m radius
    lean = (rnd.uniform(-1, 1), rnd.uniform(-1, 1))
    bm = bmesh.new()
    rings = []
    for i in range(25):
        u = i / 24
        cx, cy = 0.9 * lean[0] * u * u, 0.9 * lean[1] * u * u
        r = 0.14 + 0.08 * (1 - u) + 0.12 * max(0.0, 1 - u * 12)
        rings.append([bm.verts.new((cx + r * math.cos(t * math.pi / 6), cy + r * math.sin(t * math.pi / 6), u * height))
                      for t in range(12)])
    for r0, r1 in zip(rings, rings[1:]):
        for t in range(12):
            bm.faces.new((r0[t], r0[(t + 1) % 12], r1[(t + 1) % 12], r1[t]))
    me = bpy.data.meshes.new(f"trunk_{k}")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(trunk_mat)
    for f in me.polygons:
        f.use_smooth = True
    col.objects.link(bpy.data.objects.new(f"trunk_{k}", me))
    top = Vector((0.9 * lean[0], 0.9 * lean[1], height))
    # leaf-base boots: dark fibrous cone just under the crown
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=0.20, radius2=0.42, depth=0.9,
                                    location=top - Vector((0, 0, 0.35)))
    boot = bpy.context.object
    boot.data.materials.append(trunk_mat)
    for c in boot.users_collection:
        c.objects.unlink(boot)
    col.objects.link(boot)
    # fronds: rachis arches up then droops; ~55 pairs of leaflets hang off it in a V
    bm = bmesh.new()
    n_fr = 30
    for j in range(n_fr):
        az = j * 2.399963 + rnd.uniform(-0.15, 0.15)          # golden-angle phyllotaxis
        age = j / n_fr                                         # 0 young (upright) .. 1 old (drooping)
        rise = 1.1 - 1.4 * age + rnd.uniform(-0.15, 0.15)
        length = rnd.uniform(4.0, 4.8)
        d = Vector((math.cos(az), math.sin(az), 0))
        side = Vector((-math.sin(az), math.cos(az), 0))
        n_seg = 60
        pts = [top + d * (i / n_seg * length) * 0.92
               + Vector((0, 0, rise * (i / n_seg * length) - (0.45 + 0.35 * age) * (i / n_seg * length) ** 2 / length))
               for i in range(n_seg + 1)]
        for i in range(n_seg):          # rachis ribbon
            o = Vector((0, 0, 0.035 * (1 - i / n_seg) + 0.01))
            p0, p1 = pts[i], pts[i + 1]
            bm.faces.new([bm.verts.new(p0 - o), bm.verts.new(p1 - o), bm.verts.new(p1 + o), bm.verts.new(p0 + o)])
        for i in range(6, n_seg - 1):
            u = i / n_seg
            p0, p1 = pts[i], pts[i + 1]
            along = (p1 - p0).normalized()
            ll = 0.95 * math.sin(math.pi * min(1.0, 0.12 + u)) + 0.1
            hw = 0.035 + 0.015 * math.sin(math.pi * u)
            for sgn in (-1, 1):
                out = side * sgn
                droop = 0.25 + 0.35 * u + rnd.uniform(-0.05, 0.05)
                mid = p0 + out * 0.5 * ll + along * 0.12 * ll + Vector((0, 0, -0.15 * droop * ll))
                tip = p0 + out * ll + along * 0.30 * ll + Vector((0, 0, -droop * ll))
                v0a, v0b = bm.verts.new(p0 - along * hw * 0.5), bm.verts.new(p0 + along * hw * 0.5)
                v1a, v1b = bm.verts.new(mid - along * hw), bm.verts.new(mid + along * hw)
                vt = bm.verts.new(tip)
                bm.faces.new([v0a, v0b, v1b, v1a])
                bm.faces.new([v1a, v1b, vt])
    me = bpy.data.meshes.new(f"crown_{k}")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(frond_mat)
    col.objects.link(bpy.data.objects.new(f"crown_{k}", me))
    col["top"] = tuple(top)
    return col


def palms(trees, targets):
    """The 169 plantation palms from plan.json: green or dry-frond variants built at 12-16 m and
    stretched <4% to each tree's height, a bunch of nuts under each crown (orange = ripe)."""
    frond, frond_dry, trunk = palm_materials()
    nut_ripe = mat("nut_ripe", (0.80, 0.50, 0.08), 0.5)
    nut_green = mat("nut_green", (0.22, 0.38, 0.08), 0.5)
    heights = (12.0, 13.0, 14.0, 15.0, 16.0)
    variants = {(h, dry): [palm_variant(int(h) * 10 + 5 * dry + i, frond_dry if dry else frond, trunk, h)
                           for i in range(2)] for h in heights for dry in (False, True)}
    root = bpy.data.collections.new("plantation")
    bpy.context.scene.collection.children.link(root)
    for vs in variants.values():              # instanced, not rendered directly
        for v in vs:
            bpy.context.scene.collection.children.link(v)
            bpy.context.view_layer.layer_collection.children[v.name].exclude = True
    rnd = random.Random(7)
    for t in trees:
        h, cond = float(t["height"]), t["condition"]
        hv = min(heights, key=lambda x: abs(x - h))
        src = variants[(hv, "frond" in cond)][rnd.randrange(2)]
        inst = bpy.data.objects.new(f"tree_{t['id']}", None)
        inst.instance_type = "COLLECTION"
        inst.instance_collection = src
        inst.location = (float(t["e"]), float(t["n"]), 0)
        yaw = rnd.uniform(0, 6.28)
        inst.scale = (1.0, 1.0, h / hv)
        inst.rotation_euler = (0, 0, yaw)
        root.objects.link(inst)
        top = Vector(src["top"])
        top = Vector((top.x * math.cos(yaw) - top.y * math.sin(yaw), top.x * math.sin(yaw) + top.y * math.cos(yaw),
                      top.z * h / hv)) + inst.location
        nm = nut_ripe if "ripe" in cond else nut_green
        for j in range(9 if "ripe" in cond else 5):      # nuts hang just under the frond bases
            a_ = rnd.uniform(0, 6.28)
            r_ = rnd.uniform(0.25, 0.45)
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.14,
                                                 location=top + Vector((r_ * math.cos(a_), r_ * math.sin(a_),
                                                                        -0.55 - 0.18 * (j % 3))))
            s_ = bpy.context.object
            s_.scale = (1.0, 1.0, 1.15)
            s_.data.materials.append(nm)
            for c in s_.users_collection:
                c.objects.unlink(s_)
            root.objects.link(s_)
        if t["id"] in targets:                  # target marker on the ground
            bpy.ops.mesh.primitive_torus_add(major_radius=4.5, minor_radius=0.08,
                                             location=(float(t["e"]), float(t["n"]), 0.05))
            r = bpy.context.object
            r.name = f"target_ring_{t['id']}"
            r.data.materials.append(mat("target", (0.9, 0.35, 0.1), 0.5, emit=1.5))


# ---------------------------------------------------------------- aircraft
def flu(X, Y, Z):
    """build frame mm (X aft, Y right, Z up) -> aircraft local m (X right, Y nose, Z up), CG origin."""
    return Vector((Y / 1000.0, (X_CG - X) / 1000.0, (Z - Z_CG) / 1000.0))


def aircraft():
    rig = link(bpy.data.objects.new("aircraft", None))
    rig.rotation_mode = "YXZ"
    bpy.ops.wm.stl_import(filepath=str(STL))
    body = bpy.context.object
    body.data.materials.append(mat("airframe", (0.92, 0.92, 0.90), 0.45))
    # STL is build-frame mm: scale + map (X aft, Y right, Z up) -> (Y nose=-X, X right=Y)
    for v in body.data.vertices:
        v.co = flu(v.co.x, v.co.y, v.co.z)
    body.parent = rig
    props = {}
    blade_m = mat("prop", (0.05, 0.05, 0.05), 0.4)
    disc_m = mat("disc", (0.1, 0.1, 0.1), 0.6, alpha=0.25)
    zr = AF.Z_BOOM + 30
    rotors = {"FR": (AF.X_ROTOR_FRONT, AF.BOOM_Y), "RL": (AF.X_ROTOR_REAR, -AF.BOOM_Y),
              "FL": (AF.X_ROTOR_FRONT, -AF.BOOM_Y), "RR": (AF.X_ROTOR_REAR, AF.BOOM_Y)}
    for i, (nm, (x, y)) in enumerate(rotors.items()):
        props[i] = prop(nm, flu(x, y, zr + 12), (0, 0, 0), rig, blade_m, disc_m)
    props[4] = prop("pusher", flu(AF.X_PUSHER + 8, 0, AF.Z_TAIL), (math.pi / 2, 0, 0), rig, blade_m, disc_m)
    return rig, props


def prop(name, loc, rot, parent, blade_m, disc_m):
    hub = bpy.data.objects.new(f"prop_{name}", None)
    link(hub)
    hub.parent = parent
    hub.location = loc
    hub.rotation_euler = rot
    bpy.ops.mesh.primitive_cube_add(size=1)
    b = bpy.context.object
    b.scale = (0.254, 0.022, 0.004)
    b.data.materials.append(blade_m)
    b.parent = hub
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.127, depth=0.002)
    d = bpy.context.object
    d.data.materials.append(disc_m)
    d.parent = hub
    return hub, b, d


# ---------------------------------------------------------------- timeline
def schedule(tr, cut):
    """List of (track_index, speed, camera) per output frame. The track is already at the video
    frame rate, so speed 1 is real time and speed N shows every Nth logged frame.
    full     : every frame, real time, chase camera
    highlight: real time + chase camera for takeoff, transition and the first 12 s of lane 1;
               6x on the high "map" camera for the rest of the sweep (the planned path, the
               flown trail and the palms turning "scanned" make the racetrack readable, and from
               that far away 6x still moves smoothly); real time again from 12 s before the
               back-transition through the first confirm stop; 2x for the other stops; real
               time for the last 25 s (landing)."""
    fr = tr["frames"]
    n = len(fr)
    if cut == "full":
        return [(i, 1, "chase") for i in range(n)]
    on = [max(f["lift"]) > 0.06 for f in fr]
    switch = [fr[i]["t"] for i in range(1, n) if on[i] != on[i - 1] and fr[i]["up"] > 2]
    s_off, s_on = (switch[0], switch[-1]) if len(switch) >= 2 else (fr[-1]["t"], fr[-1]["t"])
    t_end = fr[-1]["t"]

    def rule(t):
        if t < s_off + 12 or t > t_end - 25:
            return 1, "chase"
        if t < s_on - 12:
            return 6, "map"
        if t < s_on + 25:
            return 1, "chase"
        return 2, "chase"
    out, i = [], 0
    while i < n:
        sp, cam = rule(fr[i]["t"])
        out.append((i, sp, cam))
        i += sp
    return out


def camera_rigs(rig, lay):
    cams = {}
    for nm, lens in (("chase", 42), ("map", 45), ("nose", 18)):
        c = bpy.data.cameras.new(nm)
        c.lens = lens
        c.clip_end = 3000
        cams[nm] = link(bpy.data.objects.new(nm, c))
    # nose ESP32-CAM: on the aircraft, 60 deg below the horizon, ~60 deg HFOV
    n = cams["nose"]
    n.parent = rig
    n.location = flu(AF.POD_X[0] + 20, 0, 0)
    n.rotation_euler = Euler((math.radians(90 - 60), 0, 0), "XYZ")
    n.data.sensor_fit = "HORIZONTAL"
    n.data.angle = math.radians(60)
    tc = cams["chase"].constraints.new("TRACK_TO")
    tc.target = rig
    tc.track_axis = "TRACK_NEGATIVE_Z"
    tc.up_axis = "UP_Y"
    # map: fixed, high and south of the field, looking at its centre (whole field in frame)
    fe, fn, fm = lay["field_e0"], lay["field_n0"], lay["field_m"]
    centre = link(bpy.data.objects.new("field_centre", None))
    centre.location = (fe + fm / 2, fn + fm / 2 + 10, 0)
    cams["map"].location = (fe + fm / 2, fn - 0.9 * fm, 1.3 * fm)
    tc = cams["map"].constraints.new("TRACK_TO")
    tc.target = centre
    tc.track_axis = "TRACK_NEGATIVE_Z"
    tc.up_axis = "UP_Y"
    return cams


def poly_curve(name, pts, bevel, rgb, emit, alpha=1.0):
    cd = bpy.data.curves.new(name, "CURVE")
    cd.dimensions = "3D"
    cd.bevel_depth = bevel
    cd.bevel_resolution = 2
    sp = cd.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p_, q in zip(sp.points, pts):
        p_.co = (*q, 1.0)
    ob = link(bpy.data.objects.new(name, cd))
    cd.materials.append(mat(name, rgb, 0.6, emit=emit, alpha=alpha))
    return ob


def overlays(tr):
    """Planned path (on the ground), flown trail (revealed as the flight goes), a beacon on the
    aircraft for the map camera, and a 'scanned' disc under every palm once the nose camera has
    imaged it."""
    path = [(e, n, 0.25) for n, e in tr["path"]]
    plan_line = poly_curve("planned_path", path, 0.35, (0.95, 0.95, 0.90), 1.0, alpha=0.85)
    trail_idx = list(range(0, len(tr["frames"]), 10))
    f0 = tr["frames"][0]
    trail = poly_curve("trail", [(f0["e"], f0["n"], f0["up"])] * len(trail_idx), 0.45, (1.0, 0.30, 0.0), 0.6)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.6, segments=16, ring_count=8)
    beacon = bpy.context.object
    beacon.data.materials.append(mat("beacon", (1.0, 0.85, 0.2), 0.5, emit=6.0))
    scan_m = mat("scanned", (0.15, 0.75, 0.95), 0.6, emit=0.8, alpha=0.45)
    discs = []
    for t in tr["trees"]:
        if t["id"] not in tr.get("imaged_t", {}):
            continue
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=3.0, depth=0.04,
                                            location=(float(t["e"]), float(t["n"]), 0.08))
        d = bpy.context.object
        d.data.materials.append(scan_m)
        d.hide_render = True
        discs.append((tr["imaged_t"][t["id"]], d))
    return trail, trail_idx, beacon, discs, plan_line


def target_pulses(tr):
    """Map-camera markers on the confirm-stop palms: an orange ring at crown height that pulses,
    so the 4 targets stand out among the 169 palms while the sweep runs."""
    m = mat("target_pulse", (1.0, 0.22, 0.0), 0.5, emit=1.2)
    rings = []
    for t in tr["trees"]:
        if t["id"] not in tr["targets"]:
            continue
        bpy.ops.mesh.primitive_torus_add(major_radius=5.0, minor_radius=0.35,
                                         location=(float(t["e"]), float(t["n"]), float(t["height"]) + 0.6))
        r = bpy.context.object
        r.data.materials.append(m)
        r.hide_render = True
        rings.append(r)
    return rings


def pose(f, rig, props, spin):
    rig.location = (f["e"], f["n"], f["up"] + 0.22)
    rig.rotation_euler = (math.radians(f["pitch"]), math.radians(f["roll"]), math.radians(-f["yaw"]))
    for i, (hub, blade, disc) in props.items():
        thr = f["lift"][i] if i < 4 else f["pusher"]
        on = thr > 0.06
        spin[i] += 0.9 if on else 0.0
        hub.rotation_euler.z = spin[i] if i < 4 else 0
        if i == 4:
            hub.rotation_euler = (math.pi / 2, spin[i], 0)
        blade.hide_render = on
        disc.hide_render = not on


def fov_wedge(nose, length=12.0):
    """The nose camera's field of view (60 x 46 deg) as a translucent pyramid parented to the
    camera, plus brighter edges: shows what the ESP32-CAM sees and why the aircraft hovers short
    of the palm (the camera looks 60 deg down and forward)."""
    tx, ty = math.tan(math.radians(30)) * length, math.tan(math.radians(23)) * length
    bm = bmesh.new()
    apex = bm.verts.new((0, 0, 0))
    c = [bm.verts.new((sx * tx, sy * ty, -length)) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for i in range(4):
        bm.faces.new((apex, c[i], c[(i + 1) % 4]))
    me = bpy.data.meshes.new("fov")
    bm.to_mesh(me)
    bm.free()
    wedge = link(bpy.data.objects.new("fov", me))
    wedge.data.materials.append(mat("fov", (0.3, 0.85, 1.0), 0.5, emit=0.6, alpha=0.09))
    wedge.parent = nose
    edges = link(bpy.data.objects.new("fov_edges", me.copy()))
    wf = edges.modifiers.new("wf", "WIREFRAME")
    wf.thickness = 0.03
    edges.data.materials.clear()
    edges.data.materials.append(mat("fov_edge", (0.5, 0.95, 1.0), 0.5, emit=1.5, alpha=0.5))
    edges.parent = nose
    return [wedge, edges]


def shot_rigs(tr, shot, nose):
    """Camera for one inserted shot. side/high/orbit frame the aircraft and its target palm,
    esp32 is the nose camera, trans_side flies alongside the aircraft through the transition."""
    c = bpy.data.cameras.new(shot["name"])
    c.clip_end = 3000
    cam = link(bpy.data.objects.new(shot["name"], c))
    look = link(bpy.data.objects.new(shot["name"] + "_look", None))
    tc = cam.constraints.new("TRACK_TO")
    tc.target = look
    tc.track_axis = "TRACK_NEGATIVE_Z"
    tc.up_axis = "UP_Y"
    if shot["cam"] == "esp32":
        return nose, None, None
    if shot["cam"] == "trans_side":
        c.lens = 65
        return cam, look, None
    tree = next(t for t in tr["trees"] if t["id"] == shot["tree"])
    T = Vector((float(tree["e"]), float(tree["n"]), float(tree["height"]) - 0.5))
    hover = [f for f in tr["frames"] if shot["t0"] <= f["t"] <= shot["t1"]]
    D = min(hover, key=lambda f: math.hypot(f["e"] - T.x, f["n"] - T.y))
    D = Vector((D["e"], D["n"], D["up"]))
    u = Vector((T.x - D.x, T.y - D.y, 0)).normalized()
    perp = Vector((-u.y, u.x, 0))
    M = (D + T) / 2
    look.location = M
    geo = {"T": T, "D": D, "u": u, "perp": perp, "M": M}
    if shot["cam"] == "side":
        c.lens = 20                                    # over the shoulder: aircraft close, palm beyond
        cam.location = D - u * 5 + perp * 5 + Vector((0, 0, 1.5))
    elif shot["cam"] == "high":
        c.lens = 28
        cam.location = D - u * 9 + perp * 4 + Vector((0, 0, 13))
    elif shot["cam"] == "orbit":
        c.lens = 22
    return cam, look, geo


def render_shots(a, tr, sc, rig, props, cams, discs, rings):
    """--shots FILE: render each listed shot (real time, every track frame from t0 to t1) into
    OUT/<name>/, plus OUT/<name>/boxes.json for ESP32 shots (crown bounding box in the image,
    from the camera geometry -- for the overlay, not a detector output)."""
    from bpy_extras.object_utils import world_to_camera_view
    shots = json.loads(a.shots.read_text())
    nose = cams["nose"]
    wedge = fov_wedge(nose)
    wedge_m = wedge[0].data.materials[0]
    beam = poly_curve("beam", [(0, 0, 0), (0, 0, 1)], 0.05, (0.5, 0.95, 1.0), 3.0, alpha=0.9)
    hl = mat("target_hl", (1.0, 0.85, 0.2), 0.5, emit=5.0)
    w0, h0 = sc.render.resolution_x, sc.render.resolution_y
    for shot in shots:
        if a.only and shot["name"] not in a.only.split(","):
            continue
        out = a.out / shot["name"]
        out.mkdir(parents=True, exist_ok=True)
        cam, look, geo = shot_rigs(tr, shot, nose)
        sc.camera = cam
        esp = shot["cam"] == "esp32"
        sc.render.resolution_x, sc.render.resolution_y = (800, 600) if esp else (w0, h0)
        tree = next((t for t in tr["trees"] if t["id"] == shot.get("tree")), None)
        ring = None
        if tree is not None and not esp:
            bpy.ops.mesh.primitive_torus_add(major_radius=4.6, minor_radius=0.12,
                                             location=(float(tree["e"]), float(tree["n"]), float(tree["height"]) + 0.3))
            ring = bpy.context.object
            ring.data.materials.append(hl)
        for ob in wedge + [beam]:
            ob.hide_render = esp or tree is None
        for r in rings:
            r.hide_render = True
        for ob in bpy.data.objects:                    # ground target rings: not in the camera view
            if ob.name.startswith("target_ring"):
                ob.hide_render = esp
        idx = [i for i, f in enumerate(tr["frames"]) if shot["t0"] <= f["t"] < shot["t1"]]
        if a.frames:                                   # quick test: A:B:STEP within the shot
            lo, hi, *st = (int(x) for x in a.frames.split(":"))
            idx = idx[lo:hi:(st[0] if st else 1)]
        spin = [0.0] * 5
        boxes = {}
        for j, i in enumerate(idx):
            f = tr["frames"][i]
            pose(f, rig, props, spin)
            if shot["cam"] == "trans_side":            # alongside, 7 m off the left wing, 2 m above (palms behind)
                yaw = math.radians(f["yaw"])
                cam.location = Vector((f["e"] - 7 * math.cos(yaw), f["n"] + 7 * math.sin(yaw), f["up"] + 2.0))
                look.location = rig.location
            if geo is not None:                        # keep both the aircraft and its palm in frame
                look.location = rig.location * 0.7 + geo["T"] * 0.3
            if shot["cam"] == "orbit":                 # 70 deg arc round the aircraft
                s = j / max(1, len(idx) - 1)
                ang = math.atan2(geo["perp"].y, geo["perp"].x) - math.radians(35) + math.radians(70) * s
                cam.location = rig.location + Vector((9 * math.cos(ang), 9 * math.sin(ang), 3))
            if tree is not None and not esp:           # wedge lights up + beam once the crown is wholly in frame
                locked = tree["id"] in f.get("tgt", [])
                beam.hide_render = not locked
                colour = (0.3, 1.0, 0.45, 1) if locked else (0.3, 0.85, 1.0, 1)
                bsdf = wedge_m.node_tree.nodes["Principled BSDF"]
                bsdf.inputs["Emission Color"].default_value = colour
                bsdf.inputs["Base Color"].default_value = colour
                bsdf.inputs["Alpha"].default_value = 0.16 if locked else 0.07
                bpy.context.view_layer.update()
                p0 = nose.matrix_world.translation
                pts = beam.data.splines[0].points
                pts[0].co = (*p0, 1.0)
                pts[1].co = (float(tree["e"]), float(tree["n"]), float(tree["height"]) - 0.3, 1.0)
            for t_img, d in discs:                     # analysis overlays stay out of the camera view
                d.hide_render = esp or t_img > f["t"]
            if esp and tree is not None:
                bpy.context.view_layer.update()
                cr = tr["layout"]["crown_radius_m"]
                ps = [world_to_camera_view(sc, nose, Vector((float(tree["e"]) + cr * math.cos(q), float(tree["n"])
                                                             + cr * math.sin(q), float(tree["height"]) + dz)))
                      for q in [k * math.pi / 6 for k in range(12)] for dz in (-1.2, 0.4)]
                if all(p.z > 0 for p in ps):
                    boxes[j] = [min(p.x for p in ps), min(1 - p.y for p in ps), max(p.x for p in ps), max(1 - p.y for p in ps)]
            sc.render.filepath = str(out / f"{j:06d}.jpg")
            bpy.ops.render.render(write_still=True)
            if j % 50 == 0:
                print(f"[shot {shot['name']}] frame {j}/{len(idx)} t={f['t']:.1f}s", flush=True)
        if esp:
            (out / "boxes.json").write_text(json.dumps(boxes))
        if ring is not None:
            bpy.data.objects.remove(ring)
    sc.render.resolution_x, sc.render.resolution_y = w0, h0


def main():
    a = args()
    tr = json.loads(a.track.read_text())
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    try:
        sc.render.engine = "BLENDER_EEVEE" if a.engine == "eevee" else "CYCLES"
    except TypeError:
        sc.render.engine = "BLENDER_EEVEE_NEXT"
    if a.engine == "cycles":
        sc.cycles.samples = a.samples
        sc.cycles.device = "GPU"
    else:
        try:
            sc.eevee.taa_render_samples = a.samples
        except AttributeError:
            pass
    w, h = (int(x) for x in a.res.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.image_settings.file_format = a.format
    if a.format == "JPEG":
        sc.render.image_settings.quality = 93
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = -0.3 if HDRI.exists() else -0.7
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    world()
    ground(tr["layout"])
    palms(tr["trees"], set(tr["targets"]))
    rig, props = aircraft()
    cams = camera_rigs(rig, tr["layout"])
    trail, trail_idx, beacon, discs, plan_line = overlays(tr)
    rings = target_pulses(tr)
    a.out = a.out.resolve()  # Blender resolves a relative render path against the drive root
    if a.shots:
        for ob in (beacon, trail, plan_line):
            ob.hide_render = True
        render_shots(a, tr, sc, rig, props, cams, discs, rings)
        return

    sched = schedule(tr, a.cut)
    lo, hi, step = 0, len(sched), 1
    if a.frames:                                   # A:B or A:B:STEP (STEP > 1 for quick previews)
        lo, hi, *st = (int(x) for x in a.frames.split(":"))
        step = st[0] if st else 1
    a.out.mkdir(parents=True, exist_ok=True)
    chase_pos, spin = None, [0.0] * 5
    # resuming mid-way: run the camera smoothing over the previous 90 frames without rendering
    for k in range(max(0, lo - 90), min(hi, len(sched))):
        idx, speed, cam = sched[k]
        if a.cam != "auto":
            cam = a.cam
        f = tr["frames"][idx]
        pose(f, rig, props, spin)
        # chase camera: 7 m behind / 1.6 m above along the smoothed heading
        yaw = math.radians(f["yaw"])
        want = Vector((f["e"] - 7 * math.sin(yaw), f["n"] - 7 * math.cos(yaw), f["up"] + 1.6 + 0.22))
        chase_pos = want if chase_pos is None else chase_pos.lerp(want, min(0.5, 0.08 * speed))
        chase_pos.z = max(chase_pos.z, 1.5)
        cams["chase"].location = chase_pos
        sc.camera = cams[cam]
        beacon.location = rig.location
        for ob in [beacon, trail, plan_line] + rings:      # map-camera overlays only: up close they fill the frame
            ob.hide_render = cam != "map"
        for r in rings:
            r.scale = [1.0 + 0.22 * math.sin(k * 0.35)] * 3
        if k < lo or (k - lo) % step:
            continue
        pts = trail.data.splines[0].points          # flown trail up to now, the rest collapsed onto the aircraft
        for j, ti in enumerate(trail_idx):
            g = tr["frames"][min(ti, idx)]
            pts[j].co = (g["e"], g["n"], g["up"] + 0.22, 1.0)
        for t_img, d in discs:
            d.hide_render = t_img > f["t"]
        sc.render.filepath = str(a.out / f"{k:06d}.{'jpg' if a.format == 'JPEG' else 'png'}")
        bpy.ops.render.render(write_still=True)
        if k % 50 == 0:
            print(f"[render] frame {k}/{len(sched)} track t={f['t']:.1f}s cam={cam}", flush=True)
    (a.out / "schedule.json").write_text(json.dumps({"fps": tr["fps"], "frames": len(sched), "cut": a.cut,
                                                      "t": [tr["frames"][i]["t"] for i, _, _ in sched],
                                                      "speed": [sp for _, sp, _ in sched],
                                                      "cam": [c for _, _, c in sched], "phases": tr["phases"]}))


main()
