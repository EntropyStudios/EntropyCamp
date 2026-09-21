#!/usr/bin/env python3
"""Build a physically scaled Outer Wilds celestial-body Blender comparison scene.

The existing distant-proxy catalog intentionally normalizes every object for
inspection. This builder starts from that catalog, removes the presentation
normalization, and applies one common game-unit scale to selected bodies.
"""

from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "scale-catalog"
OUTPUT.mkdir(parents=True, exist_ok=True)
NINE_BLEND = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "all-distant-proxies" / "blender" / "outer_wilds_nine_proxies.blend"
SUN_BLEND = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "sun-and-dlc" / "blender" / "outer_wilds_sun_dlc.blend"

# One Blender unit represents 100 Unity/game units. The ratio is unchanged;
# this keeps the 2,000-unit Sun practical to frame beside the planets.
GAME_TO_BLENDER = 0.01


def descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    result: list[bpy.types.Object] = []
    stack = [root]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(reversed(list(current.children)))
    return result


def bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector] | None:
    points = [
        obj.matrix_world @ Vector(corner)
        for obj in objects
        if obj.type == "MESH" and not obj.hide_render
        for corner in obj.bound_box
    ]
    if not points:
        return None
    low = Vector((min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)))
    high = Vector((max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)))
    return low, high


def find_catalog_ancestor(obj: bpy.types.Object) -> bpy.types.Object | None:
    current = obj
    while current:
        if current.name.startswith("CATALOG::"):
            return current
        current = current.parent
    return None


def source_roots(collection_name: str, root_names: list[str]) -> list[tuple[bpy.types.Object, bpy.types.Object]]:
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        raise RuntimeError(f"Missing source collection: {collection_name}")
    roots = []
    for name in root_names:
        root = bpy.data.objects.get(name)
        if root is None or root.name not in collection.objects:
            raise RuntimeError(f"Missing source root {name!r} in {collection_name}")
        catalog = find_catalog_ancestor(root)
        if catalog is None:
            raise RuntimeError(f"Source root {name!r} has no catalog ancestor")
        roots.append((root, catalog))
    return roots


def clone_raw(root: bpy.types.Object, catalog: bpy.types.Object, collection: bpy.types.Collection) -> tuple[bpy.types.Object, list[bpy.types.Object], dict[bpy.types.Object, Matrix]]:
    """Clone a proxy subtree and retain its world matrices in catalog-local space."""
    source = descendants(root)
    source_matrices = {original: catalog.matrix_world.inverted() @ original.matrix_world for original in source}
    mapping: dict[bpy.types.Object, bpy.types.Object] = {}
    for original in source:
        clone = original.copy()
        if original.data:
            clone.data = original.data
        clone.animation_data_clear()
        clone.name = f"SCALE::{original.name}"
        collection.objects.link(clone)
        mapping[original] = clone

    for original, clone in mapping.items():
        parent = mapping.get(original.parent)
        clone.parent = parent
        clone.hide_viewport = False
        if (
            "fogsphere" in original.name.lower()
            or "volumetricfog" in original.name.lower()
            or "dusttail" in original.name.lower()
            or "gastail" in original.name.lower()
            or "sandcolumn" in original.name.lower()
        ):
            clone.hide_render = True
            clone.hide_viewport = True
    return mapping[root], list(mapping.values()), {mapping[original]: matrix for original, matrix in source_matrices.items()}


def make_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def make_material(name: str, color: tuple[float, float, float, float], emission: float = 0.0, alpha: float = 1.0):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    if alpha < 1:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        shader = nodes.new("ShaderNodeEmission")
        shader.inputs["Color"].default_value = color
        shader.inputs["Strength"].default_value = emission
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = 1 - alpha
        links.new(transparent.outputs[0], mix.inputs[1])
        links.new(shader.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs[0])
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
    else:
        shader = nodes.new("ShaderNodeEmission")
        shader.inputs["Color"].default_value = color
        shader.inputs["Strength"].default_value = emission
        links.new(shader.outputs[0], output.inputs[0])
    material.diffuse_color = (*color[:3], alpha)
    return material


def replace_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    if obj.type != "MESH":
        return
    obj.data.materials.clear()
    obj.data.materials.append(material)


def make_text(collection: bpy.types.Collection, body: str, location: tuple[float, float, float], camera: bpy.types.Object, size: float = 0.45, material=None):
    curve = bpy.data.curves.new(f"Text::{body}", "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.006
    text = bpy.data.objects.new(f"Text::{body}", curve)
    collection.objects.link(text)
    text.location = location
    if camera is not None:
        text.rotation_euler = (camera.location - text.location).to_track_quat("Z", "Y").to_euler()
    if material:
        curve.materials.append(material)
    return text


def make_line(collection: bpy.types.Collection, name: str, start: tuple[float, float, float], end: tuple[float, float, float], material):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = 0.018
    curve.bevel_resolution = 2
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (*start, 1)
    spline.points[1].co = (*end, 1)
    obj = bpy.data.objects.new(name, curve)
    collection.objects.link(obj)
    curve.materials.append(material)
    return obj


def setup_world(scene: bpy.types.Scene) -> None:
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 3200
    scene.render.resolution_y = 1400
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.003, 0.008, 0.018, 1)
    background.inputs["Strength"].default_value = 0.16
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.use_nodes = True
    tree = bpy.data.node_groups.new("True Scale Catalog Compositor", "CompositorNodeTree")
    scene.compositing_node_group = tree
    tree.nodes.clear()
    layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 0.65
    glare.inputs["Size"].default_value = 7
    tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    output = tree.nodes.new("NodeGroupOutput")
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], output.inputs["Image"])


def append_sun() -> bpy.types.Object:
    before = set(bpy.data.objects)
    with bpy.data.libraries.load(str(SUN_BLEND), link=False) as (source, target):
        target.objects = ["Sun - sphere reconstruction for runtime surface"]
    obj = next(obj for obj in target.objects if obj and obj not in before)
    obj.name = "SCALE::Sun_Surface"
    return obj


def configure_sun(obj: bpy.types.Object, collection: bpy.types.Collection, center: Vector) -> bpy.types.Object:
    wrapper = bpy.data.objects.new("SCALE::SUN / radius 2000", None)
    collection.objects.link(wrapper)
    obj.parent = wrapper
    obj.location = (0, 0, 0)
    obj.rotation_euler = (0, 0, 0)
    obj.scale = (40 / max(obj.dimensions.x, 0.001),) * 3
    wrapper.location = center
    wrapper["game_radius"] = 2000
    wrapper["game_diameter"] = 4000
    wrapper["scale_basis"] = "1 Blender unit = 100 game units"
    return wrapper


def build_white_hole(collection: bpy.types.Collection, center: Vector, radius: float) -> bpy.types.Object:
    root = bpy.data.objects.new("SCALE::WHITE_HOLE / visual radius 100", None)
    collection.objects.link(root)
    root.location = center
    root["visual_radius_game_units"] = 100
    root["note"] = "Visual anomaly; not a solid planetary body"

    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=radius, location=center)
    core = bpy.context.object
    core.name = "WhiteHole luminous core"
    core.data.name = "WhiteHole_Core_Mesh"
    core.parent = root
    core.location = (0, 0, 0)
    core_material = make_material("WhiteHole Core Glow", (0.88, 0.98, 1.0, 1), 10.0)
    core.data.materials.append(core_material)
    core_emission = next(node for node in core_material.node_tree.nodes if node.type == "EMISSION")
    core_driver = core_emission.inputs["Strength"].driver_add("default_value").driver
    core_driver.expression = "9 + 1.5 * sin((frame - 1) * 0.12)"
    collection.objects.link(core)

    for index, factor in enumerate((1.25, 1.6)):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=radius * factor, location=center)
        shell = bpy.context.object
        shell.name = f"WhiteHole halo shell {index + 1}"
        shell.parent = root
        shell.location = (0, 0, 0)
        shell.data.materials.append(make_material(f"WhiteHole Halo {index + 1}", (0.35, 0.82, 1.0, 1), 3.0 / (index + 1), 0.12))
        for axis in range(3):
            driver = shell.driver_add("scale", axis).driver
            driver.expression = f"1 + 0.04 * sin((frame - 1) * 0.10 + {index} * pi)"
        collection.objects.link(shell)

    bpy.ops.mesh.primitive_torus_add(major_radius=radius * 1.2, minor_radius=radius * 0.025, major_segments=96, minor_segments=12, location=center, rotation=(math.pi / 2, 0, 0))
    ring = bpy.context.object
    ring.name = "WhiteHole accretion ring"
    ring.parent = root
    ring.location = (0, 0, 0)
    ring.data.materials.append(make_material("WhiteHole Ring Glow", (0.45, 0.9, 1.0, 1), 8.0))
    ring_driver = ring.driver_add("rotation_euler", 2).driver
    ring_driver.expression = "(frame - 1) * 0.018"
    collection.objects.link(ring)
    return root


def add_light(name: str, kind: str, location: tuple[float, float, float], energy: float, color: tuple[float, float, float], radius: float = 5.0):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "POINT":
        data.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    return obj


def add_scaled_asset(source_collection: str, root_name: str, output_collection: bpy.types.Collection, name: str, center: Vector, target_diameter: float, *, reference_names: tuple[str, ...] = ()):
    root, catalog = source_roots(source_collection, [root_name])[0]
    clone_root, clones, local_matrices = clone_raw(root, catalog, output_collection)
    visible = [obj for obj in clones if obj.type == "MESH" and not obj.hide_render]
    reference = [obj for obj in visible if any(token.lower() in obj.name.lower() for token in reference_names)] if reference_names else visible
    if not reference:
        reference = visible
    reference_points = [local_matrices[obj] @ Vector(corner) for obj in reference for corner in obj.bound_box]
    if reference_points:
        low = Vector(tuple(min(point[i] for point in reference_points) for i in range(3)))
        high = Vector(tuple(max(point[i] for point in reference_points) for i in range(3)))
    else:
        low, high = Vector((-1, -1, -1)), Vector((1, 1, 1))
    center_raw = (low + high) * 0.5
    size_raw = max(high - low)
    scale = target_diameter / max(size_raw, 0.001)
    wrapper = bpy.data.objects.new(f"SCALE::{name}", None)
    output_collection.objects.link(wrapper)
    wrapper.matrix_world = Matrix.Translation(center) @ Matrix.Scale(scale, 4) @ Matrix.Translation(-center_raw)
    # A flat presentation copy avoids retaining transforms whose original
    # parents live outside the selected body subtree (for example moon pivots).
    for clone in clones:
        if clone.type not in {"MESH", "CURVE"}:
            clone.hide_render = True
            clone.hide_viewport = True
            continue
        clone.parent = wrapper
        clone.matrix_parent_inverse.identity()
        clone.matrix_basis = local_matrices[clone]
    wrapper["game_diameter_reference"] = target_diameter / GAME_TO_BLENDER
    wrapper["game_radius_reference"] = target_diameter / GAME_TO_BLENDER / 2
    wrapper["source_collection"] = source_collection
    wrapper["source_root"] = root_name
    return wrapper


def make_camera(collection: bpy.types.Collection) -> bpy.types.Object:
    data = bpy.data.cameras.new("Scale Catalog Camera")
    data.type = "ORTHO"
    data.ortho_scale = 144
    data.clip_start = 0.1
    data.clip_end = 180
    camera = bpy.data.objects.new("Scale Catalog Camera", data)
    camera.location = (20, -90, 9)
    camera.rotation_euler = (Vector((20, 0, 9)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def clear_objects() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        if collection.name != "Collection" and collection.users == 0:
            bpy.data.collections.remove(collection)


def configure_viewports(camera: bpy.types.Object) -> None:
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.shading.type = "RENDERED"
            space.shading.use_scene_world = True
            space.shading.use_scene_lights = True
            space.region_3d.view_perspective = "CAMERA"
            space.region_3d.view_camera_zoom = 0
            space.clip_end = 500
            space.overlay.show_overlays = False


def main() -> None:
    # This script is run with the nine-proxy blend as its input, so source
    # objects are still available while we clone them.
    source_data = {
        "TimberHearth_DistantProxy",
        "BrittleHollow_DistantProxy",
        "AshTwin_DistantProxy",
        "EmberTwin_DistantProxy",
        "GiantsDeep_DistantProxy",
        "QuantumMoon_DistantProxy",
        "Comet_DistantProxy",
        "DarkBramble_DistantProxy",
        "WhiteHole_DistantProxy",
    }
    if not all(bpy.data.collections.get(name) for name in source_data):
        raise RuntimeError("Run this builder with outer_wilds_nine_proxies.blend as the input file")

    scene = bpy.context.scene
    scene.render.fps = 30
    scene.frame_start = 1
    scene.frame_end = 240
    # Clone source trees before removing the normalized catalog objects.
    output_root = make_collection("SCALE CATALOG / 1:100 GAME UNITS")
    satellites = make_collection("01 SATELLITES / SMALL BODIES")
    planets = make_collection("02 PLANETS / REFERENCE RADII")
    stars = make_collection("03 STARS AND ANOMALIES")
    guides = make_collection("04 SCALE GUIDES")
    setup_world(scene)

    # Main linear layout. Values are game reference diameters converted to
    # Blender units by GAME_TO_BLENDER.
    assets = []
    assets.append(("Attlerock / R100", "TimberHearth_DistantProxy", "Moon_Pivot", satellites, Vector((-38, 0, 1)), 200 * GAME_TO_BLENDER, ("Terrain_THM",)))
    assets.append(("Quantum Moon / R110", "QuantumMoon_DistantProxy", "QuantumMoon_DistantProxy", satellites, Vector((-33, 0, 1)), 220 * GAME_TO_BLENDER, ()))
    assets.append(("Interloper / R110 nominal", "Comet_DistantProxy", "Comet_DistantProxy", satellites, Vector((-28, 0, 1)), 220 * GAME_TO_BLENDER, ("Proxy_CO_Melting", "Proxy_CO_Surface")))
    assets.append(("Hollow's Lantern / R130", "BrittleHollow_DistantProxy", "VolcanicMoon_Pivot", satellites, Vector((-23, 0, 1)), 260 * GAME_TO_BLENDER, ("VolcanicMoon",)))
    assets.append(("Ash Twin / R200", "AshTwin_DistantProxy", "AshTwin_DistantProxy", planets, Vector((-16, 0, 1)), 400 * GAME_TO_BLENDER, ("Terrain_Proxy_TT",)))
    assets.append(("Ember Twin / R200", "EmberTwin_DistantProxy", "EmberTwin_DistantProxy", planets, Vector((-9, 0, 1)), 400 * GAME_TO_BLENDER, ("Terrain_Proxy_CT",)))
    assets.append(("Timber Hearth / R250", "TimberHearth_DistantProxy", "Proxy_TH", planets, Vector((-1, 0, 1)), 500 * GAME_TO_BLENDER, ("BakedTerrain_TH", "Terrain_TH")))
    assets.append(("Brittle Hollow / R300", "BrittleHollow_DistantProxy", "Proxy_BH", planets, Vector((8, 0, 1)), 600 * GAME_TO_BLENDER, ()))
    assets.append(("Dark Bramble / R650 envelope", "DarkBramble_DistantProxy", "DarkBramble_DistantProxy", planets, Vector((21, 0, 1)), 1300 * GAME_TO_BLENDER, ()))
    assets.append(("Giant's Deep / R950 cloud top", "GiantsDeep_DistantProxy", "GiantsDeep_DistantProxy", planets, Vector((39, 0, 1)), 1900 * GAME_TO_BLENDER, ("CloudsTopLayer",)))

    created = []
    for label, group, root, collection, center, diameter, reference in assets:
        created.append((label, add_scaled_asset(group, root, collection, label, center, diameter, reference_names=reference), center, diameter))

    sun_collection = stars
    sun = append_sun()
    sun_wrapper = configure_sun(sun, sun_collection, Vector((70, 0, 9)))
    if sun.users_collection:
        for current in list(sun.users_collection):
            current.objects.unlink(sun)
    sun_collection.objects.link(sun)
    add_light("Sun illumination", "POINT", (70, -3, 9), 220, (1.0, 0.55, 0.22), 8)

    build_white_hole(stars, Vector((48, 0, -14)), 1.0)
    add_light("White hole cyan glow", "POINT", (48, -2, -14), 500, (0.35, 0.8, 1.0), 3)

    # Keep the source catalog in the file for provenance, but hide its
    # presentation-normalized copies so only the common-scale scene renders.
    for collection_name in source_data:
        collection = bpy.data.collections.get(collection_name)
        if collection:
            collection.hide_render = True
            collection.hide_viewport = True
    for collection in list(bpy.data.collections):
        if collection.name.startswith("PRESENTATION"):
            collection.hide_render = True
            collection.hide_viewport = True

    guide_material = make_material("Scale guide", (0.25, 0.48, 0.64, 1), 0.8)
    label_material = make_material("Scale labels", (0.72, 0.86, 0.95, 1), 0.5)
    title_material = make_material("Scale title", (1.0, 0.68, 0.26, 1), 0.8)
    make_line(guides, "Scale baseline", (-41, 0.15, -1.5), (91, 0.15, -1.5), guide_material)
    for game_value, x in ((100, -38), (250, -1), (650, 21), (950, 39), (2000, 70)):
        make_line(guides, f"Tick {game_value}", (x, 0.15, -1.72), (x, 0.15, -1.28), guide_material)
    for label, _, center, _diameter in created:
        make_text(guides, label.replace(" / ", "\n"), (center.x, -0.9, -2.6), None, 0.42, label_material)
    make_text(guides, "SATELLITES / SMALL BODIES", (-30, -0.9, 5.0), None, 0.8, title_material)
    make_text(guides, "PLANETS", (10, -0.9, 13.0), None, 0.8, title_material)
    make_text(guides, "STAR", (70, -0.9, 31.0), None, 0.8, title_material)
    make_text(guides, "OUTER WILDS / TRUE REFERENCE SCALE  ·  1 BLENDER UNIT = 100 GAME UNITS", (14, -0.9, 36.0), None, 1.0, title_material)
    make_text(guides, "WHITE HOLE\nvisual anomaly", (48, -0.9, -16.5), None, 0.5, label_material)
    make_text(guides, "Giant's Deep: sea R500 / visible cloud top R950  ·  Sun R2000", (29, -0.9, -20.5), None, 0.48, label_material)

    camera = make_camera(guides)
    for obj in guides.objects:
        if obj.type == "FONT":
            obj.rotation_euler = (camera.location - obj.location).to_track_quat("Z", "Y").to_euler()

    add_light("Neutral fill", "AREA", (5, -18, 20), 1500, (0.58, 0.7, 0.88), 18)
    add_light("Warm rim", "AREA", (-25, -5, 8), 500, (0.7, 0.35, 0.15), 12)
    scene.camera = camera
    scene.render.filepath = str(OUTPUT / "outer_wilds_true_scale_catalog.png")
    configure_viewports(camera)

    readme = bpy.data.texts.new("README - true reference scale")
    readme.write(
        "This scene uses one common scale: 1 Blender unit = 100 Outer Wilds game units.\n"
        "Reference radii read from the local Unity scene: Attlerock 100, Hollow's Lantern 130, Quantum Moon 110, Interloper 110 nominal, Ash/Ember 200, Timber Hearth 250, Brittle Hollow 300, Giant's Deep sea surface 500, Sun 2000.\n"
        "The distant-proxy meshes are original extracted game assets, but their proxy geometry was authored for distant rendering. Each selected envelope is fitted to its verified gameplay reference radius while retaining its extracted textures and proportions.\n"
        "The Sun uses the extracted heightmap/color-ramp reconstruction from the Sun+DLC catalog. White hole glow is rebuilt with emission shells, a ring, point light, and Eevee fog glow; Unity's runtime post-processing/lensing is not included.\n"
        "The old normalized catalog remains in the file but is hidden for provenance.\n"
    )
    bpy.ops.render.render(write_still=True)

    detail_data = bpy.data.cameras.new("Luminosity Detail Camera")
    detail_data.type = "ORTHO"
    detail_data.ortho_scale = 64
    detail_data.clip_start = 0.1
    detail_data.clip_end = 180
    detail_camera = bpy.data.objects.new("Luminosity Detail Camera", detail_data)
    detail_camera.location = (60, -90, 2)
    detail_camera.rotation_euler = (Vector((60, 0, 2)) - detail_camera.location).to_track_quat("-Z", "Y").to_euler()
    guides.objects.link(detail_camera)
    scene.camera = detail_camera
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.filepath = str(OUTPUT / "outer_wilds_luminous_bodies_detail.png")
    bpy.ops.render.render(write_still=True)
    scene.camera = camera
    scene.render.resolution_x = 3200
    scene.render.resolution_y = 1400
    scene.render.filepath = str(OUTPUT / "outer_wilds_true_scale_catalog.png")
    bpy.ops.object.select_all(action="DESELECT")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "outer_wilds_true_scale_catalog.blend"))
    print({"output": str(OUTPUT), "assets": len(created), "objects": len(bpy.data.objects), "materials": len(bpy.data.materials)}, flush=True)


if __name__ == "__main__":
    main()
