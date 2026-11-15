#!/usr/bin/env python3
"""Compute Splat section candidate bounds, not N64Recomp-ready symbols.

The derived section size is the gap to the following top-level Splat segment.
Exact executable text/function boundaries, relocation sites and indirect
branches must be established separately from the Japanese ROM.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

EXECUTABLE_KINDS = {"asm", "hasm", "c"}


def section_candidates(path: Path) -> list[dict]:
    config = yaml.safe_load(path.read_text())
    segments = config["segments"]
    found: list[dict] = []
    for i, segment in enumerate(segments[:-1]):
        if not isinstance(segment, dict) or segment.get("type") != "code":
            continue
        name = segment.get("name")
        kinds = {
            sub[1] for sub in segment.get("subsegments", [])
            if isinstance(sub, list) and len(sub) >= 2
        }
        if not kinds.intersection(EXECUTABLE_KINDS):
            continue
        if name not in ("entry", "main") and not (
            segment.get("overlay") and isinstance(name, str)
            and name.startswith("file_")
        ):
            continue
        start, end = segment["start"], segments[i + 1]["start"]
        if not 0 <= start < end <= 0x2000000:
            raise ValueError(f"Invalid {name} ROM bounds {start:x}-{end:x}")
        vram = segment.get("vram")
        if not isinstance(vram, int) or not 0 <= vram <= 0xFFFFFFFF:
            raise ValueError(f"Invalid {name} VRAM")
        found.append({
            "name": name,
            "rom_start": f"0x{start:08X}",
            "rom_end_exclusive": f"0x{end:08X}",
            "size": f"0x{end-start:X}",
            "vram": f"0x{vram:08X}",
            "overlay": bool(segment.get("overlay")),
            "subsegments": len(segment.get("subsegments", [])),
        })
    return found


def compare(japan: Path, usa: Path) -> dict:
    jp = section_candidates(japan)
    us = section_candidates(usa)
    usa_by_name = {item["name"]: item for item in us}
    changed = []
    for item in jp:
        original = usa_by_name.get(item["name"])
        if original is not None and item != original:
            changed.append({"name": item["name"], "japan": item, "usa": original})
    return {
        "japan_section_candidates": len(jp),
        "usa_section_candidates": len(us),
        "region_differences": len(changed),
        "japan": jp,
        "changes": changed,
        "caveat": (
            "Splat ROM/VRAM section candidate metadata only. "
            "No complete N64Recomp symbol or relocation map."
        ),
    }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--japan-splat", type=Path, required=True)
    cli.add_argument("--usa-splat", type=Path, required=True)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    data = compare(args.japan_splat, args.usa_splat)
    rendered = json.dumps(data, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(json.dumps({
        key: data[key] for key in (
            "japan_section_candidates",
            "usa_section_candidates",
            "region_differences",
        )
    }))


if __name__ == "__main__":
    main()
