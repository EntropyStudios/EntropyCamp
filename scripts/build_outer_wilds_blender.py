#!/usr/bin/env python3
"""Build a local-only Blender study of the Outer Wilds planetary system."""

from __future__ import annotations

import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "private" / "outer-wilds-blender"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TAU = math.tau
FRAMES = 240
RNG = random.Random(2242019)


def color(hex_value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    value = hex_value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)) + (alpha,)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def principled_input(shader, *names: str):
    for name in names:
        value = shader.inputs.get(name)
        if value is not None:
            return value
    return None


def basic_material(
    name: str,
    base: str,
    *,
    roughness: float = 0.65,
    metallic: float = 0.0,
    emission: str | None = None,
    emission_strength: float = 0.0,
    alpha: float = 1.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    material.diffuse_color = color(base, alpha)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    shader = next((node for node in nodes if node.type == "BSDF_PRINCIPLED"), None)
    if shader is None:
        shader = nodes.new("ShaderNodeBsdfPrincipled")
    output = next((node for node in nodes if node.type == "OUTPUT_MATERIAL"), None)
    if output is None:
        output = nodes.new("ShaderNodeOutputMaterial")
    if not shader.outputs["BSDF"].is_linked:
        links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    principled_input(shader, "Base Color").default_value = color(base)
    principled_input(shader, "Roughness").default_value = roughness
    principled_input(shader, "Metallic").default_value = metallic
    if emission and emission_strength:
        principled_input(shader, "Emission Color", "Emission").default_value = color(emission)
        principled_input(shader, "Emission Strength").default_value = emission_strength
    if alpha < 1:
        principled_input(shader, "Alpha").default_value = alpha
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "BLENDED"
        elif hasattr(material, "blend_method"):
            material.blend_method = "BLEND"
        material.use_transparency_overlap = False
    return material


def noise_material(
    name: str,
    palette: list[tuple[float, str]],
    *,
    scale: float = 3.5,
    detail: float = 4.0,
    roughness: float = 0.72,
    bump: float = 0.18,
    emission_strength: float = 0.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    bump_node = nodes.new("ShaderNodeBump")

    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = detail
    noise.inputs["Roughness"].default_value = 0.72
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    first = ramp.color_ramp.elements[0]
    first.position = palette[0][0]
    first.color = color(palette[0][1])
    for position, hex_value in palette[1:]:
        element = ramp.color_ramp.elements.new(position)
        element.color = color(hex_value)

    principled_input(shader, "Roughness").default_value = roughness
    if emission_strength:
        principled_input(shader, "Emission Strength").default_value = emission_strength
    bump_node.inputs["Strength"].default_value = bump
    bump_node.inputs["Distance"].default_value = 0.16

    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], principled_input(shader, "Base Color"))
    if emission_strength:
        links.new(ramp.outputs["Color"], principled_input(shader, "Emission Color", "Emission"))
    links.new(noise.outputs["Fac"], bump_node.inputs["Height"])
    links.new(bump_node.outputs["Normal"], principled_input(shader, "Normal"))
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def banded_material(
    name: str,
    palette: list[tuple[float, str]],
    *,
    bands: float = 10.0,
    emission_strength: float = 0.04,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    texcoord = nodes.new("ShaderNodeTexCoord")
    separate = nodes.new("ShaderNodeSeparateXYZ")
    multiply = nodes.new("ShaderNodeMath")
    sine = nodes.new("ShaderNodeMath")
    noise = nodes.new("ShaderNodeTexNoise")
    mix = nodes.new("ShaderNodeMath")
    ramp = nodes.new("ShaderNodeValToRGB")

    multiply.operation = "MULTIPLY"
    multiply.inputs[1].default_value = bands
    sine.operation = "SINE"
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 2.4
    noise.inputs["Detail"].default_value = 3.0
    mix.operation = "ADD"
    mix.inputs[1].default_value = 0.0

    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    first = ramp.color_ramp.elements[0]
    first.position = palette[0][0]
    first.color = color(palette[0][1])
    for position, hex_value in palette[1:]:
        element = ramp.color_ramp.elements.new(position)
        element.color = color(hex_value)

    principled_input(shader, "Roughness").default_value = 0.58
    principled_input(shader, "Emission Strength").default_value = emission_strength
    links.new(texcoord.outputs["Generated"], separate.inputs["Vector"])
    links.new(separate.outputs["Z"], multiply.inputs[0])
    links.new(multiply.outputs[0], sine.inputs[0])
    links.new(sine.outputs[0], mix.inputs[0])
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], mix.inputs[1])
    links.new(mix.outputs[0], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], principled_input(shader, "Base Color"))
    links.new(ramp.outputs["Color"], principled_input(shader, "Emission Color", "Emission"))
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def atmosphere_material(name: str, tint: str, strength: float = 1.0, alpha: float = 0.3):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    layer = nodes.new("ShaderNodeLayerWeight")
    subtract = nodes.new("ShaderNodeMath")
    power = nodes.new("ShaderNodeMath")
    multiply = nodes.new("ShaderNodeMath")

    subtract.operation = "SUBTRACT"
    subtract.inputs[0].default_value = 1.0
    power.operation = "POWER"
    power.inputs[1].default_value = 2.2
    multiply.operation = "MULTIPLY"
    multiply.inputs[1].default_value = alpha

    principled_input(shader, "Base Color").default_value = color(tint)
    principled_input(shader, "Roughness").default_value = 0.18
    principled_input(shader, "Emission Color", "Emission").default_value = color(tint)
    principled_input(shader, "Emission Strength").default_value = strength
    principled_input(shader, "Alpha").default_value = alpha

    links.new(layer.outputs["Facing"], subtract.inputs[1])
    links.new(subtract.outputs[0], power.inputs[0])
    links.new(power.outputs[0], multiply.inputs[0])
    links.new(multiply.outputs[0], principled_input(shader, "Alpha"))
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "BLENDED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"
    material.use_transparency_overlap = False
    return material


def make_root(name: str) -> bpy.types.Object:
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    return root


def attach(obj: bpy.types.Object, parent: bpy.types.Object) -> bpy.types.Object:
    obj.parent = parent
    return obj


def deterministic_noise(point: Vector, seed: float) -> float:
    return (
        math.sin(point.x * 5.17 + seed * 1.37)
        + math.sin(point.y * 7.13 - seed * 0.91)
        + math.sin(point.z * 9.71 + point.x * 2.4 + seed)
    ) / 3.0


def add_ico(
    name: str,
    *,
    radius: float,
    material: bpy.types.Material,
    location=(0.0, 0.0, 0.0),
    subdivisions: int = 3,
    displacement: float = 0.0,
    seed: float = 0.0,
    parent: bpy.types.Object | None = None,
    smooth: bool = True,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    if displacement:
        for vertex in obj.data.vertices:
            direction = vertex.co.normalized()
            vertex.co *= 1 + deterministic_noise(direction, seed) * displacement
    for polygon in obj.data.polygons:
        polygon.use_smooth = smooth
    if parent:
        attach(obj, parent)
    return obj


def add_uv_sphere(
    name: str,
    *,
    radius: float,
    material: bpy.types.Material,
    location=(0.0, 0.0, 0.0),
    segments: int = 64,
    rings: int = 32,
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        radius=radius,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if parent:
        attach(obj, parent)
    return obj


def add_torus(
    name: str,
    *,
    major_radius: float,
    minor_radius: float,
    material: bpy.types.Material,
    location=(0.0, 0.0, 0.0),
    rotation=(0.0, 0.0, 0.0),
    parent: bpy.types.Object | None = None,
    major_segments: int = 72,
    minor_segments: int = 10,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=major_segments,
        minor_segments=minor_segments,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    if parent:
        attach(obj, parent)
    return obj


def add_box(
    name: str,
    *,
    dimensions: tuple[float, float, float],
    material: bpy.types.Material,
    location=(0.0, 0.0, 0.0),
    rotation=(0.0, 0.0, 0.0),
    parent: bpy.types.Object | None = None,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bevel = obj.modifiers.new("Soft edges", "BEVEL")
    bevel.width = min(dimensions) * 0.12
    bevel.segments = 2
    if parent:
        attach(obj, parent)
    return obj


def orient_z(obj: bpy.types.Object, direction: Vector) -> None:
    obj.rotation_euler = Vector((0, 0, 1)).rotation_difference(direction.normalized()).to_euler()


def add_cone(
    name: str,
    *,
    radius1: float,
    radius2: float,
    depth: float,
    material: bpy.types.Material,
    location: Vector,
    direction: Vector,
    parent: bpy.types.Object | None = None,
    vertices: int = 7,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        location=location,
    )
    obj = bpy.context.object
    obj.name = name
    orient_z(obj, direction)
    obj.data.materials.append(material)
    if parent:
        attach(obj, parent)
    return obj


def add_curve(
    name: str,
    points: list[Vector],
    *,
    material: bpy.types.Material,
    bevel: float = 0.05,
    parent: bpy.types.Object | None = None,
    resolution: int = 2,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = bevel
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for control, point in zip(spline.bezier_points, points):
        control.co = point
        control.handle_left_type = "AUTO"
        control.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    curve.materials.append(material)
    if parent:
        attach(obj, parent)
    return obj


def add_fragment_shell(
    name: str,
    *,
    radius: float,
    inner_radius: float,
    materials: list[bpy.types.Material],
    holes: list[Vector],
    parent: bpy.types.Object,
    seed: int,
    shrink: float = 0.87,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=radius)
    source = bpy.context.object
    source_vertices = [vertex.co.copy() for vertex in source.data.vertices]
    source_faces = [[source_vertices[index] for index in polygon.vertices] for polygon in source.data.polygons]
    bpy.data.objects.remove(source, do_unlink=True)

    rng = random.Random(seed)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    face_materials: list[int] = []
    normalized_holes = [hole.normalized() for hole in holes]

    for source_face in source_faces:
        center = sum(source_face, Vector()) / 3
        direction = center.normalized()
        if any(direction.dot(hole) > 0.82 for hole in normalized_holes):
            continue
        local_shrink = shrink + rng.uniform(-0.035, 0.025)
        outer = [center + (vertex - center) * local_shrink for vertex in source_face]
        outer = [vertex.normalized() * radius * (1 + rng.uniform(-0.025, 0.025)) for vertex in outer]
        inner = [vertex.normalized() * inner_radius for vertex in outer]
        offset = len(vertices)
        vertices.extend([tuple(vertex) for vertex in outer + inner])
        block_faces = [
            (offset, offset + 1, offset + 2),
            (offset + 5, offset + 4, offset + 3),
            (offset, offset + 3, offset + 4, offset + 1),
            (offset + 1, offset + 4, offset + 5, offset + 2),
            (offset + 2, offset + 5, offset + 3, offset),
        ]
        faces.extend(block_faces)
        material_index = rng.randrange(len(materials))
        face_materials.extend([material_index] * len(block_faces))

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    for material in materials:
        mesh.materials.append(material)
    for polygon, material_index in zip(mesh.polygons, face_materials):
        polygon.material_index = material_index
        polygon.use_smooth = False
    attach(obj, parent)
    return obj


def animate_rotation(obj: bpy.types.Object, axis: int, turns: float, frames: int = FRAMES) -> None:
    obj.rotation_mode = "XYZ"
    obj.rotation_euler[axis] = 0
    driver = obj.driver_add("rotation_euler", axis).driver
    driver.expression = f"(frame - 1) * {TAU * turns / frames:.12f}"


def create_sun(materials) -> bpy.types.Object:
    root = make_root("Sun.Root")
    spin = attach(make_root("Sun.Spin"), root)
    add_ico(
        "Sun",
        radius=1.45,
        material=materials["sun"],
        subdivisions=5,
        displacement=0.045,
        seed=1.2,
        parent=spin,
    )
    add_uv_sphere("Sun.Corona", radius=1.62, material=materials["sun_atmosphere"], parent=spin)
    for index, rotation in enumerate(((0.2, 0.4, 0), (1.1, 0.2, 0.5), (0.5, 1.0, 0.2))):
        add_torus(
            f"Sun.Prominence.{index}",
            major_radius=1.55,
            minor_radius=0.025,
            material=materials["sun_hot"],
            rotation=rotation,
            parent=spin,
        )
    station = attach(make_root("SunStation.Orbit"), spin)
    add_box(
        "SunStation.Body",
        dimensions=(0.42, 0.12, 0.14),
        material=materials["nomai_gold"],
        location=(2.1, 0, 0),
        parent=station,
    )
    add_torus(
        "SunStation.Ring",
        major_radius=0.16,
        minor_radius=0.025,
        material=materials["nomai_blue"],
        location=(2.1, 0, 0),
        rotation=(math.pi / 2, 0, 0),
        parent=station,
        major_segments=32,
        minor_segments=6,
    )
    animate_rotation(spin, 2, 0.7)
    animate_rotation(station, 1, 2.4)
    return root


def create_twins(materials) -> bpy.types.Object:
    root = make_root("HourglassTwins.Root")
    orbit = attach(make_root("HourglassTwins.Orbit"), root)
    ash_center = Vector((-1.05, 0, 0.12))
    ember_center = Vector((1.05, 0, -0.12))
    add_ico(
        "AshTwin",
        radius=0.76,
        material=materials["ash"],
        location=ash_center,
        subdivisions=4,
        displacement=0.055,
        seed=2.0,
        parent=orbit,
    )
    add_uv_sphere("AshTwin.Atmosphere", radius=0.83, material=materials["pink_atmosphere"], location=ash_center, parent=orbit)
    add_ico(
        "EmberTwin",
        radius=0.8,
        material=materials["ember"],
        location=ember_center,
        subdivisions=4,
        displacement=0.07,
        seed=3.0,
        parent=orbit,
    )
    add_uv_sphere("EmberTwin.Atmosphere", radius=0.87, material=materials["pink_atmosphere"], location=ember_center, parent=orbit)

    for index in range(7):
        angle = index / 7 * TAU
        normal = Vector((math.cos(angle), 0.18 * math.sin(angle * 2), math.sin(angle)))
        add_cone(
            f"AshTwin.Tower.{index}",
            radius1=0.055,
            radius2=0.018,
            depth=0.27,
            material=materials["nomai_gold"],
            location=ash_center + normal.normalized() * 0.82,
            direction=normal,
            parent=orbit,
            vertices=5,
        )
    for index, rotation in enumerate(((0.2, 0.5, 0.1), (0.9, 0.2, 0.7), (0.3, 1.1, 0.4))):
        add_torus(
            f"EmberTwin.Canyon.{index}",
            major_radius=0.63 + index * 0.035,
            minor_radius=0.025,
            material=materials["ember_dark"],
            location=ember_center,
            rotation=rotation,
            parent=orbit,
            major_segments=48,
            minor_segments=6,
        )

    sand_points = [
        ash_center + Vector((0.62, 0, 0.08)),
        Vector((-0.22, -0.03, 0.2)),
        Vector((0.22, 0.03, -0.2)),
        ember_center + Vector((-0.65, 0, -0.06)),
    ]
    add_curve("HourglassTwins.SandColumn", sand_points, material=materials["sand"], bevel=0.095, parent=orbit)
    for index in range(16):
        t = index / 15
        point = sand_points[0].lerp(sand_points[-1], t)
        point.y += math.sin(t * TAU * 2) * 0.07
        add_ico(
            f"HourglassTwins.Sand.{index}",
            radius=0.035 + 0.012 * math.sin(t * math.pi),
            material=materials["sand_hot"],
            location=point,
            subdivisions=1,
            parent=orbit,
            smooth=False,
        )
    animate_rotation(orbit, 1, 0.45)
    return root


def create_timber(materials) -> bpy.types.Object:
    root = make_root("TimberHearth.Root")
    spin = attach(make_root("TimberHearth.Spin"), root)
    add_ico(
        "TimberHearth",
        radius=1.0,
        material=materials["timber"],
        subdivisions=4,
        displacement=0.045,
        seed=4.0,
        parent=spin,
    )
    add_uv_sphere("TimberHearth.Atmosphere", radius=1.085, material=materials["blue_atmosphere"], parent=spin)
    for index in range(34):
        y = 1 - 2 * (index + 0.5) / 34
        radial = math.sqrt(max(0, 1 - y * y))
        angle = index * 2.399963
        normal = Vector((math.cos(angle) * radial, y, math.sin(angle) * radial))
        if normal.y > 0.74 or index % 7 == 0:
            continue
        add_cone(
            f"TimberHearth.Tree.{index}",
            radius1=0.045,
            radius2=0.0,
            depth=0.16,
            material=materials["forest"],
            location=normal * 1.055,
            direction=normal,
            parent=spin,
            vertices=6,
        )
    moon_orbit = attach(make_root("Attlerock.Orbit"), spin)
    add_ico(
        "Attlerock",
        radius=0.29,
        material=materials["attlerock"],
        location=(1.65, 0, 0.12),
        subdivisions=3,
        displacement=0.1,
        seed=5.0,
        parent=moon_orbit,
    )
    add_torus(
        "Attlerock.OrbitLine",
        major_radius=1.65,
        minor_radius=0.008,
        material=materials["orbit"],
        rotation=(math.pi / 2, 0, 0),
        parent=spin,
    )
    animate_rotation(spin, 2, 0.35)
    animate_rotation(moon_orbit, 1, 1.0)
    return root


def create_brittle(materials) -> bpy.types.Object:
    root = make_root("BrittleHollow.Root")
    spin = attach(make_root("BrittleHollow.Spin"), root)
    add_ico("BrittleHollow.Interior", radius=0.82, material=materials["brittle_inner"], subdivisions=3, parent=spin)
    add_fragment_shell(
        "BrittleHollow.Shell",
        radius=1.1,
        inner_radius=0.83,
        materials=[materials["brittle_a"], materials["brittle_b"], materials["brittle_c"]],
        holes=[Vector((0.3, -1, 0.25)), Vector((-0.7, -0.6, -0.25)), Vector((0.4, 0.3, 0.9))],
        parent=spin,
        seed=31,
    )
    add_uv_sphere("BrittleHollow.BlackHole", radius=0.26, material=materials["black_hole"], parent=spin)
    add_torus(
        "BrittleHollow.Accretion",
        major_radius=0.39,
        minor_radius=0.032,
        material=materials["black_hole_ring"],
        rotation=(1.15, 0.25, 0.3),
        parent=spin,
    )
    lantern_orbit = attach(make_root("HollowsLantern.Orbit"), spin)
    lantern_center = Vector((1.72, 0, 0.18))
    add_ico("HollowsLantern.Lava", radius=0.34, material=materials["lava"], location=lantern_center, subdivisions=3, parent=lantern_orbit)
    lantern_shell_root = attach(make_root("HollowsLantern.ShellRoot"), lantern_orbit)
    lantern_shell_root.location = lantern_center
    add_fragment_shell(
        "HollowsLantern.Crust",
        radius=0.4,
        inner_radius=0.32,
        materials=[materials["volcanic"], materials["volcanic_brown"]],
        holes=[Vector((0.2, -1, 0.2)), Vector((-0.8, -0.2, 0.5)), Vector((0.4, 0.2, -0.8))],
        parent=lantern_shell_root,
        seed=72,
        shrink=0.9,
    )
    add_torus(
        "HollowsLantern.OrbitLine",
        major_radius=1.72,
        minor_radius=0.008,
        material=materials["orbit"],
        rotation=(math.pi / 2, 0, 0),
        parent=spin,
    )
    animate_rotation(spin, 2, 0.3)
    animate_rotation(lantern_orbit, 1, 1.4)
    return root


def create_giants_deep(materials) -> bpy.types.Object:
    root = make_root("GiantsDeep.Root")
    spin = attach(make_root("GiantsDeep.Spin"), root)
    add_uv_sphere("GiantsDeep", radius=1.15, material=materials["giant"], parent=spin)
    add_uv_sphere("GiantsDeep.Atmosphere", radius=1.29, material=materials["cyan_atmosphere"], parent=spin)
    for index, height in enumerate((-0.75, -0.42, -0.12, 0.18, 0.48, 0.76)):
        ring_radius = math.sqrt(max(0.05, 1.16 * 1.16 - height * height))
        add_torus(
            f"GiantsDeep.CloudBand.{index}",
            major_radius=ring_radius,
            minor_radius=0.025 + 0.015 * (index % 2),
            material=materials["giant_cloud_a" if index % 2 else "giant_cloud_b"],
            location=(0, 0, height),
            parent=spin,
            major_segments=64,
            minor_segments=6,
        )
    for index, center in enumerate((Vector((-0.45, -1.0, 0.25)), Vector((0.55, -0.92, -0.18)))):
        points = []
        for step in range(10):
            t = step / 9
            angle = t * TAU * 1.6 + index * 2
            points.append(center + Vector((math.cos(angle) * 0.22 * (1 - t), -0.05 * t, math.sin(angle) * 0.22 * (1 - t))))
        add_curve(f"GiantsDeep.Cyclone.{index}", points, material=materials["storm"], bevel=0.028, parent=spin)

    cannon = attach(make_root("OrbitalProbeCannon.Orbit"), spin)
    cannon.location = (1.75, 0, 0.32)
    add_torus(
        "OrbitalProbeCannon.Ring",
        major_radius=0.32,
        minor_radius=0.045,
        material=materials["nomai_gold"],
        rotation=(math.pi / 2, 0.3, 0),
        parent=cannon,
        major_segments=36,
        minor_segments=7,
    )
    for index in range(3):
        angle = index / 3 * TAU
        add_box(
            f"OrbitalProbeCannon.Module.{index}",
            dimensions=(0.2, 0.08, 0.08),
            material=materials["nomai_blue"],
            location=(math.cos(angle) * 0.34, 0, math.sin(angle) * 0.34),
            rotation=(0, angle, 0),
            parent=cannon,
        )
    animate_rotation(spin, 2, 0.42)
    animate_rotation(cannon, 1, 1.1)
    return root


def create_dark_bramble(materials) -> bpy.types.Object:
    root = make_root("DarkBramble.Root")
    spin = attach(make_root("DarkBramble.Spin"), root)
    add_uv_sphere("DarkBramble.FogCore", radius=0.7, material=materials["bramble_fog"], parent=spin)
    shard_locations = [
        Vector((0.82, 0.0, 0.52)),
        Vector((-0.72, 0.08, 0.62)),
        Vector((0.58, 0.15, -0.78)),
        Vector((-0.75, -0.08, -0.62)),
        Vector((0.12, 0.42, 0.98)),
        Vector((-0.08, -0.35, -1.02)),
    ]
    for index, location in enumerate(shard_locations):
        shard = add_ico(
            f"DarkBramble.IceShard.{index}",
            radius=0.48,
            material=materials["bramble_ice_a" if index % 2 else "bramble_ice_b"],
            location=location,
            subdivisions=2,
            displacement=0.18,
            seed=8 + index,
            parent=spin,
            smooth=False,
        )
        shard.scale = (1.05, 0.58, 0.72)
        shard.rotation_euler = (index * 0.5, index * 0.72, index * 0.31)
        mid = location * 0.47 + Vector((0, -0.18 - index * 0.015, math.sin(index) * 0.12))
        add_curve(
            f"DarkBramble.Vine.{index}",
            [Vector((0, 0, 0)), mid, location * 0.92],
            material=materials["bramble_vine"],
            bevel=0.095,
            parent=spin,
        )
        if index < 4:
            branch_end = location * 0.72 + Vector(((-1) ** index * 0.45, 0.06, 0.22 * math.cos(index)))
            add_curve(
                f"DarkBramble.Branch.{index}",
                [mid * 0.8, branch_end],
                material=materials["bramble_vine_dark"],
                bevel=0.052,
                parent=spin,
            )
    add_uv_sphere("DarkBramble.SeedLight", radius=0.105, material=materials["white_hot"], location=(0, -0.68, 0), parent=spin)
    animate_rotation(spin, 2, 0.18)
    return root


def create_interloper(materials) -> bpy.types.Object:
    root = make_root("Interloper.Root")
    spin = attach(make_root("Interloper.Spin"), root)
    nucleus = add_ico(
        "Interloper",
        radius=0.62,
        material=materials["interloper"],
        subdivisions=3,
        displacement=0.16,
        seed=12,
        parent=spin,
    )
    nucleus.scale = (1.2, 0.72, 0.78)
    add_curve(
        "Interloper.Fissure",
        [Vector((-0.5, -0.45, -0.15)), Vector((0, -0.58, 0.16)), Vector((0.48, -0.42, 0.05))],
        material=materials["interloper_fissure"],
        bevel=0.035,
        parent=spin,
    )
    for index in range(6):
        offset = (index - 2.5) * 0.1
        add_curve(
            f"Interloper.Tail.{index}",
            [
                Vector((-0.48, 0.06 * index, offset)),
                Vector((-1.3, 0.12 * math.sin(index), offset * 1.5)),
                Vector((-2.45 - index * 0.1, 0.18 * math.cos(index), offset * 2.0)),
            ],
            material=materials["comet_tail"],
            bevel=0.035 + index * 0.004,
            parent=spin,
        )
    animate_rotation(spin, 0, 0.55)
    return root


def create_quantum_moon(materials) -> bpy.types.Object:
    root = make_root("QuantumMoon.Root")
    spin = attach(make_root("QuantumMoon.Spin"), root)
    add_ico(
        "QuantumMoon",
        radius=0.86,
        material=materials["quantum"],
        subdivisions=4,
        displacement=0.075,
        seed=21,
        parent=spin,
    )
    add_uv_sphere("QuantumMoon.Fog", radius=1.02, material=materials["quantum_fog"], parent=spin)
    for index in range(6):
        angle = index / 6 * TAU
        add_torus(
            f"QuantumMoon.Glyph.{index}",
            major_radius=0.11,
            minor_radius=0.012,
            material=materials["quantum_glyph"],
            location=(math.cos(angle) * 0.72, -0.55, math.sin(angle) * 0.45),
            rotation=(math.pi / 2, angle * 0.2, 0),
            parent=spin,
            major_segments=24,
            minor_segments=5,
        )
    animate_rotation(spin, 2, -0.28)
    return root


def create_white_hole(materials) -> bpy.types.Object:
    root = make_root("WhiteHole.Root")
    spin = attach(make_root("WhiteHole.Spin"), root)
    add_uv_sphere("WhiteHole", radius=0.56, material=materials["white_hot"], parent=spin)
    for index, rotation in enumerate(((0.4, 0.2, 0), (1.0, 0.5, 0.3), (0.3, 1.2, 0.5))):
        add_torus(
            f"WhiteHole.Lensing.{index}",
            major_radius=0.72 + index * 0.12,
            minor_radius=0.025,
            material=materials["white_hole_ring"],
            rotation=rotation,
            parent=spin,
        )
    station = attach(make_root("WhiteHoleStation"), spin)
    station.location = (1.35, 0, 0.12)
    add_torus(
        "WhiteHoleStation.Ring",
        major_radius=0.25,
        minor_radius=0.035,
        material=materials["nomai_gold"],
        rotation=(math.pi / 2, 0.4, 0),
        parent=station,
        major_segments=36,
        minor_segments=6,
    )
    add_box("WhiteHoleStation.Core", dimensions=(0.32, 0.1, 0.12), material=materials["nomai_blue"], parent=station)
    animate_rotation(spin, 2, 0.8)
    animate_rotation(station, 1, -1.3)
    return root


def create_stranger(materials) -> bpy.types.Object:
    root = make_root("Stranger.Root")
    spin = attach(make_root("Stranger.Spin"), root)
    ring_rotation = (math.pi / 2, 0.28, -0.18)
    add_torus(
        "Stranger.Hull",
        major_radius=1.02,
        minor_radius=0.25,
        material=materials["stranger_hull"],
        rotation=ring_rotation,
        parent=spin,
        major_segments=96,
        minor_segments=14,
    )
    add_torus(
        "Stranger.InnerWorld",
        major_radius=1.02,
        minor_radius=0.17,
        material=materials["stranger_inner"],
        rotation=ring_rotation,
        parent=spin,
        major_segments=96,
        minor_segments=10,
    )
    add_uv_sphere("Stranger.ArtificialSun", radius=0.13, material=materials["stranger_sun"], parent=spin)
    for index in range(4):
        angle = index / 4 * TAU
        add_box(
            f"Stranger.Sail.{index}",
            dimensions=(0.42, 0.035, 0.2),
            material=materials["stranger_sail"],
            location=(math.cos(angle) * 1.35, 0, math.sin(angle) * 1.35),
            rotation=(0, -angle, angle),
            parent=spin,
        )
    animate_rotation(spin, 1, 0.5)
    return root


def create_eye(materials) -> bpy.types.Object:
    root = make_root("Eye.Root")
    spin = attach(make_root("Eye.Spin"), root)
    add_ico(
        "EyeOfTheUniverse",
        radius=0.96,
        material=materials["eye"],
        subdivisions=4,
        displacement=0.11,
        seed=44,
        parent=spin,
    )
    for index in range(12):
        angle = index / 12 * TAU
        start = Vector((math.cos(angle) * 0.35, -0.87, math.sin(angle) * 0.35))
        middle = Vector((math.cos(angle + 0.45) * 0.75, -0.72, math.sin(angle + 0.45) * 0.72))
        end = Vector((math.cos(angle + 0.8) * 1.15, -0.18, math.sin(angle + 0.8) * 1.08))
        add_curve(
            f"Eye.Branch.{index}",
            [start, middle, end],
            material=materials["eye_branch"],
            bevel=0.018 + 0.005 * (index % 3),
            parent=spin,
        )
    add_uv_sphere("Eye.Fog", radius=1.12, material=materials["eye_fog"], parent=spin)
    animate_rotation(spin, 2, -0.2)
    return root


def create_satellite(materials) -> bpy.types.Object:
    root = make_root("DeepSpaceSatellite.Root")
    spin = attach(make_root("DeepSpaceSatellite.Spin"), root)
    add_box("Satellite.Core", dimensions=(0.42, 0.34, 0.42), material=materials["satellite"], parent=spin)
    for index in range(4):
        angle = index / 4 * TAU
        direction = Vector((math.cos(angle), 0, math.sin(angle)))
        add_box(
            f"Satellite.Arm.{index}",
            dimensions=(0.7, 0.07, 0.1),
            material=materials["satellite_arm"],
            location=direction * 0.48,
            rotation=(0, -angle, 0),
            parent=spin,
        )
        add_box(
            f"Satellite.Panel.{index}",
            dimensions=(0.34, 0.035, 0.48),
            material=materials["satellite_panel"],
            location=direction * 0.9,
            rotation=(0, -angle, 0),
            parent=spin,
        )
    add_torus(
        "Satellite.Signal",
        major_radius=0.7,
        minor_radius=0.018,
        material=materials["signal"],
        rotation=(math.pi / 2, 0, 0),
        parent=spin,
    )
    animate_rotation(spin, 1, 0.8)
    return root


def build_materials() -> dict[str, bpy.types.Material]:
    return {
        "sun": noise_material("Sun Plasma", [(0.0, "#a51e09"), (0.35, "#ef4710"), (0.68, "#ffad1f"), (1.0, "#ffe875")], scale=4.8, detail=6, roughness=0.38, bump=0.28, emission_strength=2.6),
        "sun_hot": basic_material("Sun Hot", "#ffbf3d", emission="#ffd65d", emission_strength=4.5),
        "sun_atmosphere": atmosphere_material("Sun Corona", "#ff6b18", 1.4, 0.24),
        "ash": noise_material("Ash Twin", [(0, "#6e3423"), (0.35, "#b76535"), (0.7, "#d99d5c"), (1, "#f0c98e")], scale=5.2, detail=5, bump=0.24),
        "ember": banded_material("Ember Twin", [(0, "#591e1d"), (0.3, "#9d3422"), (0.58, "#d56027"), (0.8, "#f19b45"), (1, "#7b211d")], bands=12),
        "ember_dark": basic_material("Ember Canyons", "#4b191b", roughness=0.9),
        "pink_atmosphere": atmosphere_material("Twin Atmosphere", "#ef8f91", 0.8, 0.22),
        "sand": basic_material("Sand Column", "#c66f22", emission="#e58b2f", emission_strength=0.22, alpha=0.7),
        "sand_hot": basic_material("Sand Grain", "#e9a04a", emission="#ef9b32", emission_strength=0.55),
        "timber": noise_material("Timber Hearth", [(0, "#183c42"), (0.28, "#245f65"), (0.5, "#396b47"), (0.72, "#718056"), (1, "#b0946c")], scale=3.1, detail=5, bump=0.2),
        "forest": basic_material("Timber Forest", "#173d32", roughness=0.92),
        "blue_atmosphere": atmosphere_material("Blue Atmosphere", "#62bdd2", 0.48, 0.18),
        "attlerock": noise_material("Attlerock", [(0, "#454c52"), (0.42, "#7c8589"), (0.74, "#aab2af"), (1, "#d6d5ca")], scale=6, detail=3, bump=0.3),
        "brittle_a": basic_material("Brittle Slate", "#31374f", roughness=0.86),
        "brittle_b": basic_material("Brittle Violet", "#55506b", roughness=0.82),
        "brittle_c": basic_material("Brittle Pale", "#777487", roughness=0.78),
        "brittle_inner": noise_material("Brittle Geode", [(0, "#251f37"), (0.48, "#5b285e"), (0.78, "#b54a8f"), (1, "#4fe0e4")], scale=9, detail=4, bump=0.15, emission_strength=0.35),
        "black_hole": basic_material("Black Hole", "#000004", roughness=0.1, emission="#07001a", emission_strength=0.2),
        "black_hole_ring": basic_material("Black Hole Lensing", "#5137ff", emission="#7ce9ff", emission_strength=7),
        "lava": noise_material("Lava", [(0, "#6b160d"), (0.35, "#e23712"), (0.7, "#ff8d16"), (1, "#fff06a")], scale=5, detail=4, bump=0.12, emission_strength=4.2),
        "volcanic": basic_material("Volcanic Crust", "#211a1b", roughness=0.95),
        "volcanic_brown": basic_material("Volcanic Brown", "#4a2922", roughness=0.94),
        "giant": banded_material("Giant's Deep", [(0, "#102f2b"), (0.28, "#1e5445"), (0.5, "#34745b"), (0.74, "#173e36"), (1, "#65a678")], bands=17, emission_strength=0.05),
        "cyan_atmosphere": atmosphere_material("Giant Atmosphere", "#48c9c1", 0.72, 0.22),
        "giant_cloud_a": basic_material("Giant Cloud Light", "#76ba82", emission="#5ec9a2", emission_strength=0.15, alpha=0.62),
        "giant_cloud_b": basic_material("Giant Cloud Dark", "#153d38", emission="#194e47", emission_strength=0.08, alpha=0.66),
        "storm": basic_material("Storm Lightning", "#d7fff2", emission="#8effed", emission_strength=5.5),
        "nomai_gold": basic_material("Nomai Gold", "#c79943", roughness=0.42, metallic=0.35, emission="#e8b95c", emission_strength=0.1),
        "nomai_blue": basic_material("Nomai Blue", "#69cdd5", roughness=0.38, metallic=0.18, emission="#62e8f1", emission_strength=1.3),
        "orbit": basic_material("Orbit Line", "#536478", emission="#5b7894", emission_strength=0.25, alpha=0.35),
        "bramble_fog": atmosphere_material("Bramble Fog", "#b7cbc6", 0.34, 0.14),
        "bramble_ice_a": noise_material("Bramble Ice", [(0, "#183242"), (0.5, "#427585"), (0.78, "#91c8cf"), (1, "#d9eff0")], scale=5, detail=3, bump=0.26),
        "bramble_ice_b": noise_material("Bramble Ice Shadow", [(0, "#0d222c"), (0.55, "#355665"), (1, "#9fbfc2")], scale=6, detail=4, bump=0.3),
        "bramble_vine": noise_material("Bramble Vine", [(0, "#24160f"), (0.48, "#4a2817"), (0.75, "#6f3b1e"), (1, "#2a180e")], scale=8, detail=3, bump=0.28),
        "bramble_vine_dark": basic_material("Bramble Vine Dark", "#24130e", roughness=0.95),
        "white_hot": basic_material("White Hot", "#eaffff", emission="#dfffff", emission_strength=10),
        "interloper": noise_material("Interloper Ice", [(0, "#123a52"), (0.38, "#2d7897"), (0.7, "#77bed0"), (1, "#d8f4f2")], scale=6, detail=5, bump=0.32),
        "interloper_fissure": basic_material("Interloper Fissure", "#251833", emission="#81386e", emission_strength=1.0),
        "comet_tail": basic_material("Comet Tail", "#75cfea", emission="#8edfff", emission_strength=2.1, alpha=0.35),
        "quantum": noise_material("Quantum Moon", [(0, "#282c34"), (0.35, "#545969"), (0.62, "#838a92"), (1, "#b2b8b5")], scale=5, detail=4, bump=0.24),
        "quantum_fog": atmosphere_material("Quantum Fog", "#e0e5df", 1.1, 0.27),
        "quantum_glyph": basic_material("Quantum Glyph", "#d8ffff", emission="#b9ffff", emission_strength=2.5),
        "white_hole_ring": basic_material("White Hole Ring", "#8ad9ff", emission="#bdeeff", emission_strength=5.0, alpha=0.72),
        "stranger_hull": noise_material("Stranger Hull", [(0, "#111b19"), (0.45, "#26342d"), (0.7, "#465248"), (1, "#161d1b")], scale=7, detail=3, bump=0.2, roughness=0.76),
        "stranger_inner": banded_material("Stranger Inner", [(0, "#3c4d28"), (0.38, "#64813d"), (0.62, "#9b8746"), (1, "#2e5338")], bands=13, emission_strength=0.08),
        "stranger_sun": basic_material("Artificial Sun", "#fff1a4", emission="#fff0a2", emission_strength=9),
        "stranger_sail": basic_material("Stranger Sail", "#667c55", roughness=0.6, metallic=0.2, emission="#6d8e57", emission_strength=0.12),
        "eye": noise_material("Eye Surface", [(0, "#030309"), (0.5, "#111527"), (0.76, "#252d4c"), (1, "#05050a")], scale=7, detail=6, bump=0.25, emission_strength=0.12),
        "eye_branch": basic_material("Eye Branch", "#6ebac8", emission="#86dfe8", emission_strength=2.2),
        "eye_fog": atmosphere_material("Eye Fog", "#5b83c9", 0.62, 0.14),
        "satellite": basic_material("Satellite Body", "#b08247", roughness=0.5, metallic=0.45),
        "satellite_arm": basic_material("Satellite Arm", "#caa36b", roughness=0.48, metallic=0.5),
        "satellite_panel": basic_material("Satellite Panel", "#203756", roughness=0.4, metallic=0.36, emission="#28558d", emission_strength=0.2),
        "signal": basic_material("Satellite Signal", "#7ecfd5", emission="#94f7f0", emission_strength=2.5, alpha=0.48),
        "label": basic_material("Labels", "#dce4e3", emission="#dce4e3", emission_strength=0.45),
    }


def create_camera(name: str) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(name)
    camera = bpy.data.objects.new(name, camera_data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    return camera


def look_at(obj: bpy.types.Object, target: Vector) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def create_label(text: str, location: Vector, camera: bpy.types.Object, material, size=0.34):
    bpy.ops.object.text_add(location=location)
    obj = bpy.context.object
    obj.name = f"Label.{text}"
    obj.data.body = text
    obj.data.align_x = "CENTER"
    obj.data.align_y = "CENTER"
    obj.data.size = size
    obj.data.extrude = 0.006
    obj.data.bevel_depth = 0.003
    obj.data.materials.append(material)
    obj.rotation_euler = (camera.location - obj.location).to_track_quat("Z", "Y").to_euler()
    return obj


def add_lights() -> None:
    lights = [
        ("Key", "AREA", (0, -10, 14), 1500, "#ffd6aa", 9.0),
        ("Blue Rim", "AREA", (-14, 2, 8), 1250, "#75baff", 8.0),
        ("Warm Fill", "AREA", (14, -2, 2), 1100, "#ffb26b", 7.0),
    ]
    for name, kind, location, energy, tint, size in lights:
        data = bpy.data.lights.new(name, kind)
        data.energy = energy
        data.color = color(tint)[:3]
        data.shape = "DISK"
        data.size = size
        obj = bpy.data.objects.new(name, data)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
        look_at(obj, Vector((0, 0, 0)))


def add_starfield(materials) -> bpy.types.Object:
    rng = random.Random(2049)
    vertices = []
    faces = []
    face_materials = []
    for index in range(190):
        theta = rng.uniform(0, TAU)
        phi = math.acos(rng.uniform(-1, 1))
        radius = rng.uniform(26, 34)
        center = Vector((
            radius * math.sin(phi) * math.cos(theta),
            radius * math.sin(phi) * math.sin(theta),
            radius * math.cos(phi),
        ))
        size = rng.uniform(0.015, 0.055) * (2.2 if index % 31 == 0 else 1)
        offset = len(vertices)
        vertices.extend([
            tuple(center + Vector((size, 0, 0))),
            tuple(center + Vector((-size * 0.55, size * 0.75, 0))),
            tuple(center + Vector((-size * 0.55, -size * 0.75, 0))),
            tuple(center + Vector((0, 0, size * 0.9))),
        ])
        faces.extend([
            (offset, offset + 1, offset + 2),
            (offset, offset + 3, offset + 1),
            (offset + 1, offset + 3, offset + 2),
            (offset + 2, offset + 3, offset),
        ])
        face_materials.extend([index % 3] * 4)
    mesh = bpy.data.meshes.new("Starfield")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("Starfield", mesh)
    bpy.context.scene.collection.objects.link(obj)
    for material in (materials["white_hot"], materials["sun_hot"], materials["nomai_blue"]):
        mesh.materials.append(material)
    for polygon, material_index in zip(mesh.polygons, face_materials):
        polygon.material_index = material_index
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
    scene.frame_end = FRAMES
    scene.render.fps = 30
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = color("#020408")
    background.inputs["Strength"].default_value = 0.025
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    scene.use_nodes = True
    tree = bpy.data.node_groups.new("EntropyCamp Compositor", "CompositorNodeTree")
    scene.compositing_node_group = tree
    layers = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 0.8
    glare.inputs["Strength"].default_value = 0.26
    glare.inputs["Size"].default_value = 0.56
    tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    composite = tree.nodes.new("NodeGroupOutput")
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], composite.inputs["Image"])


def render_catalog(roots, camera, materials):
    layout = {
        "dark_bramble": (-9, 0, 5.4),
        "brittle": (-3, 0, 5.4),
        "giant": (3, 0, 5.4),
        "eye": (9, 0, 5.4),
        "twins": (-9, 0, 0.4),
        "sun": (-3, 0, 0.4),
        "timber": (3, 0, 0.4),
        "stranger": (9, 0, 0.4),
        "interloper": (-9, 0, -5.0),
        "quantum": (-3, 0, -5.0),
        "white_hole": (3, 0, -5.0),
        "satellite": (9, 0, -5.0),
    }
    labels = {
        "dark_bramble": "DARK BRAMBLE",
        "brittle": "BRITTLE HOLLOW + HOLLOW'S LANTERN",
        "giant": "GIANT'S DEEP + PROBE CANNON",
        "eye": "EYE OF THE UNIVERSE",
        "twins": "THE HOURGLASS TWINS",
        "sun": "SUN + SUN STATION",
        "timber": "TIMBER HEARTH + ATTLEROCK",
        "stranger": "THE STRANGER",
        "interloper": "THE INTERLOPER",
        "quantum": "QUANTUM MOON",
        "white_hole": "WHITE HOLE + STATION",
        "satellite": "DEEP SPACE SATELLITE",
    }
    for key, root in roots.items():
        root.location = layout[key]
    camera.location = Vector((0, -42.0, 1.7))
    camera.data.lens = 54
    look_at(camera, Vector((0, 0, 0.45)))

    label_objects = []
    for key, text in labels.items():
        x, _, z = layout[key]
        size = 0.26 if len(text) > 24 else 0.32
        label_objects.append(create_label(text, Vector((x, -0.85, z - 1.85)), camera, materials["label"], size=size))
    title = create_label("ENTROPYCAMP / OUTER WILDS 3D STUDY", Vector((0, -0.6, 8.55)), camera, materials["sun_hot"], size=0.54)
    label_objects.append(title)

    scene = bpy.context.scene
    scene.render.filepath = str(OUTPUT_DIR / "outer_wilds_catalog.png")
    scene.frame_set(72)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / "outer_wilds_catalog.blend"))
    bpy.ops.render.render(write_still=True)
    return label_objects


def render_system(roots, camera, labels, materials):
    layout = {
        "sun": (0, 0, 0),
        "twins": (3.9, 1.0, 0.3),
        "timber": (-1.0, 5.0, 0.65),
        "brittle": (-5.7, 1.5, 1.1),
        "giant": (-4.2, -5.5, -0.3),
        "dark_bramble": (3.5, -7.0, 1.1),
        "interloper": (8.2, 4.0, 2.1),
        "quantum": (2.0, 7.7, 1.6),
        "stranger": (-8.7, -5.8, 3.0),
        "eye": (8.7, -7.2, 4.9),
        "white_hole": (9.3, 1.2, -2.8),
        "satellite": (-8.7, 5.8, 3.6),
    }
    for key, root in roots.items():
        root.location = layout[key]
    for label in labels:
        label.hide_render = True
        label.hide_viewport = True

    orbit_root = make_root("System.Orbits")
    for index, radius in enumerate((3.9, 5.2, 6.7, 8.2, 9.7)):
        ring = add_torus(
            f"System.Orbit.{index}",
            major_radius=radius,
            minor_radius=0.009,
            material=materials["orbit"],
            parent=orbit_root,
            major_segments=128,
            minor_segments=5,
        )
        ring.scale.y = 0.72
        ring.rotation_euler.x = 0.08 * (index - 2)

    camera.location = Vector((0, -32.0, 27.0))
    camera.data.lens = 50
    look_at(camera, Vector((0, 0.2, 0.65)))
    scene = bpy.context.scene
    scene.render.filepath = str(OUTPUT_DIR / "outer_wilds_system.png")
    scene.frame_set(116)
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_DIR / "outer_wilds_system.blend"))


def main() -> None:
    clear_scene()
    configure_scene()
    materials = build_materials()
    add_lights()
    add_starfield(materials)
    camera = create_camera("EntropyCamp Camera")
    roots = {
        "sun": create_sun(materials),
        "twins": create_twins(materials),
        "timber": create_timber(materials),
        "brittle": create_brittle(materials),
        "giant": create_giants_deep(materials),
        "dark_bramble": create_dark_bramble(materials),
        "interloper": create_interloper(materials),
        "quantum": create_quantum_moon(materials),
        "white_hole": create_white_hole(materials),
        "stranger": create_stranger(materials),
        "eye": create_eye(materials),
        "satellite": create_satellite(materials),
    }
    labels = render_catalog(roots, camera, materials)
    render_system(roots, camera, labels, materials)
    print(f"Saved Blender studies to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
