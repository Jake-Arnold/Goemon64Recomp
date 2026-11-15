#!/usr/bin/env python3
"""Make a separate all-assembly Splat configuration for Japan N64Recomp research.

The normal Japan Splat config retains C sections for matching decompilation.
N64Recomp needs instructions for every function, including C-designated segments.
This tool never edits the supplied YAML or ROM and never commits extracted code.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

EXPECTED_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
GENERATED_ROOT = "build-generated/japan_recomp"
SPLAT_ROOT = ".splat/japan_recomp"


def convert(config: dict) -> tuple[dict, int]:
    if config.get("sha1") != EXPECTED_SHA1:
        raise ValueError("Unrecognised Japanese decompressed ROM SHA-1")
    if not isinstance(config.get("segments"), list):
        raise ValueError("Japanese Splat segments are missing")
    result = yaml.safe_load(yaml.safe_dump(config, sort_keys=False))
    options = result["options"]
    options.update({
        "asm_path": GENERATED_ROOT + "/asm",
        "src_path": GENERATED_ROOT + "/src",
        "asset_path": GENERATED_ROOT + "/bin",
        "build_path": GENERATED_ROOT + "/build",
        "ld_script_path": SPLAT_ROOT + "/mnsg.ld",
        "undefined_funcs_auto_path": SPLAT_ROOT + "/undefined_funcs_auto.ld",
        "undefined_syms_auto_path": SPLAT_ROOT + "/undefined_syms_auto.ld",
    })
    changed = 0
    for segment in result["segments"]:
        if not isinstance(segment, dict) or segment.get("type") != "code":
            continue
        for subsection in segment.get("subsegments", []):
            if isinstance(subsection, list) and len(subsection) > 1 and subsection[1] == "c":
                subsection[1] = "asm"
                changed += 1
    if changed == 0:
        raise ValueError("No C-designated Japanese code subsections to convert")
    if result["sha1"] != config["sha1"] or result["segments"] == config["segments"]:
        raise ValueError("Converted Splat config did not preserve source identity")
    return result, changed


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--japan-splat", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    source = args.japan_splat.resolve(strict=True)
    output = args.output.resolve()
    if source == output:
        cli.error("Refusing to overwrite original Splat configuration")
    if output.exists():
        cli.error("Output exists: choose a fresh isolated filename")
    try:
        original = yaml.safe_load(source.read_text())
        converted, changed = convert(original)
    except (OSError, ValueError, KeyError) as error:
        cli.error(str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(converted, sort_keys=False, allow_unicode=True))
    print(json.dumps({"config": str(output), "c_to_asm": changed,
                      "generated_asm": converted["options"]["asm_path"],
                      "source_unchanged": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
