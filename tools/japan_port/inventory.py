#!/usr/bin/env python3
"""Compare Splat overlay candidates for USA and Japan (metadata only).

Candidate segments alone are insufficient to generate N64Recomp symbols.
Requires PyYAML; produces no extracted game code or game assets.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

EXECUTABLE = {"asm", "hasm", "c"}


def inspect(path: Path) -> dict:
    configuration = yaml.safe_load(path.read_text())
    overlays = {}
    code_count = 0
    for segment in configuration["segments"]:
        if not isinstance(segment, dict) or segment.get("type") != "code":
            continue
        code_count += 1
        types = {
            entry[1] for entry in segment.get("subsegments", [])
            if isinstance(entry, list) and len(entry) > 1
        }
        if segment.get("overlay") and types & EXECUTABLE:
            overlays[segment["name"]] = {
                "rom": segment["start"], "vram": segment["vram"]
            }
    return {
        "sha1": configuration["sha1"],
        "code_type_segments": code_count,
        "overlay_candidates": overlays,
        "relocation_paths": configuration["options"].get("reloc_addrs_path", []),
    }


def compare(japan_path: Path, usa_path: Path) -> dict:
    jp, us = inspect(japan_path), inspect(usa_path)
    names = sorted(set(jp["overlay_candidates"]) & set(us["overlay_candidates"]),
                   key=lambda name: int(name.rsplit("_", 1)[-1]))
    diffs = []
    for name in names:
        j, u = jp["overlay_candidates"][name], us["overlay_candidates"][name]
        if j != u:
            diffs.append({
                "name": name,
                "japan_rom": f"0x{j['rom']:X}",
                "japan_vram": f"0x{j['vram']:X}",
                "usa_rom": f"0x{u['rom']:X}",
                "usa_vram": f"0x{u['vram']:X}",
            })
    return {
        "japan_sha1": jp["sha1"], "usa_sha1": us["sha1"],
        "japan_overlay_candidates": len(jp["overlay_candidates"]),
        "usa_overlay_candidates": len(us["overlay_candidates"]),
        "overlays_compared": len(names),
        "different_overlay_addresses": len(diffs),
        "japan_relocation_paths": jp["relocation_paths"],
        "differences": diffs,
        "warning": "Not an N64Recomp section/function/relocation map",
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--japan-splat", type=Path, required=True)
    cli.add_argument("--usa-splat", type=Path, required=True)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    result = compare(args.japan_splat, args.usa_splat)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
