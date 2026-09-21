#!/usr/bin/env python3
"""Statically extract compact celestial/spacecraft roots not in the proxy catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import UnityPy

from extract_outer_wilds_sun_dlc import Extractor, PROJECT_ROOT


GROUPS_BY_LEVEL = {
    "level0": {
        "player_ship": {
            "reference": (88, "Structure_HEA_PlayerShip_v4_NearProxy"),
            "roots": [88],
            "description": "Player spacecraft near proxy",
        },
    },
    "level1": {
        "nomai_shuttle": {
            "reference": (89827, "Structure_NOM_Shuttle_Exterior"),
            "roots": [89827],
            "description": "Nomai shuttle exterior",
        },
    },
    "level2": {
        "nomai_vessel": {
            "reference": (394, "Structure_NOM_Vessel"),
            "roots": [388, 387, 386, 385, 390],
            "description": "Nomai Vessel exterior shell, opening, glass and lights",
        },
        "eye_proxy": {
            "reference": (1666, "Proxy_SixthPlanet"),
            "roots": [1193],
            "description": "Eye of the Universe distant quadsphere; oversized symbol effect excluded",
        },
    },
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "private" / "outer-wilds-extracted" / "web-high-source" / "scene-data",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    groups = {}
    meshes = {}
    materials = {}
    textures = {}
    errors = []
    extras = {}
    for level_name, specs in GROUPS_BY_LEVEL.items():
        extractor = Extractor(args.data.resolve(), output, level_name=level_name)
        for name, spec in specs.items():
            groups[name] = extractor.export_group(spec)
        meshes.update(extractor.meshes)
        materials.update(extractor.materials)
        textures.update(extractor.textures)
        errors.extend(extractor.errors)
        if level_name == "level1":
            extras["ash_sand_sphere_mesh"] = extractor.export_mesh(
                extractor.resolve({"m_FileID": 2, "m_PathID": 3969}, extractor.level)
            )
            extras["ash_sand_materials"] = [
                extractor.export_material(
                    extractor.resolve({"m_FileID": 2, "m_PathID": material_id}, extractor.level)
                )
                for material_id in (704, 705)
            ]
            meshes.update(extractor.meshes)
            materials.update(extractor.materials)
            textures.update(extractor.textures)

    manifest = {
        "format": 1,
        "unity_version": "2019.4.39f1",
        "unitypy_version": UnityPy.__version__,
        "source_directory": str(args.data.resolve()),
        "groups": groups,
        "meshes": meshes,
        "materials": materials,
        "textures": textures,
        "errors": errors,
        **extras,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    print({"groups": len(groups), "meshes": len(meshes), "materials": len(materials), "textures": len(textures), "errors": len(errors)}, flush=True)
    if errors or any(not group["nodes"] for group in groups.values()):
        raise RuntimeError("Special asset extraction incomplete; inspect manifest.json")


if __name__ == "__main__":
    main()
