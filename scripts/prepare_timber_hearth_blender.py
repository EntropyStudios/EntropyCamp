#!/usr/bin/env python3
"""Prepare the extracted Timber Hearth distant proxy for inspection in Blender."""

from __future__ import annotations

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_ROOT = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "timber-hearth"
FBX_DIR = EXTRACT_ROOT / "assetstudio" / "TimberHearth_DistantProxy" / "FBX_GameObjects" / "TimberHearth_DistantProxy"
FBX_PATH = FBX_DIR / "TimberHearth_DistantProxy.fbx"
OUTPUT_DIR = EXTRACT_ROOT / "blender"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def rgba(value: str, alpha: float = 1.0):
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)) + (alpha,)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def find_principled(material: bpy.types.Material):
    if not material.node_tree:
        return None
    return next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)


def principled_input(shader, *names: str):
    for name in names:
        socket = shader.inputs.get(name)
        if socket is not None:
            return socket
    return None


def make_emission_material(name: str, tint: str, strength: float, alpha: float = 1.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    principled_input(shader, "Base Color").default_value = rgba(tint)
    principled_input(shader, "Roughness").default_value = 0.34
    principled_input(shader, "Emission Color", "Emission").default_value = rgba(tint)
    principled_input(shader, "Emission Strength").default_value = strength
    principled_input(shader, "Alpha").default_value = alpha
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    if alpha < 1:
        material.surface_render_method = "BLENDED"
        material.use_transparency_overlap = False
    return material


def make_atmosphere_material() -> bpy.types.Material:
    material = bpy.data.materials.new("Inspection Atmosphere - not extracted shader")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    layer = nodes.new("ShaderNodeLayerWeight")
    inverse = nodes.new("ShaderNodeMath")
    power = nodes.new("ShaderNodeMath")
    multiply = nodes.new("ShaderNodeMath")
    inverse.operation = "SUBTRACT"
    inverse.inputs[0].default_value = 1.0
    power.operation = "POWER"
    power.inputs[1].default_value = 2.8
    multiply.operation = "MULTIPLY"
    multiply.inputs[1].default_value = 0.48
    principled_input(shader, "Base Color").default_value = rgba("#66c9df")
    principled_input(shader, "Emission Color", "Emission").default_value = rgba("#4ca8c4")
    principled_input(shader, "Emission Strength").default_value = 0.42
    principled_input(shader, "Roughness").default_value = 0.2
    links.new(layer.outputs["Facing"], inverse.inputs[1])
    links.new(inverse.outputs[0], power.inputs[0])
    links.new(power.outputs[0], multiply.inputs[0])
    links.new(multiply.outputs[0], principled_input(shader, "Alpha"))
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material.surface_render_method = "BLENDED"
    material.use_transparency_overlap = False
    return material


def add_atmosphere() -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96, ring_count=64, radius=2.98, location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = "Inspection Atmosphere (procedural presentation only)"
    obj.data.materials.append(make_atmosphere_material())
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    obj.hide_render = True
    obj.hide_viewport = True
    return obj


def add_starfield(material: bpy.types.Material) -> None:
    rng = random.Random(753640)
    vertices = []
    faces = []
    for _ in range(260):
        theta = rng.uniform(0, math.tau)
        phi = math.acos(rng.uniform(-1, 1))
        radius = rng.uniform(24, 34)
        center = Vector((
            radius * math.sin(phi) * math.cos(theta),
            radius * math.sin(phi) * math.sin(theta),
            radius * math.cos(phi),
        ))
        size = rng.uniform(0.012, 0.045)
        offset = len(vertices)
        vertices.extend([
            tuple(center + Vector((size, 0, 0))),
            tuple(center + Vector((-size, 0, 0))),
            tuple(center + Vector((0, size, 0))),
            tuple(center + Vector((0, 0, size))),
        ])
        faces.extend([
            (offset, offset + 2, offset + 3),
            (offset + 2, offset + 1, offset + 3),
            (offset + 1, offset, offset + 3),
            (offset, offset + 1, offset + 2),
        ])
    mesh = bpy.data.meshes.new("Inspection Starfield")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new("Inspection Starfield", mesh)
    bpy.context.scene.collection.objects.link(obj)


def add_area_light(name: str, location, energy: float, tint: str, size: float) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = rgba(tint)[:3]
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, Vector((0, 0, 0)))
    return obj


def add_sun_light() -> bpy.types.Object:
    data = bpy.data.lights.new("Neutral Sun", "SUN")
    data.energy = 2.8
    data.angle = math.radians(7)
    data.color = rgba("#fff1d2")[:3]
    obj = bpy.data.objects.new("Neutral Sun", data)
    obj.location = (-12, -14, 13)
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, Vector((2.5, 0, 0)))
    return obj


def create_camera(name: str, location, target, lens: float) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.clip_start = 0.05
    data.clip_end = 200
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, Vector(target))
    return obj


def create_label(camera: bpy.types.Object) -> bpy.types.Object:
    bpy.ops.object.text_add(location=(3.7, -1.1, -4.5))
    obj = bpy.context.object
    obj.name = "Inspection Label"
    obj.data.body = "TIMBER HEARTH + ATTLEROCK\nOfficial distant-proxy mesh and textures / game v1.1.16.1351"
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = 0.34
    obj.data.space_line = 1.35
    obj.data.extrude = 0.006
    obj.data.bevel_depth = 0.003
    obj.data.materials.append(make_emission_material("Inspection Label", "#dce9e7", 0.55))
    obj.rotation_euler = (camera.location - obj.location).to_track_quat("Z", "Y").to_euler()
    return obj


def configure_scene() -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 1280
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.frame_start = 1
    scene.frame_end = 240
    scene.render.fps = 30
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = rgba("#010306")
    background.inputs["Strength"].default_value = 0.1
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    scene.use_nodes = True
    compositor = bpy.data.node_groups.new("Timber Hearth Compositor", "CompositorNodeTree")
    scene.compositing_node_group = compositor
    layers = compositor.nodes.new("CompositorNodeRLayers")
    glare = compositor.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 1.1
    glare.inputs["Strength"].default_value = 0.2
    glare.inputs["Size"].default_value = 0.48
    compositor.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    output = compositor.nodes.new("NodeGroupOutput")
    compositor.links.new(layers.outputs["Image"], glare.inputs["Image"])
    compositor.links.new(glare.outputs["Image"], output.inputs["Image"])


def tune_extracted_materials() -> None:
    for material in bpy.data.materials:
        shader = find_principled(material)
        if shader is None:
            continue
        roughness = principled_input(shader, "Roughness")
        metallic = principled_input(shader, "Metallic")
        if roughness:
            roughness.default_value = max(0.62, roughness.default_value)
        if metallic and "NOM" not in material.name:
            metallic.default_value = 0.0
        for node in material.node_tree.nodes:
            if node.type != "TEX_IMAGE" or node.image is None:
                continue
            if node.image.name.lower().endswith("_n.png") or "_n" in node.image.name.lower():
                node.image.colorspace_settings.name = "Non-Color"


def add_readme() -> None:
    text = bpy.data.texts.new("README - extraction provenance")
    text.write(
        "Timber Hearth inspection scene\n\n"
        "Source: local Outer Wilds v1.1.16.1351 copy.\n"
        "Extractor: AssetStudioModCLI v0.19.0, SplitObjects export.\n"
        "Official extracted data: TimberHearth_DistantProxy FBX and its image textures.\n"
        "Presentation-only additions: lights, cameras, starfield, label, and atmosphere material.\n"
        "The original Unity fog/atmosphere shader is not represented by FBX and was not claimed as extracted.\n"
        "This local study must remain under private/ and must not be redistributed.\n"
    )


def animate_scene() -> None:
    planet = bpy.data.objects.get("Proxy_TH")
    moon = bpy.data.objects.get("Moon_Pivot")
    if planet:
        driver = planet.driver_add("rotation_euler", 2).driver
        driver.expression = f"(frame - 1) * {math.tau / 720:.12f}"
    if moon:
        driver = moon.driver_add("rotation_euler", 2).driver
        driver.expression = f"(frame - 1) * {math.tau / 240:.12f}"


def main() -> None:
    if not FBX_PATH.exists():
        raise FileNotFoundError(FBX_PATH)
    clear_scene()
    configure_scene()
    bpy.ops.import_scene.fbx(filepath=str(FBX_PATH), use_image_search=True)
    tune_extracted_materials()

    fog = bpy.data.objects.get("FogSphere")
    if fog:
        fog.hide_render = True
        fog.hide_viewport = True
    add_atmosphere()
    star_material = make_emission_material("Inspection Stars", "#d9f4ff", 3.0)
    add_starfield(star_material)
    add_sun_light()
    add_area_light("Sun Key", (-9, -10, 9), 2100, "#ffd5a3", 7.0)
    add_area_light("Cool Fill", (12, -7, 8), 1750, "#a8d9e9", 7.0)
    moon_fill = add_area_light("Attlerock Fill", (9, -10, 4), 1100, "#d6e9ef", 4.5)
    look_at(moon_fill, Vector((9, 0, 0)))

    system_camera = create_camera("System Camera", (12.5, -23.5, 8.2), (4.15, 0, -0.15), 55)
    closeup_camera = create_camera("Closeup Camera", (8.1, -12.4, 6.2), (0, 0, 0), 58)
    create_label(system_camera)
    animate_scene()
    add_readme()

    scene = bpy.context.scene
    scene.frame_set(64)
    scene.camera = closeup_camera
    scene.render.filepath = str(OUTPUT_DIR / "timber_hearth_extracted_closeup.png")
    bpy.ops.render.render(write_still=True)

    scene.camera = system_camera
    scene.frame_set(1)
    scene.render.filepath = str(OUTPUT_DIR / "timber_hearth_extracted_system.png")
    bpy.ops.render.render(write_still=True)

    for image in bpy.data.images:
        if image.source == "FILE" and image.filepath:
            image.filepath = str(Path(image.filepath).resolve())
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / "timber_hearth_extracted.blend"))
    print(f"Saved extracted Timber Hearth study to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
