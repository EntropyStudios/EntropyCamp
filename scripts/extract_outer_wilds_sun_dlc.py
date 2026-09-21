#!/usr/bin/env python3
"""Statically extract selected Outer Wilds scene trees for local Blender study."""

from __future__ import annotations

import argparse
from array import array
import json
from pathlib import Path
import re
import sys
import zipfile

import UnityPy
from UnityPy.classes import PPtr
from UnityPy.helpers.MeshHelper import MeshHandler
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "stranger_exterior": {
        "reference": (64773, "SolarSystemRoot"),
        "roots": [77690, 34994],
        "description": "Station exterior geometry and independent static solar-sail frame",
    },
    "stranger_interior": {
        "reference": (22932, "RingWorld_Body"),
        "roots": [63815, 14258, 22214, 71839, 58691, 5873, 35019],
        "proxies": True,
        "proxy_root": 84814,
        "description": "Ringworld terrain, intact dam, artificial sun and landmark proxies",
    },
    "dreamworld": {
        "reference": (7522, "DreamWorld_Body"),
        "roots": [62749, 31051, 52804, 58588],
        "proxies": True,
        "description": "Four dreamworld terrain regions and landmark proxies; no full props/characters",
    },
    "visible_homeworld": {
        "reference": (32215, "VisiblePlanet_Pivot"),
        "roots": [32215],
        "description": "Ringed planet visible in the DLC dreamworld sky",
    },
    "sun_station": {
        "reference": (28127, "SunStation_Body"),
        "roots": [76448],
        "description": "Official Sun Station distant proxy",
    },
}


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "asset"


def v3(value):
    return [float(value.x), float(value.y), float(value.z)]


def rgba(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


class Extractor:
    def __init__(self, data: Path, output: Path, level_name: str = "level1"):
        self.data = data
        self.level_name = level_name
        self.output = output
        self.output.mkdir(parents=True, exist_ok=True)
        self.generator = TypeTreeGenerator("2019.4.39f1")
        # The generator reads assembly metadata; it does not execute game code.
        self.generator.load_local_dll_folder(str(data / "Managed"))
        self.environment = UnityPy.load(str(data / level_name))
        self.environment.typetree_generator = self.generator
        self.level = next(f for f in self.environment.assets if Path(f.name).name == level_name)
        self.streaming_table = {
            row["assetBundleName"]: row
            for row in json.loads((data / "StreamingAssets" / "StreamingAssetsTable.json").read_text())["assetBundles"]
        }
        self.meshes = {}
        self.materials = {}
        self.textures = {}
        self.nodes = {}
        self.bundles = {}
        self.texture_overrides = {}
        self.errors = []
        if level_name == "level1":
            self.scan_material_tables()

    @staticmethod
    def key(reader) -> str:
        return f"{safe_name(Path(reader.assets_file.name).name)}_{reader.path_id}"

    @staticmethod
    def resolve(pointer: dict, assets_file):
        return PPtr(
            m_FileID=pointer["m_FileID"],
            m_PathID=pointer["m_PathID"],
            assetsfile=assets_file,
        ).deref()

    def bundle(self, name: str):
        if name not in self.bundles:
            environment = UnityPy.load(str(self.data / "StreamingAssets" / name))
            self.bundles[name] = environment
        return self.bundles[name]

    def scan_material_tables(self):
        shared = self.resolve({"m_FileID": 2, "m_PathID": 1503}, self.level).assets_file
        for reader in shared.objects.values():
            if reader.type.name != "MonoBehaviour":
                continue
            name = reader.peek_name() or ""
            if not name.startswith("StreamingMaterialTable_"):
                continue
            table = reader.parse_as_dict()
            bundle_name = table.get("assetBundle") or ""
            if not bundle_name.startswith(("ringworld/", "dreamworld/")):
                continue
            for row in table.get("_materialPropertyLookups") or []:
                material_reader = self.resolve(row["material"], reader.assets_file)
                for prop in row.get("propertyLookups") or []:
                    self.texture_overrides[(self.key(material_reader), prop["propertyName"])] = (
                        bundle_name, prop["textureIndex"]
                    )

    def streamed_texture(self, bundle_name: str, texture_index: int):
        env = self.bundle(bundle_name)
        lookup = next(
            obj.parse_as_object()
            for obj in env.objects
            if obj.type.name == "MonoBehaviour" and obj.peek_name() == "StreamingTextureLookup"
        )
        return lookup.textures[texture_index].deref()

    def export_texture(self, reader) -> str:
        key = self.key(reader)
        if key in self.textures:
            return self.textures[key]["path"]
        texture = reader.parse_as_object()
        relative = Path("textures") / f"{safe_name(texture.m_Name)}_{key}.png"
        destination = self.output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        texture.image.save(destination)
        self.textures[key] = {
            "name": texture.m_Name,
            "path": relative.as_posix(),
            "width": texture.m_Width,
            "height": texture.m_Height,
            "format": int(texture.m_TextureFormat),
        }
        return relative.as_posix()

    def export_material(self, reader) -> str:
        key = self.key(reader)
        if key in self.materials:
            return key
        material = reader.parse_as_object()
        properties = material.m_SavedProperties
        value = {
            "name": material.m_Name,
            "keywords": material.m_ShaderKeywords,
            "colors": {name: rgba(color) for name, color in properties.m_Colors},
            "floats": dict(properties.m_Floats),
            "textures": {},
        }
        self.materials[key] = value
        for name, env in properties.m_TexEnvs:
            override = self.texture_overrides.get((key, name))
            if not env.m_Texture and not override:
                continue
            try:
                texture_reader = (
                    self.streamed_texture(*override)
                    if override
                    else env.m_Texture.deref()
                )
                if texture_reader.type.name != "Texture2D":
                    continue
                texture = texture_reader.parse_as_object()
                value["textures"][name] = {
                    "path": self.export_texture(texture_reader),
                    "name": texture.m_Name,
                    "scale": [env.m_Scale.x, env.m_Scale.y],
                    "offset": [env.m_Offset.x, env.m_Offset.y],
                    "streamed": bool(override),
                }
            except Exception as error:
                self.errors.append({"material": material.m_Name, "property": name, "error": str(error)})
        return key

    def export_mesh(self, reader) -> str:
        key = self.key(reader)
        if key in self.meshes:
            return key
        mesh = reader.parse_as_object()
        handler = MeshHandler(mesh)
        handler.process()
        submeshes = handler.get_triangles()
        triangles = [face for submesh in submeshes for face in submesh]
        material_indices = [index for index, submesh in enumerate(submeshes) for _ in submesh]
        relative = Path("geometry") / f"{safe_name(mesh.m_Name)}_{key}.owmesh"
        destination = self.output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        def binary(rows, typecode="f"):
            values = array(typecode, (number for row in rows for number in row))
            if sys.byteorder != "little":
                values.byteswap()
            return values.tobytes()

        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("positions.bin", binary(handler.m_Vertices))
            archive.writestr("triangles.bin", binary(triangles, "I"))
            archive.writestr("material_indices.bin", binary(([i] for i in material_indices), "I"))
            for name, rows in (
                ("uv0.bin", handler.m_UV0),
                ("uv1.bin", handler.m_UV1),
                ("colors.bin", handler.m_Colors),
                ("normals.bin", handler.m_Normals),
            ):
                if rows:
                    archive.writestr(name, binary(rows))
        self.meshes[key] = {
            "name": mesh.m_Name,
            "path": relative.as_posix(),
            "vertices": len(handler.m_Vertices),
            "triangles": len(triangles),
            "colors": bool(handler.m_Colors),
        }
        return key

    def node(self, game_object_id: int):
        if game_object_id in self.nodes:
            return self.nodes[game_object_id]
        reader = self.level.objects[game_object_id]
        game_object = reader.parse_as_object()
        components = [entry.component.deref() for entry in game_object.m_Component]
        transform = next(c.parse_as_object() for c in components if c.type.name == "Transform")
        value = {
            "reader": reader,
            "game_object": game_object,
            "components": components,
            "transform": transform,
            "children": [c.deref().parse_as_object().m_GameObject.m_PathID for c in transform.m_Children],
            "name": game_object.m_Name,
        }
        self.nodes[game_object_id] = value
        return value

    def descendants(self, root_id):
        result = []
        stack = [root_id]
        while stack:
            pid = stack.pop()
            result.append(pid)
            stack.extend(reversed(self.node(pid)["children"]))
        return result

    def mesh_for_node(self, node):
        mesh_reader = None
        for component in node["components"]:
            if component.type.name == "MonoBehaviour":
                head = component.parse_monobehaviour_head()
                script = head.m_Script.deref().parse_as_object()
                if script.m_ClassName != "StreamingRenderMeshHandle":
                    continue
                handle = component.parse_as_dict()
                bundle_name = handle["assetBundle"]
                index = handle["meshIndex"]
                path = self.streaming_table[bundle_name]["meshNamesByID"][index].lower()
                bundle = self.bundle(bundle_name)
                candidates = {key.lower(): reader for key, reader in bundle.container.items()}
                mesh_reader = candidates[path].deref()
                break
        if mesh_reader is None:
            component = next((c for c in node["components"] if c.type.name == "MeshFilter"), None)
            if component:
                mesh_ptr = component.parse_as_object().m_Mesh
                if mesh_ptr:
                    mesh_reader = mesh_ptr.deref()
        return mesh_reader

    def export_group(self, spec):
        reference_id, expected_name = spec["reference"]
        reference = self.node(reference_id)
        if reference["name"] != expected_name:
            raise ValueError(f"Unsupported game scene: expected {expected_name}")
        selected = set()
        for root in spec["roots"]:
            selected.update(self.descendants(root))
        if spec.get("proxies"):
            for pid in self.descendants(spec.get("proxy_root", reference_id)):
                name = self.node(pid)["name"]
                if name.startswith(("Proxy_IP_", "Proxy_DW_")) and not any(
                    word in name for word in ("Broken", "Destroyed", "Destructible", "Detached", "Artifact", "Shaft")
                ):
                    selected.add(pid)

        records = {}
        mesh_nodes = 0
        for pid in sorted(selected):
            node = self.node(pid)
            renderer = next((c for c in node["components"] if c.type.name == "MeshRenderer"), None)
            if renderer is None:
                continue
            game_object = node["game_object"]
            mesh_reader = self.mesh_for_node(node)
            if mesh_reader is None:
                continue
            try:
                mesh_key = self.export_mesh(mesh_reader)
            except Exception as error:
                self.errors.append({"object": node["name"], "error": str(error)})
                continue
            renderer_value = renderer.parse_as_object()
            materials = [self.export_material(ptr.deref()) if ptr else None for ptr in renderer_value.m_Materials]
            records[pid] = {"mesh": mesh_key, "materials": materials, "active": bool(game_object.m_IsActive)}
            mesh_nodes += 1
            ancestor_id = pid
            while ancestor_id != reference_id:
                ancestor = self.node(ancestor_id)
                father = ancestor["transform"].m_Father
                if not father:
                    raise ValueError(f"Object outside group: {node['name']}")
                ancestor_id = father.deref().parse_as_object().m_GameObject.m_PathID
                records.setdefault(ancestor_id, {})

        output = []
        for pid, value in records.items():
            node = self.node(pid)
            transform = node["transform"]
            rotation = transform.m_LocalRotation
            parent_id = (
                transform.m_Father.deref().parse_as_object().m_GameObject.m_PathID
                if transform.m_Father and pid != reference_id
                else None
            )
            output.append({
                "id": pid,
                "name": node["name"],
                "parent": parent_id,
                "position": v3(transform.m_LocalPosition) if pid != reference_id else [0, 0, 0],
                "rotation": [rotation.x, rotation.y, rotation.z, rotation.w] if pid != reference_id else [0, 0, 0, 1],
                "scale": v3(transform.m_LocalScale) if pid != reference_id else [1, 1, 1],
                "source_active": bool(node["game_object"].m_IsActive),
                **value,
            })
        print(f"{expected_name}: {mesh_nodes} render meshes, {len(output)} hierarchy nodes", flush=True)
        return {"description": spec["description"], "reference": expected_name, "nodes": output}

    def run(self):
        groups = {name: self.export_group(spec) for name, spec in GROUPS.items()}
        sun_materials = []
        for material_id in (1503, 1502, 1501, 1500, 1499):
            sun_materials.append(self.export_material(self.resolve({"m_FileID": 2, "m_PathID": material_id}, self.level)))
        sun_sphere = self.export_mesh(self.resolve({"m_FileID": 2, "m_PathID": 3969}, self.level))
        manifest = {
            "format": 1,
            "unity_version": "2019.4.39f1",
            "unitypy_version": UnityPy.__version__,
            "source_directory": str(self.data),
            "groups": groups,
            "meshes": self.meshes,
            "materials": self.materials,
            "textures": self.textures,
            "sun_materials": sun_materials,
            "sun_sphere_mesh": sun_sphere,
            "sun_geometry_note": "Extracted game geodesic sphere substitutes for the runtime TessellatedSphereRenderer; SunProxy is preserved separately",
            "errors": self.errors,
        }
        (self.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
        print({"meshes": len(self.meshes), "materials": len(self.materials), "textures": len(self.textures), "errors": len(self.errors)}, flush=True)
        if self.errors or any(not group["nodes"] for group in groups.values()):
            raise RuntimeError("Extraction incomplete; inspect manifest.json before importing")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "private" / "outer-wilds-extracted" / "sun-and-dlc" / "scene-data")
    args = parser.parse_args()
    Extractor(args.data.resolve(), args.output.resolve()).run()


if __name__ == "__main__":
    main()
