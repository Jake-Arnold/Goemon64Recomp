#!/usr/bin/env python3
"""Experimental JP-only recovery of three ROM-backed libultra functions.

N64Recomp maps certain libultra names to host _recomp implementations.
Three leaf functions are missing from the pinned host runtime. Renaming the
source symbol permits compiling their original MIPS instruction bodies to
native C instead. Diagnostic only: NOT proof of correct controller-pak gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from pathlib import Path

ROM_HASH = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
LEAVES = {
    "__osCheckId": (0x8004CFC0, 0xFC),
    "__osPfsRWInode": (0x8004D0BC, 0x320),
    "__osPfsSelectBank": (0x8004D3DC, 0x6C),
}


def apply(source: str) -> tuple[str, dict]:
    parsed = tomllib.loads(source)
    sections = parsed.get("section", [])
    main = [s for s in sections if s.get("name") == ".main"]
    if len(main) != 1:
        raise ValueError("Expected exactly one Japanese .main section")
    all_names = [f["name"] for s in sections for f in s.get("functions", [])]
    if len(set(all_names)) != len(all_names):
        raise ValueError("Duplicate original symbol names")
    count_before = len(all_names)
    result = source
    for name, (vram, size) in LEAVES.items():
        candidates = [f for f in main[0].get("functions", []) if f["name"] == name]
        if len(candidates) != 1 or (candidates[0]["vram"], candidates[0]["size"]) != (vram, size):
            raise ValueError(f"Unexpected Japanese libultra function layout: {name}")
        alias = "jp_impl_" + name
        if alias in all_names:
            raise ValueError("Alias already exists: " + alias)
        line = f'{{ name = "{name}", vram = 0x{vram:08X}, size = 0x{size:X} }}'
        if result.count(line) != 1:
            raise ValueError(f"Expected one original TOML symbol row for {name}")
        result = result.replace(
            line, f'{{ name = "{alias}", vram = 0x{vram:08X}, size = 0x{size:X} }}', 1
        )
    after = tomllib.loads(result)
    final = [f for s in after["section"] for f in s.get("functions", [])]
    if len(final) != count_before or any(
        name in {f["name"] for f in final} for name in LEAVES
    ):
        raise ValueError("Experimental rewrite did not preserve function inventory")
    return result, {
        "aliases": sorted("jp_impl_" + name for name in LEAVES),
        "input_functions": count_before,
        "output_functions": len(final),
        "status": "Experimental C-generation metadata; PFS semantics and linking unverified",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--symbols", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.rom.resolve(), args.symbols.resolve()):
        parser.error("Output must not overwrite source files")
    try:
        data = args.rom.read_bytes()
        if len(data) != 0x2000000 or hashlib.sha1(data).hexdigest() != ROM_HASH:
            parser.error("Only the exact Japanese decompressed revision is supported")
        rewritten, report = apply(args.symbols.read_text())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rewritten)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({**report, "rom_sha1": ROM_HASH, "output": str(args.output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
