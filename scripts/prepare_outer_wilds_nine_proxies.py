#!/usr/bin/env python3
"""Build a textured Blender catalog from the nine extracted distant proxies."""

from __future__ import annotations

import math
import re
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_ROOT = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "all-distant-proxies"
SOURCE_ROOT = EXTRACT_ROOT / "assetstudio"
OUTPUT_ROOT = EXTRACT_ROOT / "blender"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

PROXIES = [
    ("AshTwin_DistantProxy", "ASH TWIN", (-8.0, 0.0, 6.0)),
    ("EmberTwin_DistantProxy", "EMBER TWIN", (0.0, 0.0, 6.0)),
    ("TimberHearth_DistantProxy", "TIMBER HEARTH + ATTLEROCK", (8.0, 0.0, 6.0)),
    ("BrittleHollow_DistantProxy", "BRITTLE HOLLOW + HOLLOW'S LANTERN", (-8.0, 0.0, 0.0)),
    ("GiantsDeep_DistantProxy", "GIANT'S DEEP", (0.0, 0.0, 0.0)),
    ("DarkBramble_DistantProxy", "DARK BRAMBLE", (8.0, 0.0, 0.0)),
    ("Comet_DistantProxy", "THE INTERLOPER", (-8.0, 0.0, -6.0)),
    ("QuantumMoon_DistantProxy", "QUANTUM MOON", (0.0, 0.0, -6.0)),
    ("WhiteHole_DistantProxy", "WHITE HOLE", (8.0, 0.0, -6.0)),
]


def rgba(value: str, alpha: float = 1.0):
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)) + (alpha,)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def proxy_fbx(proxy_name: str) -> Path:
    return SOURCE_ROOT / proxy_name / "FBX_GameObjects" / proxy_name / f"{proxy_name}.fbx"


def move_to_collection(objects, collection: bpy.types.Collection) -> None:
    for obj in objects:
        for current in list(obj.users_collection):
            current.objects.unlink(obj)
        collection.objects.link(obj)


def visible_meshes(objects) -> list[bpy.types.Object]:
    visible = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        lower = obj.name.lower()
        if (
            "fogsphere" in lower
            or lower.startswith("fog_")
            or "volumetricfog" in lower
            or "volumeticfog" in lower
        ):
            obj.hide_render = True
            obj.hide_viewport = True
            continue
        visible.append(obj)
    return visible


def world_bounds(objects) -> tuple[Vector, Vector]:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        for corner in obj.bound_box
    ]
    if not points:
        return Vector((-1, -1, -1)), Vector((1, 1, 1))
    minimum = Vector((
        min(point.x for point in points),
        min(point.y for point in points),
        min(point.z for point in points),
    ))
    maximum = Vector((
        max(point.x for point in points),
        max(point.y for point in points),
        max(point.z for point in points),
    ))
    return minimum, maximum


def tune_materials(materials) -> None:
    for material in materials:
        if not material.node_tree:
            continue
        shader = next(
            (node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"),
            None,
        )
        if shader:
            roughness = shader.inputs.get("Roughness")
            metallic = shader.inputs.get("Metallic")
            if roughness:
                roughness.default_value = max(0.58, roughness.default_value)
            if metallic and "nom" not in material.name.lower():
                metallic.default_value = 0.0
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            image_name = node.image.name.lower()
            if re.search(r"(?:^|[_-])n(?:\.|[_-])", image_name) or "normal" in image_name:
                node.image.colorspace_settings.name = "Non-Color"


def image_by_filename(filename: str):
    for image in bpy.data.images:
        if image.filepath and Path(image.filepath).name == filename:
            return image
    return None


def rebuild_material(
    material: bpy.types.Material,
    *,
    diffuse: str | None = None,
    normal: str | None = None,
    tint: str | None = None,
    emission_strength: float = 0.0,
) -> None:
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.72
    shader.inputs["Metallic"].default_value = 0.0
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])

    diffuse_image = image_by_filename(diffuse) if diffuse else None
    color_output = None
    if diffuse_image:
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = diffuse_image
        color_output = texture.outputs["Color"]
    if tint:
        if color_output:
            multiply = nodes.new("ShaderNodeMixRGB")
            multiply.blend_type = "MULTIPLY"
            multiply.inputs["Fac"].default_value = 1.0
            multiply.inputs[2].default_value = rgba(tint)
            links.new(color_output, multiply.inputs[1])
            color_output = multiply.outputs["Color"]
        else:
            shader.inputs["Base Color"].default_value = rgba(tint)
    if color_output:
        links.new(color_output, shader.inputs["Base Color"])

    normal_image = image_by_filename(normal) if normal else None
    if normal_image:
        normal_image.colorspace_settings.name = "Non-Color"
        normal_texture = nodes.new("ShaderNodeTexImage")
        normal_texture.image = normal_image
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.inputs["Strength"].default_value = 0.72
        links.new(normal_texture.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], shader.inputs["Normal"])

    if emission_strength:
        emission = shader.inputs.get("Emission Color") or shader.inputs.get("Emission")
        if emission:
            if color_output:
                links.new(color_output, emission)
            elif tint:
                emission.default_value = rgba(tint)
        if shader.inputs.get("Emission Strength"):
            shader.inputs["Emission Strength"].default_value = emission_strength


def repair_proxy_materials(proxy_name: str, materials) -> None:
    for material in materials:
        if proxy_name == "AshTwin_DistantProxy" and material.name.startswith("Terrain_TT_Proxy_mat"):
            rebuild_material(
                material,
                diffuse="TT_Proxy_d.png",
                emission_strength=0.03,
            )
        elif proxy_name == "DarkBramble_DistantProxy" and material.name.startswith("DB_Proxy_mat"):
            rebuild_material(
                material,
                diffuse="DB_Proxy_mat_d.png",
                normal="DB_Proxy_mat_n.png",
                emission_strength=0.08,
            )
        elif proxy_name == "GiantsDeep_DistantProxy" and material.name.startswith("Clouds_GD_Top_mat"):
            rebuild_material(
                material,
                diffuse="Clouds_GD_Top_d.png",
                normal="Clouds_GD_Top_n.png",
                tint="#4f8060",
                emission_strength=0.06,
            )
        elif proxy_name == "WhiteHole_DistantProxy" and material.name.startswith(
            "Effects_BH_WhiteHole_DistantProxy_mat"
        ):
            rebuild_material(
                material,
                tint="#c8f5ff",
                emission_strength=5.0,
            )


def import_proxy(proxy_name: str, target: tuple[float, float, float], index: int):
    fbx_path = proxy_fbx(proxy_name)
    if not fbx_path.is_file():
        raise FileNotFoundError(fbx_path)
    objects_before = set(bpy.data.objects)
    materials_before = set(bpy.data.materials)
    bpy.ops.import_scene.fbx(filepath=str(fbx_path), use_image_search=True)
    imported = [obj for obj in bpy.data.objects if obj not in objects_before]
    imported_materials = [material for material in bpy.data.materials if material not in materials_before]
    tune_materials(imported_materials)
    repair_proxy_materials(proxy_name, imported_materials)

    collection = bpy.data.collections.new(proxy_name)
    bpy.context.scene.collection.children.link(collection)
    move_to_collection(imported, collection)
    meshes = visible_meshes(imported)
    minimum, maximum = world_bounds(meshes)
    center = (minimum + maximum) * 0.5
    diameter = max(maximum.x - minimum.x, maximum.y - minimum.y, maximum.z - minimum.z)
    display_scale = 3.8 / max(diameter, 0.001)

    wrapper = bpy.data.objects.new(f"CATALOG::{proxy_name}", None)
    content = bpy.data.objects.new(f"CONTENT::{proxy_name}", None)
    collection.objects.link(wrapper)
    collection.objects.link(content)
    wrapper.location = target
    wrapper.scale = (display_scale,) * 3
    wrapper.rotation_euler.z = math.radians((index % 3 - 1) * 7)
    content.location = -center
    content.parent = wrapper
    imported_set = set(imported)
    for obj in imported:
        if obj.parent not in imported_set:
            obj.parent = content

    wrapper["source_fbx"] = str(fbx_path)
    wrapper["official_proxy"] = True
    wrapper["display_scale"] = display_scale
    wrapper["source_diameter"] = diameter
    return wrapper, collection, meshes


def make_material(name: str, tint: str, emission_strength: float = 0.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = rgba(tint)
    shader.inputs["Roughness"].default_value = 0.6
    emission = shader.inputs.get("Emission Color") or shader.inputs.get("Emission")
    if emission:
        emission.default_value = rgba(tint)
    if shader.inputs.get("Emission Strength"):
        shader.inputs["Emission Strength"].default_value = emission_strength
    return material


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_label(collection, text: str, position, camera, material, size=0.3):
    bpy.ops.object.text_add(location=position)
    obj = bpy.context.object
    obj.name = f"LABEL::{text}"
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.004
    obj.data.bevel_depth = 0.002
    obj.data.materials.append(material)
    obj.rotation_euler = (camera.location - obj.location).to_track_quat("Z", "Y").to_euler()
    move_to_collection([obj], collection)
    return obj


def add_light(name, kind, location, energy, tint, size=6.0, target=(0, 0, 0)):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = rgba(tint)[:3]
    if kind == "AREA":
        data.shape = "DISK"
        data.size = size
    elif kind == "SUN":
        data.angle = math.radians(8)
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, Vector(target))
    return obj


def add_camera() -> bpy.types.Object:
    data = bpy.data.cameras.new("Nine Proxy Catalog Camera")
    data.type = "ORTHO"
    data.ortho_scale = 32.0
    data.clip_start = 0.1
    data.clip_end = 200
    camera = bpy.data.objects.new("Nine Proxy Catalog Camera", data)
    camera.location = (0, -42, 0)
    bpy.context.scene.collection.objects.link(camera)
    look_at(camera, Vector((0, 0, 0)))
    bpy.context.scene.camera = camera
    return camera


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 1280
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = rgba("#020408")
    background.inputs["Strength"].default_value = 0.12
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    scene.use_nodes = True
    compositor = bpy.data.node_groups.new("Nine Proxy Compositor", "CompositorNodeTree")
    scene.compositing_node_group = compositor
    layers = compositor.nodes.new("CompositorNodeRLayers")
    glare = compositor.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 1.0
    glare.inputs["Strength"].default_value = 0.16
    glare.inputs["Size"].default_value = 0.42
    compositor.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    output = compositor.nodes.new("NodeGroupOutput")
    compositor.links.new(layers.outputs["Image"], glare.inputs["Image"])
    compositor.links.new(glare.outputs["Image"], output.inputs["Image"])


def set_textured_viewport_default() -> None:
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            shading = area.spaces.active.shading
            shading.type = "MATERIAL"
            shading.color_type = "MATERIAL"
            shading.show_shadows = True
            shading.show_cavity = True
            shading.cavity_type = "WORLD"


def add_readme() -> None:
    text = bpy.data.texts.new("README - nine official proxies")
    text.write(
        "Outer Wilds nine-body distant-proxy catalog\n\n"
        "All celestial geometry and image textures in the nine named Collections were exported from the local game copy.\n"
        "The grid positions, normalized display scales, labels, camera, and lights are presentation-only.\n"
        "The original Unity atmosphere/fog shaders do not survive FBX conversion; broken FogSphere meshes are hidden.\n"
        "Viewport shading is saved as Material Preview. Press Z then R for full Eevee Rendered view.\n"
        "Each body remains in a separate Collection and retains its source hierarchy.\n"
        "Local study only; do not redistribute extracted assets.\n"
    )


def main() -> None:
    clear_scene()
    configure_scene()
    presentation = bpy.data.collections.new("PRESENTATION")
    bpy.context.scene.collection.children.link(presentation)
    camera = add_camera()
    label_material = make_material("Catalog Labels", "#dce8e5", 0.35)
    title_material = make_material("Catalog Title", "#efbd66", 0.7)

    totals = {"meshes": 0, "polygons": 0, "materials": 0}
    for index, (proxy_name, label, target) in enumerate(PROXIES):
        _, _, meshes = import_proxy(proxy_name, target, index)
        totals["meshes"] += len(meshes)
        totals["polygons"] += sum(len(obj.data.polygons) for obj in meshes)
        label_size = 0.23 if len(label) > 26 else 0.3
        add_label(
            presentation,
            label,
            (target[0], -0.8, target[2] - 2.3),
            camera,
            label_material,
            label_size,
        )

    add_label(
        presentation,
        "OUTER WILDS / NINE OFFICIAL DISTANT PROXIES",
        (0, -0.7, 9.2),
        camera,
        title_material,
        0.5,
    )
    add_light("Catalog Sun", "SUN", (-12, -15, 15), 2.7, "#ffe7c0", target=(0, 0, 0))
    add_light("Catalog Fill", "AREA", (13, -10, 9), 1700, "#a7d7e7", 9, target=(2, 0, 0))
    add_light("Catalog Warm Fill", "AREA", (-13, -8, -7), 1250, "#ffc58b", 8, target=(-2, 0, -2))
    totals["materials"] = len(bpy.data.materials)
    add_readme()
    set_textured_viewport_default()

    scene = bpy.context.scene
    scene.render.filepath = str(OUTPUT_ROOT / "outer_wilds_nine_proxies_catalog.png")
    bpy.ops.render.render(write_still=True)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_ROOT / "outer_wilds_nine_proxies.blend"))
    print({**totals, "images": len(bpy.data.images), "output": str(OUTPUT_ROOT)})


if __name__ == "__main__":
    main()
