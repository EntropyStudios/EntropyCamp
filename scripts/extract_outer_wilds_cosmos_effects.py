#!/usr/bin/env python3
"""Extract official Outer Wilds starfield and supernova study assets."""

from __future__ import annotations

import argparse
from array import array
import json
from pathlib import Path
import sys

import UnityPy
from UnityPy.helpers.MeshHelper import MeshHandler
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXTURES = {
    "resources.assets": {649: "distant-supernova.png"},
    "sharedassets0.assets": {
        219: "star-splatter.png",
        248: "noise-rgb.png",
        291: "star.png",
    },
    "sharedassets1.assets": {
        1600: "sunspots.png",
        2159: "sun-height.png",
        2253: "solar-flare-noise.png",
        2284: "sun-collapse-ramp.png",
        2335: "sun-color-ramp.png",
        2722: "supernova-tendril.png",
        3083: "solar-flare-streamer-mask.png",
        3303: "supernova-ramp.png",
        3344: "supernova-shockwave.png",
        3353: "solar-flare-loop-mask.png",
    },
    "sharedassets2.assets": {
        119: "eye-galaxy-zoom.png",
        142: "eye-star.png",
    },
}
MATERIALS = {
    "resources.assets": [1],
    "sharedassets0.assets": [72, 73, 75],
    "sharedassets1.assets": list(range(1480, 1504)),
    "sharedassets2.assets": [17, 22, 23, 28, 55, 56, 57],
}
PROMINENCE_MESHES = {
    "streamer": {"pathId": 5043, "prefabPathId": 8274, "scaleFactor": [0.5, 1.5, 0.5]},
    "loop": {"pathId": 4783, "prefabPathId": 8275, "scaleFactor": [1.0, 1.5, 1.0]},
    "dome": {"pathId": 4549, "prefabPathId": 8277, "scaleFactor": [3.0, 3.0, 3.0]},
}


def write_array(path: Path, typecode: str, values) -> None:
    payload = array(typecode, values)
    if sys.byteorder != "little":
        payload.byteswap()
    path.write_bytes(payload.tobytes())


def color(value):
    return [float(value.r), float(value.g), float(value.b), float(value.a)]


def export_material(reader) -> dict:
    material = reader.parse_as_object()
    props = material.m_SavedProperties
    textures = {}
    for name, env in props.m_TexEnvs:
        if not env.m_Texture:
            continue
        try:
            textures[name] = env.m_Texture.deref().peek_name()
        except Exception:
            textures[name] = "unresolved"
    return {
        "name": material.m_Name,
        "keywords": material.m_ShaderKeywords,
        "floats": {name: float(value) for name, value in props.m_Floats},
        "colors": {name: color(value) for name, value in props.m_Colors},
        "textures": textures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "private" / "outer-wilds-extracted" / "cosmos-effects",
    )
    args = parser.parse_args()
    data = args.data.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    loaded = {}
    generator = TypeTreeGenerator("2019.4.39f1")
    generator.load_local_dll_folder(str(data / "Managed"))
    manifest = {
        "format": 1,
        "source": str(data),
        "officialAssets": True,
        "textures": {},
        "materials": {},
    }
    for filename in sorted(set(TEXTURES) | set(MATERIALS) | {"sharedassets0.assets"}):
        environment = UnityPy.load(str(data / filename))
        environment.typetree_generator = generator
        loaded[filename] = next(iter(environment.assets))

    shared0 = loaded["sharedassets0.assets"]
    mesh = shared0.objects[558].parse_as_object()
    handler = MeshHandler(mesh)
    handler.process()
    triangles = [index for face in handler.get_triangles()[0] for index in face]
    write_array(output / "starfield-positions.f32", "f", (value for row in handler.m_Vertices for value in row))
    write_array(output / "starfield-uv.f32", "f", (value for row in handler.m_UV0 for value in row[:2]))
    write_array(output / "starfield-colors.f32", "f", (value for row in handler.m_Colors for value in row))
    write_array(output / "starfield-indices.u32", "I", triangles)
    manifest["starfield"] = {
        "name": mesh.m_Name,
        "vertices": len(handler.m_Vertices),
        "triangles": len(triangles) // 3,
        "positions": "starfield-positions.f32",
        "uv": "starfield-uv.f32",
        "colors": "starfield-colors.f32",
        "indices": "starfield-indices.u32",
        "bounds": {"radius": 16.3},
    }

    shared1 = loaded["sharedassets1.assets"]
    prominence = {
        "source": "SolarFlareEmitter official prefabs",
        "lifeLength": 15.0,
        "spawnIntervalSeconds": [1.0, 5.0],
        "streamersPerFlare": [1, 3],
        "scale": [0.02, 0.2],
        "frequencyCurve": [[0.0, 1.0], [20.0, 5.0]],
        "meshes": {},
    }
    for key, spec in PROMINENCE_MESHES.items():
        source = shared1.objects[spec["pathId"]].parse_as_object()
        mesh_handler = MeshHandler(source)
        mesh_handler.process()
        triangles = [index for face in mesh_handler.get_triangles()[0] for index in face]
        prominence["meshes"][key] = {
            "name": source.m_Name,
            "pathId": spec["pathId"],
            "prefabPathId": spec["prefabPathId"],
            "scaleFactor": spec["scaleFactor"],
            "positions": [value for row in mesh_handler.m_Vertices for value in row],
            "normals": [value for row in mesh_handler.m_Normals for value in row],
            "uv": [value for row in mesh_handler.m_UV0 for value in row[:2]],
            "indices": triangles,
        }
    (output / "solar-prominence-geometry.json").write_text(
        json.dumps(prominence, separators=(",", ":")), encoding="utf-8"
    )
    manifest["solarProminence"] = {
        "file": "solar-prominence-geometry.json",
        "meshes": {
            key: {
                "name": value["name"],
                "pathId": value["pathId"],
                "vertices": len(value["positions"]) // 3,
                "triangles": len(value["indices"]) // 3,
            }
            for key, value in prominence["meshes"].items()
        },
    }

    star_groups = shared0.objects[2093].parse_as_dict()["starGroups"]
    level_environment = UnityPy.load(str(data / "level0"))
    level_environment.typetree_generator = generator
    level0 = next(asset for asset in level_environment.assets if Path(asset.name).name == "level0")
    ordered = level0.objects[9364].parse_as_dict()["_orderedStarIndices"]
    stars = []
    for reference in ordered:
        group_index = reference["groupIndex"]
        star_index = reference["starIndex"]
        source = star_groups[group_index]["stars"][star_index]
        stars.append({
            "group": group_index,
            "position": source["position"],
            "scale": source["scale"],
            "color": source["color"],
            "brightness": source["brightness"],
            "supernova": bool(source["supernova"]),
            "deathStartTime": source["deathStartTime"],
            "deathLength": source["deathLength"],
        })
    starfield_data = {
        "source": "StarfieldData + StarfieldController._orderedStarIndices",
        "count": len(stars),
        "supernovaCount": sum(1 for star in stars if star["supernova"]),
        "timelineSeconds": [
            min(star["deathStartTime"] for star in stars),
            max(star["deathStartTime"] for star in stars),
        ],
        "stars": stars,
    }
    (output / "starfield-data.json").write_text(
        json.dumps(starfield_data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    manifest["starfieldData"] = {
        "file": "starfield-data.json",
        "count": starfield_data["count"],
        "supernovaCount": starfield_data["supernovaCount"],
        "timelineSeconds": starfield_data["timelineSeconds"],
    }

    for filename, entries in TEXTURES.items():
        assets = loaded[filename]
        for path_id, target_name in entries.items():
            texture = assets.objects[path_id].parse_as_object()
            texture.image.save(output / target_name)
            manifest["textures"][texture.m_Name] = {
                "file": target_name,
                "source": filename,
                "pathId": path_id,
                "size": [texture.m_Width, texture.m_Height],
            }

    for filename, path_ids in MATERIALS.items():
        assets = loaded[filename]
        for path_id in path_ids:
            reader = assets.objects.get(path_id)
            if reader is None or reader.type.name != "Material":
                continue
            value = export_material(reader)
            value.update({"source": filename, "pathId": path_id})
            manifest["materials"][value["name"]] = value

    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print({
        "starfield_vertices": manifest["starfield"]["vertices"],
        "textures": len(manifest["textures"]),
        "materials": len(manifest["materials"]),
        "output": str(output),
    })


if __name__ == "__main__":
    main()
