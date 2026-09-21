#!/usr/bin/env python3
"""Create one browser-ready high LOD GLB for each Outer Wilds celestial body/ship."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prepare_outer_wilds_sun_dlc as scene_importer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "web-high-assets"
WEB = ROOT / "glb"
RENDERS = ROOT / "renders"
SPECIAL_DATA = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "web-high-source" / "scene-data"
SUN_DLC_BLEND = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "sun-and-dlc" / "blender" / "outer_wilds_sun_dlc.blend"
WEB.mkdir(parents=True, exist_ok=True)
RENDERS.mkdir(parents=True, exist_ok=True)

MAX_TRIANGLES = 56_000
MAX_TEXTURE_SIZE = 1024
MESH_INCLUDE_TOKENS = {
    "ember-twin": ("Terrain_Proxy_CT_Arch", "Terrain_Proxy_CT_Base"),
    "giants-deep": ("CloudsTopLayer_GD",),
}

ASSETS = [
    ("sun", "Sun", "太阳", "celestial", "SCALE::SUN / radius 2000", "Solar surface reconstruction from extracted textures"),
    ("ash-twin", "Ash Twin", "灰烬双星", "celestial", "VIEW::ash_sand_sphere", "Runtime sand sphere reconstructed with extracted game mesh and materials"),
    ("ember-twin", "Ember Twin", "余烬双星", "celestial", "SCALE::Ember Twin / R200", "Official distant proxy"),
    ("timber-hearth", "Timber Hearth", "木炉星", "celestial", "SCALE::Timber Hearth / R250", "Official distant proxy"),
    ("attlerock", "The Attlerock", "废岩星", "celestial", "SCALE::Attlerock / R100", "Official distant proxy"),
    ("brittle-hollow", "Brittle Hollow", "碎空星", "celestial", "SCALE::Brittle Hollow / R300", "Official distant proxy"),
    ("hollows-lantern", "Hollow's Lantern", "空心灯", "celestial", "SCALE::Hollow's Lantern / R130", "Official distant proxy"),
    ("giants-deep", "Giant's Deep", "深巨星", "celestial", "SCALE::Giant's Deep / R950 cloud top", "Official distant proxy, visible cloud shell"),
    ("dark-bramble", "Dark Bramble", "黑棘星", "celestial", "SCALE::Dark Bramble / R650 envelope", "Official distant proxy"),
    ("interloper", "The Interloper", "闯入者", "celestial", "SCALE::Interloper / R110 nominal", "Official distant proxy without tail effects"),
    ("quantum-moon", "Quantum Moon", "量子卫星", "celestial", "SCALE::Quantum Moon / R110", "Official distant proxy"),
    ("white-hole", "White Hole", "白洞", "anomaly", "SCALE::WHITE_HOLE / visual radius 100", "Blender geometry for the web shader effect"),
    ("black-hole", "Black Hole", "黑洞", "anomaly", "SCALE::BlackHoleRenderer", "Extracted proxy geometry; web lensing is shader-driven"),
    ("stranger", "The Stranger", "陌生者", "dlc", "VIEW::stranger_exterior", "DLC exterior shell and deployed solar sails only"),
    ("owlk-homeworld", "Ringed Homeworld", "环形母星", "dlc", "VIEW::visible_homeworld", "DLC sky representation, not a physical game-space body"),
    ("eye", "Eye of the Universe", "宇宙之眼", "special", "VIEW::eye_proxy", "Distant proxy only; surface level excluded"),
    ("player-ship", "Hearthian Ship", "哈斯人飞船", "spacecraft", "VIEW::player_ship", "Player ship near proxy"),
    ("nomai-shuttle", "Nomai Shuttle", "挪麦穿梭机", "spacecraft", "VIEW::nomai_shuttle", "Exterior shell"),
    ("nomai-vessel", "The Vessel", "挪麦母舰", "spacecraft", "VIEW::nomai_vessel", "Exterior shell, opening, glass and lights"),
]


def descendants(root):
    seen = set()
    stack = [root]
    while stack:
        obj = stack.pop()
        if obj in seen:
            continue
        seen.add(obj)
        stack.extend(obj.children)
    return seen


def source_meshes(root, key):
    if root.type == "MESH":
        return [root] if not root.hide_render else []
    meshes = [obj for obj in descendants(root) if obj.type == "MESH" and not obj.hide_render]
    tokens = MESH_INCLUDE_TOKENS.get(key)
    if tokens:
        meshes = [obj for obj in meshes if any(token.lower() in obj.name.lower() for token in tokens)]
    return meshes


def triangles(obj):
    return sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def append_dlc_sources():
    with bpy.data.libraries.load(str(SUN_DLC_BLEND), link=False) as (source, target):
        target.collections = [name for name in ("stranger_exterior", "visible_homeworld") if name in source.collections]
    for collection in target.collections:
        if collection and collection.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(collection)


def import_special_sources():
    scene_importer.DATA = SPECIAL_DATA
    builder = scene_importer.Builder()
    for key in ("player_ship", "nomai_shuttle", "nomai_vessel", "eye_proxy"):
        builder.group(key)
    collection = bpy.data.collections.new("ash_sand_sphere")
    bpy.context.scene.collection.children.link(collection)
    wrapper = bpy.data.objects.new("VIEW::ash_sand_sphere", None)
    collection.objects.link(wrapper)
    sphere = bpy.data.objects.new(
        "AshTwin_SandSphere",
        builder.mesh(builder.manifest["ash_sand_sphere_mesh"], builder.manifest["ash_sand_materials"]),
    )
    sphere.data.materials.clear()
    sphere.data.materials.append(make_ash_sand_material(builder))
    sphere.parent = wrapper
    collection.objects.link(sphere)


def make_ash_sand_material(builder):
    source = builder.manifest["materials"][builder.manifest["ash_sand_materials"][-1]]
    height_source = builder.image(source["textures"]["_HeightmapMain"]["path"], data=True)
    pixels = np.empty(len(height_source.pixels), dtype=np.float32)
    height_source.pixels.foreach_get(pixels)
    pixels = pixels.reshape(-1, 4)
    height = pixels[:, :3].mean(axis=1, keepdims=True)
    tint = np.array(source["colors"]["_Color"][:3], dtype=np.float32)
    colored = np.empty_like(pixels)
    colored[:, :3] = np.clip(tint * (0.68 + height * 0.58), 0, 1)
    colored[:, 3] = 1
    albedo = bpy.data.images.new(
        "Ash Twin sand albedo - reconstructed from extracted heightmap",
        width=height_source.size[0],
        height=height_source.size[1],
        alpha=True,
    )
    albedo.colorspace_settings.name = "sRGB"
    albedo.pixels.foreach_set(colored.reshape(-1))
    albedo.pack()

    material = bpy.data.materials.new("Ash Twin sand - web reconstruction")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Roughness"].default_value = 0.76
    albedo_node = nodes.new("ShaderNodeTexImage")
    albedo_node.image = albedo
    links.new(albedo_node.outputs["Color"], shader.inputs["Base Color"])

    normal_source = source["textures"].get("_SandNormals")
    if normal_source:
        normal_image = builder.decoded_normal(normal_source["path"])
        normal_image.colorspace_settings.name = "Non-Color"
        normal_texture = nodes.new("ShaderNodeTexImage")
        normal_texture.image = normal_image
        normal = nodes.new("ShaderNodeNormalMap")
        normal.inputs["Strength"].default_value = 0.45
        links.new(normal_texture.outputs["Color"], normal.inputs["Color"])
        links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    material["shader_reconstruction"] = "Extracted sand tint/heightmap/normal adapted to glTF PBR"
    return material


def copy_materials(objects, key):
    material_map = {}
    image_map = {}
    for source in objects:
        for material in source.data.materials:
            if not material or material in material_map:
                continue
            copied = material.copy()
            copied.name = f"WEB::{key}::{material.name}"
            material_map[material] = copied
            if not copied.use_nodes:
                continue
            for node in copied.node_tree.nodes:
                if node.type != "TEX_IMAGE" or not node.image:
                    continue
                source_image = node.image
                if source_image not in image_map:
                    image = source_image.copy()
                    image.name = f"WEB::{key}::{source_image.name}"
                    width, height = source_image.size
                    longest = max(width, height)
                    if longest > MAX_TEXTURE_SIZE:
                        ratio = MAX_TEXTURE_SIZE / longest
                        image.scale(max(1, round(width * ratio)), max(1, round(height * ratio)))
                    image.pack()
                    image_map[source_image] = image
                node.image = image_map[source_image]
    return material_map, image_map


def mesh_bounds(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return low, high


def clone_and_flatten(key, root, output_collection):
    sources = source_meshes(root, key)
    if not sources:
        raise RuntimeError(f"{key}: source root has no visible meshes: {root.name}")
    material_map, image_map = copy_materials(sources, key)
    clones = []
    for source in sources:
        clone = source.copy()
        clone.name = f"WEB::{key}::{source.name}"
        clone.data = source.data.copy()
        clone.animation_data_clear()
        clone.hide_render = False
        clone.hide_viewport = False
        clone.parent = None
        clone.data.materials.clear()
        for material in source.data.materials:
            if material:
                clone.data.materials.append(material_map[material])
        output_collection.objects.link(clone)
        clone.data.transform(source.matrix_world)
        clone.matrix_world = Matrix.Identity(4)
        clones.append(clone)

    bpy.ops.object.select_all(action="DESELECT")
    for clone in clones:
        clone.select_set(True)
    bpy.context.view_layer.objects.active = clones[0]
    if len(clones) > 1:
        bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = f"WEB::{key}"
    try:
        bpy.ops.object.material_slot_remove_unused()
    except RuntimeError:
        pass

    before = triangles(joined)
    if before > MAX_TRIANGLES:
        modifier = joined.modifiers.new("WEB_HIGH_LOD", "DECIMATE")
        modifier.ratio = MAX_TRIANGLES / before
        modifier.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=modifier.name)
    for polygon in joined.data.polygons:
        polygon.use_smooth = True

    low, high = mesh_bounds(joined)
    center = (low + high) * 0.5
    diameter = max(high - low)
    joined.data.transform(Matrix.Scale(2 / max(diameter, 0.0001), 4) @ Matrix.Translation(-center))
    joined.matrix_world = Matrix.Identity(4)
    wrapper = bpy.data.objects.new(f"ASSET::{key}", None)
    output_collection.objects.link(wrapper)
    joined.parent = wrapper
    joined.matrix_parent_inverse.identity()
    return wrapper, joined, image_map


def export_glb(key, wrapper, mesh):
    bpy.ops.object.select_all(action="DESELECT")
    wrapper.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    path = WEB / f"{key}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_materials="EXPORT",
        export_image_format="WEBP",
        export_image_quality=80,
        export_image_webp_fallback=False,
        export_meshopt_compression_enable=True,
        export_meshopt_extension="EXT_meshopt_compression",
        export_yup=True,
    )
    return path


def make_material(name, color, emission=0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.65
    shader.inputs["Emission Color"].default_value = color
    shader.inputs["Emission Strength"].default_value = emission
    return material


def make_label(collection, text, location, size, material):
    curve = bpy.data.curves.new(f"Label::{text}", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.004
    curve.materials.append(material)
    obj = bpy.data.objects.new(f"Label::{text}", curve)
    obj.location = location
    obj.rotation_euler = (math.pi / 2, 0, 0)
    collection.objects.link(obj)


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_light(name, kind, location, energy, color, size=10):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "AREA":
        data.shape = "DISK"
        data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, (0, 0, 0))


def setup_scene():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 3840
    scene.render.resolution_y = 2160
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.002, 0.006, 0.012, 1)
    background.inputs["Strength"].default_value = 0.22
    scene.view_settings.look = "AgX - Medium High Contrast"


def make_camera():
    data = bpy.data.cameras.new("Web High Catalog Camera")
    data.type = "ORTHO"
    data.ortho_scale = 36
    data.clip_start = 0.1
    data.clip_end = 200
    camera = bpy.data.objects.new("Web High Catalog Camera", data)
    camera.location = (0, -34, 0)
    bpy.context.scene.collection.objects.link(camera)
    look_at(camera, (0, 0, 0))
    bpy.context.scene.camera = camera
    return camera


def configure_viewports(camera):
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            area.spaces.active.shading.type = "MATERIAL"
            area.spaces.active.region_3d.view_perspective = "CAMERA"
            area.spaces.active.region_3d.view_camera_zoom = 0


def main():
    if bpy.data.objects.get("SCALE::Timber Hearth / R250") is None:
        raise RuntimeError("Run with outer_wilds_true_scale_catalog.blend as the input")
    append_dlc_sources()
    import_special_sources()
    setup_scene()
    catalog = bpy.data.collections.new("WEB HIGH ASSETS")
    bpy.context.scene.collection.children.link(catalog)
    label_material = make_material("Web catalog labels", (0.72, 0.84, 0.88, 1), 0.35)
    title_material = make_material("Web catalog title", (1.0, 0.65, 0.25, 1), 0.55)

    records = []
    created = []
    for key, english, chinese, category, root_name, note in ASSETS:
        source_root = bpy.data.objects.get(root_name)
        if source_root is None:
            raise RuntimeError(f"Missing source root: {root_name}")
        collection = bpy.data.collections.new(f"ASSET::{key}")
        catalog.children.link(collection)
        wrapper, mesh, images = clone_and_flatten(key, source_root, collection)
        path = export_glb(key, wrapper, mesh)
        decoded_texture = sum(int(image.size[0]) * int(image.size[1]) * 4 * 4 / 3 for image in images.values())
        record = {
            "key": key,
            "name": english,
            "name_zh": chinese,
            "category": category,
            "triangles": triangles(mesh),
            "vertices": len(mesh.data.vertices),
            "materials": len(mesh.data.materials),
            "texture_images": len(images),
            "texture_max": MAX_TEXTURE_SIZE,
            "texture_gpu_mib_rgba8_mipped": round(decoded_texture / 1048576, 2),
            "glb_mib": round(path.stat().st_size / 1048576, 2),
            "source": note,
        }
        records.append(record)
        created.append((wrapper, mesh, record))
        print("ASSET", json.dumps(record, ensure_ascii=False), flush=True)

    columns = 5
    x_spacing = 6.5
    z_spacing = 4.25
    rows = math.ceil(len(created) / columns)
    for index, (wrapper, _mesh, record) in enumerate(created):
        row = index // columns
        column = index % columns
        wrapper.location = ((column - (columns - 1) / 2) * x_spacing, 0, ((rows - 1) / 2 - row) * z_spacing)
        make_label(
            catalog,
            f"{record['name']}\n{record['triangles']:,} tris / {record['glb_mib']:.2f} MiB",
            (wrapper.location.x, -0.9, wrapper.location.z - 1.55),
            0.24,
            label_material,
        )
    make_label(catalog, "OUTER WILDS / WEB HIGH ASSET CATALOG", (0, -0.9, 9.45), 0.52, title_material)

    for collection in bpy.data.collections:
        if collection == catalog or collection.name.startswith("ASSET::"):
            continue
        collection.hide_render = True
        collection.hide_viewport = True
    add_light("Catalog Key", "AREA", (-10, -15, 16), 1250, (1.0, 0.72, 0.44), 13)
    add_light("Catalog Fill", "AREA", (13, -11, 7), 1100, (0.38, 0.66, 1.0), 11)
    add_light("Catalog Rim", "AREA", (0, 6, 12), 950, (0.32, 0.72, 0.78), 10)
    camera = make_camera()
    configure_viewports(camera)
    bpy.context.scene.render.filepath = str(RENDERS / "outer-wilds-web-high-catalog.png")
    bpy.ops.render.render(write_still=True)

    manifest = {
        "format": 1,
        "profile": {"geometry_cap_triangles": MAX_TRIANGLES, "texture_max_edge": MAX_TEXTURE_SIZE, "texture_format": "WebP quality 80", "geometry_compression": "EXT_meshopt_compression"},
        "assets": records,
        "totals": {
            "assets": len(records),
            "triangles": sum(record["triangles"] for record in records),
            "glb_mib": round(sum(record["glb_mib"] for record in records), 2),
            "texture_gpu_mib_rgba8_mipped": round(sum(record["texture_gpu_mib_rgba8_mipped"] for record in records), 2),
        },
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme = bpy.data.texts.new("README - web high assets")
    readme.write(
        "Browser-oriented Outer Wilds local study assets.\n"
        "Each asset is capped near 56,000 triangles, flattened to reduce draw calls, centered and normalized.\n"
        "Textures have a maximum edge of 1024 and GLBs use WebP plus EXT_meshopt_compression.\n"
        "Dreamworld and ringworld interior terrain are intentionally excluded. The Eye uses only its distant proxy.\n"
        "The Ringed Homeworld is a DLC sky representation, not a physical game-space body.\n"
        "Black/white hole lensing is implemented separately in the web shader demo.\n"
        "Local study only; extracted game assets remain under private/ and must not be committed or redistributed.\n"
    )
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "outer-wilds-web-high-catalog.blend"))
    print("TOTALS", json.dumps(manifest["totals"], ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
