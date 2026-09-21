#!/usr/bin/env python3
"""Restore extracted Sun/DLC geometry and textures in an inspectable Blender scene."""

from __future__ import annotations

import json
import math
from pathlib import Path
import zipfile

import bpy
from mathutils import Matrix, Quaternion, Vector
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "private" / "outer-wilds-extracted" / "sun-and-dlc"
DATA = ROOT / "scene-data"
OUTPUT = ROOT / "blender"
OUTPUT.mkdir(parents=True, exist_ok=True)
UNITY_TO_BLENDER = Matrix(((-1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
BASIS = np.array([[-1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float32)


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def new_shader(name):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.inputs["Roughness"].default_value = 0.68
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material, shader


class Builder:
    def __init__(self):
        self.manifest = json.loads((DATA / "manifest.json").read_text())
        if self.manifest["errors"]:
            raise ValueError("Source extraction has unresolved errors")
        self.materials = {}
        self.images = {}
        self.normal_images = {}
        self.meshes = {}
        self.groups = {}

    def image(self, path, *, data=False):
        key = (path, data)
        if key not in self.images:
            image = bpy.data.images.load(str(DATA / path), check_existing=False)
            if data:
                image.colorspace_settings.name = "Non-Color"
            self.images[key] = image
        return self.images[key]

    def texture_node(self, material, prop, *, data=False):
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = self.image(prop["path"], data=data)
        texture.extension = "REPEAT"
        uv = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (*prop["scale"], 1)
        mapping.inputs["Location"].default_value = (*prop["offset"], 0)
        links.new(uv.outputs["UV"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
        return texture

    def decoded_normal(self, path):
        if path in self.normal_images:
            return self.normal_images[path]
        original = self.image(path, data=True)
        pixels = np.empty(len(original.pixels), dtype=np.float32)
        original.pixels.foreach_get(pixels)
        pixels = pixels.reshape(-1, 4)
        # Unity DXT5nm stores X in alpha and Y in green; the red channel is 1.
        if pixels[:, 0].mean() > 0.95 and pixels[:, 0].std() < 0.01:
            x = pixels[:, 3] * 2 - 1
            y = pixels[:, 1] * 2 - 1
            z = np.sqrt(np.maximum(0, 1 - x * x - y * y))
            result = pixels.copy()
            result[:, 0] = x * 0.5 + 0.5
            result[:, 1] = y * 0.5 + 0.5
            result[:, 2] = z * 0.5 + 0.5
            result[:, 3] = 1
            image = bpy.data.images.new(f"Decoded DXT5nm - {original.name}", width=original.size[0], height=original.size[1], alpha=True)
            image.colorspace_settings.name = "Non-Color"
            image.pixels.foreach_set(result.reshape(-1))
            image["original_source"] = path
            image.pack()
        else:
            image = original
        self.normal_images[path] = image
        return image

    def material(self, key):
        if key in self.materials:
            return self.materials[key]
        source = self.manifest["materials"][key]
        material, shader = new_shader(source["name"])
        material["source_material"] = key
        material["shader_reconstruction"] = "Blender node approximation from extracted properties"
        self.materials[key] = material
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        colors = source["colors"]
        floats = source["floats"]
        textures = source["textures"]
        tint = colors.get("_Color", [1, 1, 1, 1])
        shader.inputs["Base Color"].default_value = tint
        shader.inputs["Roughness"].default_value = max(0.28, 1 - floats.get("_Glossiness", 0.3))
        if source["name"].startswith("Terrain_"):
            shader.inputs["Roughness"].default_value = max(0.7, shader.inputs["Roughness"].default_value)
        shader.inputs["Metallic"].default_value = min(0.5, floats.get("_Metallic", 0))

        if "Stencil" in source["name"]:
            nodes.clear()
            transparent = nodes.new("ShaderNodeBsdfTransparent")
            output = nodes.new("ShaderNodeOutputMaterial")
            links.new(transparent.outputs[0], output.inputs["Surface"])
            return material

        diffuse = textures.get("_MainTex")
        color_socket = None
        alpha_socket = None
        if diffuse:
            texture = self.texture_node(material, diffuse)
            color_socket = texture.outputs["Color"]
            alpha_socket = texture.outputs["Alpha"]
        if color_socket and any(abs(tint[i] - 1) > 0.005 for i in range(3)):
            multiply = nodes.new("ShaderNodeMixRGB")
            multiply.blend_type = "MULTIPLY"
            multiply.inputs[0].default_value = 1
            multiply.inputs[2].default_value = tint
            links.new(color_socket, multiply.inputs[1])
            color_socket = multiply.outputs[0]
        if floats.get("_VertexColorAlbedo", 0) > 0:
            attribute = nodes.new("ShaderNodeVertexColor")
            attribute.layer_name = "SourceColor"
            if color_socket:
                multiply = nodes.new("ShaderNodeMixRGB")
                multiply.blend_type = "MULTIPLY"
                multiply.inputs[0].default_value = 1
                links.new(color_socket, multiply.inputs[1])
                links.new(attribute.outputs["Color"], multiply.inputs[2])
                color_socket = multiply.outputs[0]
            else:
                color_socket = attribute.outputs["Color"]
        if color_socket:
            links.new(color_socket, shader.inputs["Base Color"])

        overlay = textures.get("_TopOverlayAlbedoTex") or textures.get("_Overlay1Tex")
        if overlay and color_socket:
            texture = self.texture_node(material, overlay)
            attribute = nodes.new("ShaderNodeAttribute")
            attribute.attribute_name = "SourceSurfaceMask"
            blend = nodes.new("ShaderNodeMixRGB")
            links.new(attribute.outputs["Fac"], blend.inputs[0])
            links.new(color_socket, blend.inputs[1])
            links.new(texture.outputs["Color"], blend.inputs[2])
            color_socket = blend.outputs[0]
            links.new(color_socket, shader.inputs["Base Color"])

        bump = textures.get("_BumpMap")
        if bump:
            texture = self.texture_node(material, bump, data=True)
            texture.image = self.decoded_normal(bump["path"])
            normal = nodes.new("ShaderNodeNormalMap")
            normal.inputs["Strength"].default_value = min(0.5, floats.get("_BumpScale", 1))
            links.new(texture.outputs["Color"], normal.inputs["Color"])
            links.new(normal.outputs["Normal"], shader.inputs["Normal"])

        emission_color = colors.get("_EmissionColor", [0, 0, 0, 1])
        emission_texture = textures.get("_EmissionMap")
        emission_enabled = "_EMISSION" in (source.get("keywords") or "").split()
        if emission_enabled and emission_texture and max(emission_color[:3]) > 0:
            texture = self.texture_node(material, emission_texture)
            links.new(texture.outputs["Color"], shader.inputs["Emission Color"])
            shader.inputs["Emission Strength"].default_value = min(3, max(emission_color[:3]))
        elif emission_enabled and max(emission_color[:3]) > 0:
            shader.inputs["Emission Color"].default_value = emission_color
            shader.inputs["Emission Strength"].default_value = 0.5
        name = source["name"].lower()
        if "water" in name and "floor" not in name:
            shader.inputs["Base Color"].default_value = (0.02, 0.16, 0.12, 1)
            shader.inputs["Roughness"].default_value = 0.22
            shader.inputs["Metallic"].default_value = 0.12
        if "fakesun" in name or "sunbulb" in name:
            shader.inputs["Emission Color"].default_value = (1, 0.82, 0.35, 1)
            shader.inputs["Emission Strength"].default_value = 4
        if "visibleplanet" in name and "rings" not in name:
            ramp = textures.get("_RampTex")
            if ramp and color_socket:
                material["cloud_ramp_source"] = ramp["path"]
                image = self.image(ramp["path"])
                pixel = (image.size[0] // 2) * 4
                ramp_tint = tuple(image.pixels[pixel:pixel + 4])
                multiply = nodes.new("ShaderNodeMixRGB")
                multiply.blend_type = "MULTIPLY"
                multiply.inputs[0].default_value = 1
                multiply.inputs[2].default_value = ramp_tint
                links.new(color_socket, multiply.inputs[1])
                links.new(multiply.outputs[0], shader.inputs["Base Color"])
        if "rings" in name:
            shader.inputs["Base Color"].default_value = (0.46, 0.7, 0.72, 1)
            if alpha_socket:
                links.new(alpha_socket, shader.inputs["Alpha"])
                material.surface_render_method = "BLENDED"
        return material

    def mesh(self, key, material_keys):
        cache_key = (key, tuple(material_keys))
        if cache_key in self.meshes:
            return self.meshes[cache_key]
        source = self.manifest["meshes"][key]
        with zipfile.ZipFile(DATA / source["path"]) as archive:
            positions = np.frombuffer(archive.read("positions.bin"), dtype="<f4").reshape(-1, 3) @ BASIS.T
            faces = np.frombuffer(archive.read("triangles.bin"), dtype="<u4").reshape(-1, 3)[:, ::-1]
            indices = np.frombuffer(archive.read("material_indices.bin"), dtype="<u4")
            mesh = bpy.data.meshes.new(source["name"])
            mesh.from_pydata(positions.tolist(), [], faces.tolist())
            mesh.update()
            for material_key in material_keys:
                mesh.materials.append(self.material(material_key) if material_key else None)
            if len(material_keys):
                mesh.polygons.foreach_set("material_index", np.minimum(indices, len(material_keys) - 1).astype(np.int32))
            mesh.polygons.foreach_set("use_smooth", np.ones(len(faces), dtype=np.bool_))
            vertex_indices = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get("vertex_index", vertex_indices)
            for file, name in (("uv0.bin", "UVMap"), ("uv1.bin", "UVMap1")):
                if file in archive.namelist():
                    uvs = np.frombuffer(archive.read(file), dtype="<f4").reshape(len(positions), -1)[:, :2]
                    layer = mesh.uv_layers.new(name=name)
                    layer.data.foreach_set("uv", uvs[vertex_indices].reshape(-1))
            if "colors.bin" in archive.namelist():
                colors = np.frombuffer(archive.read("colors.bin"), dtype="<f4").reshape(len(positions), -1)
                if colors.shape[1] == 4:
                    attribute = mesh.color_attributes.new(name="SourceColor", type="FLOAT_COLOR", domain="POINT")
                    attribute.data.foreach_set("color", colors.reshape(-1))
            if "normals.bin" in archive.namelist():
                normals = np.frombuffer(archive.read("normals.bin"), dtype="<f4").reshape(len(positions), -1)[:, :3] @ BASIS.T
                mesh.normals_split_custom_set_from_vertices(normals.tolist())
        self.meshes[cache_key] = mesh
        return mesh

    def group(self, key):
        source = self.manifest["groups"][key]
        collection = bpy.data.collections.new(key)
        bpy.context.scene.collection.children.link(collection)
        wrapper = bpy.data.objects.new(f"VIEW::{key}", None)
        collection.objects.link(wrapper)
        objects = {}
        for node in source["nodes"]:
            mesh = self.mesh(node["mesh"], node["materials"]) if node.get("mesh") else None
            obj = bpy.data.objects.new(node["name"], mesh)
            obj["source_game_object"] = node["id"]
            collection.objects.link(obj)
            objects[node["id"]] = obj
        by_id = {entry["id"]: entry for entry in source["nodes"]}
        for node in source["nodes"]:
            obj = objects[node["id"]]
            obj.parent = objects.get(node["parent"]) or wrapper
            q = node["rotation"]
            transform = Matrix.LocRotScale(Vector(node["position"]), Quaternion((q[3], q[0], q[1], q[2])), Vector(node["scale"]))
            obj.matrix_basis = UNITY_TO_BLENDER @ transform @ UNITY_TO_BLENDER.inverted()
            ancestor = node
            broken_state = False
            while ancestor:
                if not ancestor.get("source_active", True) and any(
                    token in ancestor["name"] for token in ("Broken", "Destroyed", "Detached")
                ):
                    broken_state = True
                ancestor = by_id.get(ancestor.get("parent"))
            placeholder = key in {"stranger_interior", "dreamworld"} and any(
                token in node["name"].lower() for token in ("screen", "water", "floorbed", "shadowcaster", "stencil")
            )
            if broken_state or placeholder:
                obj.hide_render = True
                obj.hide_viewport = True
                obj["inspection_hidden_reason"] = "inactive destruction state or shader-only inspection occluder"
        bpy.context.view_layer.update()
        if key == "stranger_interior":
            self.surface_masks(objects.values())
        self.groups[key] = (wrapper, collection, list(objects.values()))
        return wrapper

    def surface_masks(self, objects):
        for obj in objects:
            if obj.type != "MESH" or not obj.data.vertices:
                continue
            mesh = obj.data
            if mesh.attributes.get("SourceSurfaceMask"):
                continue
            vertices = np.empty((len(mesh.vertices), 3), dtype=np.float32)
            normals = np.empty_like(vertices)
            mesh.vertices.foreach_get("co", vertices.reshape(-1))
            mesh.vertices.foreach_get("normal", normals.reshape(-1))
            matrix = np.array(obj.matrix_world, dtype=np.float32)
            positions = vertices @ matrix[:3, :3].T + matrix[:3, 3]
            normals = normals @ matrix[:3, :3].T
            inward = -positions.copy()
            inward[:, 2] = 0
            inward /= np.maximum(np.linalg.norm(inward, axis=1, keepdims=True), 0.0001)
            normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 0.0001)
            weight = np.clip((np.einsum("ij,ij->i", inward, normals) - 0.3) / 0.35, 0, 1)
            attribute = mesh.attributes.new(name="SourceSurfaceMask", type="FLOAT", domain="POINT")
            attribute.data.foreach_set("value", weight.astype(np.float32))

    def sun(self):
        source_fbx = ROOT / "assetstudio" / "SunProxy" / "FBX_GameObjects" / "SunProxy" / "SunProxy.fbx"
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(source_fbx))
        objects = [obj for obj in bpy.data.objects if obj not in before]
        original_collection = bpy.data.collections.new("sun_original_shader_proxy (hidden)")
        bpy.context.scene.collection.children.link(original_collection)
        for obj in objects:
            for current in list(obj.users_collection):
                current.objects.unlink(obj)
            original_collection.objects.link(obj)
            obj.hide_render = True
            obj.hide_viewport = True
        original_collection.hide_render = True
        original_collection.hide_viewport = True
        collection = bpy.data.collections.new("sun")
        bpy.context.scene.collection.children.link(collection)
        wrapper = bpy.data.objects.new("VIEW::sun", None)
        collection.objects.link(wrapper)
        sphere = bpy.data.objects.new("Sun - sphere reconstruction for runtime surface", self.mesh(self.manifest["sun_sphere_mesh"], []))
        sphere.parent = wrapper
        sphere["geometry_note"] = self.manifest["sun_geometry_note"]
        collection.objects.link(sphere)
        source = self.manifest["materials"][self.manifest["sun_materials"][0]]
        material, shader = new_shader("Sun Surface - extracted heightmaps, Blender reconstruction")
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        coords = nodes.new("ShaderNodeTexCoord")
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = self.image(source["textures"]["_HeightmapMain"]["path"], data=True)
        texture.projection = "BOX"
        texture.projection_blend = 0.3
        mapping = nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (4, 4, 4)
        links.new(coords.outputs["Generated"], mapping.inputs["Vector"])
        links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
        movement = source["colors"]["_WaveMovementMain"]
        for axis in (0, 1):
            driver = mapping.inputs["Location"].driver_add("default_value", axis).driver
            driver.expression = f"(frame - 1) / 30 * {movement[axis]:.8f}"
        ramp_texture = nodes.new("ShaderNodeTexImage")
        ramp_texture.image = self.image(source["textures"]["_ColorRamp"]["path"])
        ramp_texture.extension = "EXTEND"
        combine = nodes.new("ShaderNodeCombineXYZ")
        links.new(texture.outputs["Color"], combine.inputs["X"])
        combine.inputs["Y"].default_value = 0.01
        links.new(combine.outputs[0], ramp_texture.inputs["Vector"])
        multiply = nodes.new("ShaderNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs[0].default_value = 1
        multiply.inputs[2].default_value = source["colors"]["_Color"]
        links.new(ramp_texture.outputs["Color"], multiply.inputs[1])
        links.new(multiply.outputs[0], shader.inputs["Base Color"])
        links.new(multiply.outputs[0], shader.inputs["Emission Color"])
        emission = nodes.new("ShaderNodeEmission")
        links.new(multiply.outputs[0], emission.inputs["Color"])
        emission.inputs["Strength"].default_value = 2.0
        output = next(node for node in nodes if node.type == "OUTPUT_MATERIAL")
        links.new(emission.outputs[0], output.inputs["Surface"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        links.new(texture.outputs["Color"], bump.inputs["Height"])
        links.new(bump.outputs[0], shader.inputs["Normal"])
        material["source_material"] = source["name"]
        material["shader_reconstruction"] = True
        sphere.data.materials.append(material)
        self.groups["sun"] = (wrapper, collection, [sphere])
        return wrapper

    def detail_views(self, layout, overview_camera):
        scene = bpy.context.scene
        labels = [obj for obj in bpy.data.objects if obj.type == "FONT"]
        for obj in labels:
            obj.hide_render = True
        try:
            for key, (target, _) in layout.items():
                for other_key, (_, collection, _) in self.groups.items():
                    collection.hide_render = other_key != key
                view = camera(f"Detail - {key}", Vector(target) + Vector((0, -14, 1.5)), target, ortho=7.8)
                scene.camera = view
                scene.render.filepath = str(OUTPUT / f"{key}_detail.png")
                bpy.ops.render.render(write_still=True)
        finally:
            for _, collection, _ in self.groups.values():
                collection.hide_render = False
            for obj in labels:
                obj.hide_render = False
            scene.camera = overview_camera


def bounds(objects):
    points = [obj.matrix_world @ Vector(corner) for obj in objects if obj.type == "MESH" and not obj.hide_render for corner in obj.bound_box]
    minimum = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    maximum = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    return minimum, maximum


def normalize_group(builder, key, target, diameter=4.6):
    wrapper, _, objects = builder.groups[key]
    low, high = bounds(objects)
    center = (low + high) * 0.5
    size = max(high - low)
    scale = diameter / max(size, 0.001)
    wrapper.scale = (scale,) * 3
    wrapper.location = Vector(target) - center * scale
    return size


def camera(name, location, target, ortho=None):
    data = bpy.data.cameras.new(name)
    if ortho:
        data.type = "ORTHO"
        data.ortho_scale = ortho
    else:
        data.lens = 48
    data.clip_end = 1000
    obj = bpy.data.objects.new(name, data)
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, target)
    return obj


def label(text, position, size=0.28):
    curve = bpy.data.curves.new(text, "FONT")
    curve.body = text
    curve.align_x = "CENTER"
    curve.size = size
    obj = bpy.data.objects.new(f"Label::{text}", curve)
    obj.location = position
    obj.rotation_euler = (math.pi / 2, 0, 0)
    material, shader = new_shader(f"Label::{text}")
    shader.inputs["Base Color"].default_value = (0.84, 0.9, 0.87, 1)
    shader.inputs["Emission Color"].default_value = (0.84, 0.9, 0.87, 1)
    shader.inputs["Emission Strength"].default_value = 0.6
    curve.materials.append(material)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def setup_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1280
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.035, 0.045, 0.052, 1)
    background.inputs["Strength"].default_value = 0.5
    scene.view_settings.look = "AgX - Medium High Contrast"
    for name, location, energy, tint in (
        ("Key", (-8, -12, 14), 4.5, (1, 0.88, 0.68)),
        ("Fill", (7, -9, -7), 2.8, (0.62, 0.8, 1)),
    ):
        data = bpy.data.lights.new(name, "SUN")
        data.energy = energy
        data.angle = 0.15
        data.color = tint
        obj = bpy.data.objects.new(name, data)
        obj.location = location
        bpy.context.scene.collection.objects.link(obj)
        look_at(obj, (0, 0, 0))


def configure_viewports(active_camera):
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.shading.type = "MATERIAL"
            space.shading.use_scene_world = False
            space.shading.studiolight_rotate_z = 0.3
            space.region_3d.view_perspective = "CAMERA"
            space.region_3d.view_camera_zoom = 0
            space.clip_end = 1000
            space.overlay.show_overlays = False


def main():
    setup_scene()
    builder = Builder()
    for key in builder.manifest["groups"]:
        builder.group(key)
    builder.sun()
    rotations = {
        "stranger_exterior": (math.radians(70), 0, 0),
        "stranger_interior": (math.radians(70), 0, 0),
        "dreamworld": (math.radians(60), 0, 0),
        "visible_homeworld": (math.radians(30), 0, 0),
    }
    outer_wrapper, _, outer_objects = builder.groups["stranger_exterior"]
    body = next(obj for obj in outer_objects if obj.name == "RingWorld_Body")
    body_inverse = body.matrix_world.to_quaternion().inverted().to_matrix().to_4x4()
    outer_wrapper.rotation_euler = (Matrix.Rotation(math.radians(70), 4, "X") @ body_inverse).to_euler()
    for key, rotation in rotations.items():
        if key != "stranger_exterior":
            builder.groups[key][0].rotation_euler = rotation
    bpy.context.view_layer.update()

    layout = {
        "sun": ((-7, 0, 4.2), "SUN / ORIGINAL TEXTURES, RESTORED SHADER"),
        "stranger_exterior": ((0, 0, 4.2), "THE STRANGER / EXTERIOR + SAILS"),
        "visible_homeworld": ((7, 0, 4.2), "DREAMWORLD SKY / RINGED PLANET"),
        "sun_station": ((-7, 0, -3.6), "SUN STATION / DISTANT PROXY"),
        "stranger_interior": ((0, 0, -3.6), "THE STRANGER / INTERIOR TERRAIN"),
        "dreamworld": ((7, 0, -3.6), "DREAMWORLD / TERRAIN + LANDMARKS"),
    }
    for key, (target, text) in layout.items():
        size = normalize_group(builder, key, target)
        print(key, "source diameter", round(size, 2), flush=True)
        label(text, (target[0], -2.8, target[2] - 3.25), size=0.23)
    label("OUTER WILDS / SUN + ECHOES OF THE EYE", (0, -2.8, 9), 0.48)
    view = camera("Sun + DLC Catalog", (0, -38, 0), (0, 0, 0), ortho=30)
    bpy.context.scene.camera = view
    configure_viewports(view)
    bpy.context.view_layer.update()

    readme = bpy.data.texts.new("README - actual extracted sources")
    readme.write(
        "Official geometry/UVs/submesh materials/vertex colors were statically extracted from the local game copy.\n"
        "SunProxy is a shader-deformed proxy, preserved in a hidden Collection. The visible Sun uses an extracted game sphere in place of runtime tessellation, with the original heightmap/color ramp. It is not the original Unity shader.\n"
        "DLC terrain is high-detail streamed geometry; landmarks are selected original distant proxies. Full props, characters and gameplay effects are not included.\n"
        "Textures are restored using the game's StreamingMaterialTable and StreamingTextureLookup, not filename guesses.\n"
        "Display positions/scales, lighting, cameras and Blender shader conversions are presentation additions.\n"
        "The source geometry retains separate rotating RingWorld and stationary StaticRing hierarchies.\n"
        "Material Preview is the saved default. Numpad 0 shows the catalog; F12 renders it.\n"
        "Private local study only. All extracted files must remain excluded from source control.\n"
    )
    bpy.context.scene.render.filepath = str(OUTPUT / "outer_wilds_sun_dlc_catalog.png")
    bpy.ops.render.render(write_still=True)
    builder.detail_views(layout, view)
    bpy.context.scene.render.filepath = str(OUTPUT / "outer_wilds_sun_dlc_catalog.png")
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "outer_wilds_sun_dlc.blend"))
    print({"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes), "materials": len(bpy.data.materials), "packed_images": sum(bool(i.packed_file) for i in bpy.data.images)}, flush=True)


if __name__ == "__main__":
    main()
