#!/usr/bin/env python3
"""Prepare a region-isolated Japanese N64Recomp diagnostic run.

Creates no game content. Inputs are the user's exact Japanese decompressed ROM
and the locally generated provisional symbol/relocation TOML.
N64Recomp execution is optional and does not imply a playable PC build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from pathlib import Path

JP_ROM_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
JP_ROM_SIZE = 0x2000000
ENTRYPOINT = 0x80000400
OVERLAYS = [f".file_{number}" for number in range(24, 81)]


def inspect_symbol_map(symbol_map: dict) -> dict:
    sections = symbol_map.get("section", [])
    if len(sections) != 72 or len({s["name"] for s in sections}) != 72:
        raise ValueError("Expected 72 distinct Japanese section candidates")
    by_name = {s["name"]: s for s in sections}
    entry = by_name.get(".entry", {})
    entry_functions = entry.get("functions", [])
    if (entry.get("rom") != 0x1000
            or entry.get("vram") != ENTRYPOINT
            or len(entry_functions) != 1
            or entry_functions[0].get("name") != "recomp_entrypoint"
            or entry_functions[0].get("vram") != ENTRYPOINT
            or entry_functions[0].get("size") != 0x38):
        raise ValueError("Japanese entrypoint was not explicitly mapped to recomp_entrypoint")
    if {s["name"] for s in sections if s.get("vram") == 0x08000000} != set(OVERLAYS):
        raise ValueError("Expected exactly the Japanese file_24 through file_80 overlays")
    names = [by_name[n]["name"] for n in OVERLAYS]
    if any(by_name[name]["size"] <= 0 for name in names):
        raise ValueError("Overlay section has invalid size")
    if any("relocs" not in by_name[name] or not isinstance(by_name[name]["relocs"], list)
           for name in names):
        raise ValueError("Every relocatable overlay must have a relocs array (even empty)")
    functions = sum(len(s.get("functions", [])) for s in sections)
    relocations = sum(len(s.get("relocs", [])) for s in sections)
    if functions < 7300 or relocations < 6400:
        raise ValueError("Incomplete metadata: older candidate inventory or missing BSS relocations")
    return {"sections": len(sections), "functions": functions,
            "relocations": relocations, "relocatable_overlays": len(OVERLAYS)}


def create_probe(rom_file: Path, symbols_file: Path, output_dir: Path) -> dict:
    rom_file = rom_file.resolve(strict=True)
    symbols_file = symbols_file.resolve(strict=True)
    rom = rom_file.read_bytes()
    sha1 = hashlib.sha1(rom).hexdigest()
    if len(rom) != JP_ROM_SIZE or sha1 != JP_ROM_SHA1:
        raise ValueError("Japanese decompressed ROM size or SHA-1 mismatch")
    symbols_text = symbols_file.read_text()
    if "INCOMPLETE JAPAN N64RECOMP CANDIDATE MAP" not in symbols_text:
        raise ValueError("Expected explicit provisional Japanese symbol-map header")
    counts = inspect_symbol_map(tomllib.loads(symbols_text))
    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_file = output_dir / "japan.overlays.txt"
    config_file = output_dir / "japan.recomp.probe.toml"
    overlay_file.write_text("\n".join(OVERLAYS) + "\n")
    # JSON-quoted strings are safe TOML basic strings for Linux paths.
    q = lambda path: json.dumps(str(path))
    output_folder = output_dir / "RecompiledFuncsJP"
    config_file.write_text(
        "# DIAGNOSTIC ONLY. JAPANESE N64RECOMP OUTPUT IS NOT A PC GAME.\n"
        "[input]\n"
        "entrypoint = 0x80000400\n"
        f"output_func_path = {q(output_folder.resolve())}\n"
        f"relocatable_sections_path = {q(overlay_file.resolve())}\n"
        f"symbols_file_path = {q(symbols_file)}\n"
        f"rom_file_path = {q(rom_file)}\n"
        "trace_mode = true\n"
        "bss_section_suffix = \"_bss\"\n\n"
        "[patches]\n"
        "stubs = []\n"
        "ignored = []\n"
    )
    result = {**counts, "source_rom_sha1": sha1,
              "config": str(config_file.resolve()),
              "overlay_list": str(overlay_file.resolve()),
              "output_directory": str(output_folder.resolve()),
              "status": "Probe input generated; no N64Recomp execution yet"}
    (output_dir / "japan.probe-manifest.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--rom", type=Path, required=True)
    cli.add_argument("--symbols", type=Path, required=True)
    cli.add_argument("--output-dir", type=Path, required=True)
    cli.add_argument("--n64recomp", type=Path,
                     help="Optional pinned host-side recompiler to execute immediately")
    args = cli.parse_args()
    try:
        report = create_probe(args.rom, args.symbols, args.output_dir.resolve())
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as error:
        cli.error(str(error))
    if args.n64recomp is not None:
        compiler = args.n64recomp.resolve(strict=True)
        if not compiler.is_file():
            cli.error("N64Recomp executable not found")
        # Metadata correctness and execution success are distinct gates.
        completed = subprocess.run([str(compiler), report["config"]],
                                   cwd=args.output_dir.resolve(), check=False)
        report["n64recomp_exit_status"] = completed.returncode
        print(json.dumps(report, indent=2))
        return completed.returncode
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
