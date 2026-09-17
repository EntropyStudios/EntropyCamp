#!/usr/bin/env python3
"""One-time import of this app's Zen localStorage; never writes the profile."""

import argparse
import ctypes
import ctypes.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from state_store import BusinessStateStore, CARDS, SESSION, HISTORY, CLIPBOARD


def decompress(value):
    library = ctypes.util.find_library("snappy")
    if not library:
        import snappy
        return snappy.decompress(value)
    api = ctypes.CDLL(library)
    api.snappy_uncompressed_length.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    api.snappy_uncompress.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
    length = ctypes.c_size_t()
    if api.snappy_uncompressed_length(value, len(value), ctypes.byref(length)) or length.value > 32 * 1024 * 1024:
        raise ValueError("压缩数据无效或过大")
    buffer = ctypes.create_string_buffer(length.value)
    if api.snappy_uncompress(value, len(value), buffer, ctypes.byref(length)):
        raise ValueError("压缩数据无法解码")
    return buffer.raw[:length.value]


def read_profile(profile):
    path = profile / "storage/default/http+++127.0.0.1+8765/ls/data.sqlite"
    if not path.is_file():
        raise ValueError("没有找到此工具的 Zen 数据")
    connection = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
    try:
        rows = connection.execute("SELECT key, compression_type, value FROM data WHERE key IN (?,?,?,?)", (CARDS, SESSION, HISTORY, CLIPBOARD)).fetchall()
    finally:
        connection.close()
    values = {key: json.loads(decompress(value) if compressed else value) for key, compressed, value in rows}
    script = """
const fs=require('fs'), history=require(process.argv[1]), clips=require(process.argv[2]);
const data=JSON.parse(fs.readFileSync(0,'utf8'));
for(const [key,core,list] of [['lumen-reminder-work-history-v1',history,'entries'],['lumen-multi-clipboard-v1',clips,'items']]) {
 if(!(key in data)) continue;
 const normalized=core.normalizeStore(data[key]);
 const previous=Array.isArray(data[key])?data[key]:data[key][list]||[];
 if(normalized.incompatible||normalized.invalid||normalized[list].length!==previous.length) throw Error('Cannot safely normalize '+key);
 data[key]=normalized;
}
console.log(JSON.stringify(data));
"""
    result = subprocess.run(["node", "-e", script, str(ROOT / "work-history-core.js"), str(ROOT / "clipboard-core.js")], input=json.dumps(values), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    values = read_profile(args.profile)
    store = BusinessStateStore(args.data_dir)
    result = store.initialize(values, "zen-profile")
    data = result["data"]
    print(json.dumps({"imported": result["imported"], "cards": len(data[CARDS]), "history": len(data[HISTORY]["entries"]),
                      "clipboard": len(data[CLIPBOARD]["items"]), "workActive": data[SESSION]["active"], "database": str(store.path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
