#!/usr/bin/env python3
"""Build and render a reproducible Timber Hearth web-LOD comparison."""

from __future__ import annotations

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "timber-hearth-lod-comparison"
OUTPUT = ROOT / "renders"
WEB = ROOT / "web"
OUTPUT.mkdir(parents=True, exist_ok=True)
WEB.mkdir(parents=True, exist_ok=True)

LEVELS = [
    {"key": "original", "label": "ORIGINAL", "target": None, "texture": 2048},
    {"key": "high", "label": "LOD HIGH", "target": 56_000, "texture": 1024},
    {"key": "balanced", "label": "LOD BALANCED", "target": 15_000, "texture": 512},
    {"key": "low", "label": "LOD LOW", "target": 5_000, "texture": 256},
    {"key": "ultra", "label": "LOD ULTRA", "target": 1_500, "texture": 128},
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


def triangle_count(objects):
    return sum(
        sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)
        for obj in objects
        if obj.type == "MESH"
    )


def world_bounds(objects):
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH" and not obj.hide_render
        for corner in obj.bound_box
    ]
    low = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    return low, high


def hide_existing_scene():
    for collection in bpy.data.collections:
        collection.hide_render = True
        collection.hide_viewport = True


def new_collection(name):
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    collection.hide_render = False
    collection.hide_viewport = False
    return collection


def copy_materials(source_objects, key, max_texture_size):
    material_map = {}
    image_map = {}
    for source in source_objects:
        for material in source.data.materials:
            if not material or material in material_map:
                continue
            copied = material.copy()
            copied.name = f"{key}::{material.name}"
            material_map[material] = copied
            if not copied.use_nodes:
                continue
            for node in copied.node_tree.nodes:
                if node.type != "TEX_IMAGE" or not node.image:
                    continue
                source_image = node.image
                if source_image not in image_map:
                    image = source_image.copy()
                    image.name = f"{key}::{source_image.name}"
                    width, height = source_image.size
                    longest = max(width, height)
                    if longest > max_texture_size:
                        ratio = max_texture_size / longest
                        image.scale(max(1, round(width * ratio)), max(1, round(height * ratio)))
                    image.pack()
                    image_map[source_image] = image
                node.image = image_map[source_image]
    return material_map, image_map


def clone_level(source_objects, source_center, level, position, collection):
    key = level["key"]
    material_map, image_map = copy_materials(source_objects, key, level["texture"])
    wrapper = bpy.data.objects.new(f"LOD::{key}", None)
    wrapper.location = position
    collection.objects.link(wrapper)
    clones = []
    for source in source_objects:
        clone = source.copy()
        clone.name = f"{key}::{source.name.removeprefix('SCALE::')}"
        clone.data = source.data.copy()
        clone.animation_data_clear()
        clone.parent = wrapper
        clone.matrix_parent_inverse.identity()
        clone.matrix_world = source.matrix_world.copy()
        clone.location -= source_center
        clone.hide_render = False
        clone.hide_viewport = False
        clone.data.materials.clear()
        for material in source.data.materials:
            if material:
                clone.data.materials.append(material_map[material])
        collection.objects.link(clone)
        clones.append(clone)

    original_triangles = triangle_count(clones)
    target = level["target"] or original_triangles
    ratio = min(1.0, target / max(1, original_triangles))
    if ratio < 0.999:
        for clone in clones:
            if len(clone.data.polygons) < 12:
                continue
            bpy.context.view_layer.objects.active = clone
            clone.select_set(True)
            modifier = clone.modifiers.new("WEB_LOD", "DECIMATE")
            modifier.ratio = ratio
            modifier.use_collapse_triangulate = True
            bpy.ops.object.modifier_apply(modifier=modifier.name)
            clone.select_set(False)
            for polygon in clone.data.polygons:
                polygon.use_smooth = True

    triangles = triangle_count(clones)
    decoded = sum(int(image.size[0]) * int(image.size[1]) * 4 * 4 / 3 for image in image_map.values())
    return {
        **level,
        "wrapper": wrapper,
        "objects": clones,
        "triangles": triangles,
        "vertices": sum(len(clone.data.vertices) for clone in clones),
        "images": list(image_map.values()),
        "texture_gpu_mib": decoded / 1048576,
    }


def material(name, color, emission=0.0):
    result = bpy.data.materials.new(name)
    result.use_nodes = True
    shader = next(node for node in result.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Roughness"].default_value = 0.72
    shader.inputs["Emission Color"].default_value = color
    shader.inputs["Emission Strength"].default_value = emission
    return result


def label(collection, text, position, size, assigned):
    curve = bpy.data.curves.new(f"Label::{text}", "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.005
    curve.materials.append(assigned)
    obj = bpy.data.objects.new(f"Label::{text}", curve)
    obj.location = position
    obj.rotation_euler = (math.pi / 2, 0, 0)
    collection.objects.link(obj)
    return obj


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_light(name, kind, location, energy, color, size=6):
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
    return obj


def make_camera(name, location, target, ortho):
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = ortho
    data.clip_start = 0.1
    data.clip_end = 200
    camera = bpy.data.objects.new(name, data)
    camera.location = location
    bpy.context.scene.collection.objects.link(camera)
    look_at(camera, target)
    return camera


def setup_scene(scene):
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.004, 0.008, 0.014, 1)
    background.inputs["Strength"].default_value = 0.2
    scene.view_settings.look = "AgX - Medium High Contrast"


def export_glb(level):
    bpy.ops.object.select_all(action="DESELECT")
    level["wrapper"].select_set(True)
    for obj in level["objects"]:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = level["wrapper"]
    output = WEB / f"timber-hearth-{level['key']}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(output),
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
    level["glb_bytes"] = output.stat().st_size


def main():
    source_root = bpy.data.objects.get("SCALE::Timber Hearth / R250")
    if source_root is None:
        raise RuntimeError("Open outer_wilds_true_scale_catalog.blend before running this builder")
    source_objects = [obj for obj in descendants(source_root) if obj.type == "MESH" and not obj.hide_render]
    low, high = world_bounds(source_objects)
    center = (low + high) * 0.5
    hide_existing_scene()
    comparison = new_collection("TIMBER HEARTH / WEB LOD COMPARISON")
    setup_scene(bpy.context.scene)

    positions = [-12, -6, 0, 6, 12]
    results = [
        clone_level(source_objects, center, level, Vector((x, 0, 0.65)), comparison)
        for level, x in zip(LEVELS, positions)
    ]

    label_mat = material("Comparison labels", (0.72, 0.83, 0.87, 1), 0.3)
    title_mat = material("Comparison title", (1.0, 0.62, 0.24, 1), 0.55)
    for result, x in zip(results, positions):
        label(
            comparison,
            f"{result['label']}\n{result['triangles']:,} tris  /  {result['texture']} px",
            (x, -0.8, -2.55),
            0.3,
            label_mat,
        )
    label(comparison, "TIMBER HEARTH / GEOMETRY + TEXTURE LOD", (0, -0.8, 4.25), 0.48, title_mat)

    add_light("LOD Key", "AREA", (-8, -12, 11), 1150, (1.0, 0.72, 0.46), 10)
    add_light("LOD Fill", "AREA", (10, -9, 4), 850, (0.42, 0.65, 1.0), 8)
    add_light("LOD Rim", "AREA", (0, 3, 10), 900, (0.3, 0.65, 0.78), 8)

    scene = bpy.context.scene
    overview = make_camera("LOD Comparison Camera", (0, -34, 7.2), (0, 0, 0.65), 35)
    scene.camera = overview
    scene.render.resolution_x = 3200
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(OUTPUT / "timber-hearth-lod-comparison.png")
    bpy.ops.render.render(write_still=True)

    labels = [obj for obj in comparison.objects if obj.type == "FONT"]
    for obj in labels:
        obj.hide_render = True
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    detail = make_camera("LOD Detail Camera", (0, -12, 4.2), (0, 0, 0.65), 6.6)
    scene.camera = detail
    for result, x in zip(results, positions):
        detail.location.x = x
        look_at(detail, (x, 0, 0.65))
        scene.render.filepath = str(OUTPUT / f"timber-hearth-{result['key']}.png")
        bpy.ops.render.render(write_still=True)
        export_glb(result)
    for obj in labels:
        obj.hide_render = False

    metrics = []
    for result in results:
        metrics.append({
            "key": result["key"],
            "label": result["label"],
            "triangles": result["triangles"],
            "vertices": result["vertices"],
            "texture_max": result["texture"],
            "texture_gpu_mib": round(result["texture_gpu_mib"], 2),
            "glb_mib": round(result["glb_bytes"] / 1048576, 2),
        })
    (ROOT / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
    readme = bpy.data.texts.new("README - Timber Hearth LOD comparison")
    readme.write(
        "All five models use the same extracted Timber Hearth distant-proxy source, camera, transform and lighting.\n"
        "Each step reduces geometry with Blender Collapse Decimate and reduces the longest texture edge.\n"
        "GLB measurements use WebP quality 80 and EXT_meshopt_compression.\n"
        "The comparison is intended to choose a web overview LOD, not replace the inspection-quality source.\n"
    )
    scene.camera = overview
    scene.render.resolution_x = 3200
    scene.render.resolution_y = 1100
    scene.render.filepath = str(OUTPUT / "timber-hearth-lod-comparison.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "timber-hearth-lod-comparison.blend"))
    print("METRICS", json.dumps(metrics, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
