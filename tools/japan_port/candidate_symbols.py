#!/usr/bin/env python3
"""Extract Japan function symbol candidates from locally generated Splat assembly.

No ROM data or instructions are included in the output. Relocations, data
symbols, indirect branch targets and some handwritten/C-only functions still
require independent analysis. Do not claim this is N64Recomp-ready.
"""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections import defaultdict
from pathlib import Path

import yaml

DECLARATION = re.compile(
    r'^nonmatching\s+([A-Za-z_][A-Za-z0-9_]*),\s*(0x[0-9A-Fa-f]+)',
    re.MULTILINE,
)
INSTRUCTION = re.compile(
    r'/\*\s*([0-9A-Fa-f]{3,8})\s+([0-9A-Fa-f]{8})\s+[0-9A-Fa-f]{8}\s*\*/',
)
EXECUTABLE_TYPES = {"asm", "hasm", "c"}


def sections(splat: Path) -> list[dict]:
    segments = yaml.safe_load(splat.read_text())["segments"]
    result = []
    for index, segment in enumerate(segments[:-1]):
        if not isinstance(segment, dict) or segment.get("type") != "code":
            continue
        name = segment.get("name", "")
        kinds = {
            sub[1] for sub in segment.get("subsegments", [])
            if isinstance(sub, list) and len(sub) > 1
        }
        if not kinds.intersection(EXECUTABLE_TYPES):
            continue
        if name not in ("entry", "main") and not (
            segment.get("overlay") and name.startswith("file_")
        ):
            continue
        result.append({
            "name": name,
            "start": segment["start"],
            "end": segments[index + 1]["start"],
            "vram": segment["vram"],
            "bss_size": segment.get("bss_size", 0),
        })
    if not result:
        raise ValueError("No executable section candidates in Splat input")
    return result


def parse_functions(asm_root: Path, sections: list[dict]) -> list[dict]:
    if not asm_root.is_dir():
        raise ValueError(f"Missing extracted assembly folder: {asm_root}")
    found = []
    for path in sorted(asm_root.rglob("*.s")):
        if "data" in path.relative_to(asm_root).parts:
            continue
        source = path.read_text(errors="replace")
        matches = list(DECLARATION.finditer(source))
        for i, declaration in enumerate(matches):
            name, size = declaration.group(1), int(declaration.group(2), 16)
            fragment = source[
                declaration.end():
                matches[i + 1].start() if i + 1 < len(matches) else len(source)
            ]
            instruction = INSTRUCTION.search(fragment)
            if instruction is None:
                raise ValueError(f"{path}: {name} missing first-instruction annotation")
            rom, vram = int(instruction.group(1), 16), int(instruction.group(2), 16)
            matching_sections = [
                section for section in sections
                if section["start"] <= rom < section["end"]
                and section["vram"] + rom - section["start"] == vram
            ]
            if len(matching_sections) != 1 or size <= 0 or size % 4:
                raise ValueError(f"{path}: {name} invalid section or size")
            section = matching_sections[0]
            if rom + size > section["end"]:
                raise ValueError(f"{path}: {name} extends beyond section")
            if section["name"] == "entry":
                if ((rom, vram, size) != (0x1000, 0x80000400, 0x38)
                        or name not in ("func_80000400_1000", "recomp_entrypoint")):
                    raise ValueError("Japanese entrypoint layout or name differs from the native runtime ABI")
                name = "recomp_entrypoint"
            found.append({
                "section": section["name"], "name": name,
                "rom": rom, "vram": vram, "size": size,
            })
    by_section = defaultdict(list)
    for function in found:
        by_section[function["section"]].append(function)
    if len(by_section["entry"]) != 1 or by_section["entry"][0]["name"] != "recomp_entrypoint":
        raise ValueError("Japanese ROM did not yield one validated native entrypoint")
    for section, functions in by_section.items():
        ordered = sorted(functions, key=lambda function: function["vram"])
        for previous, following in zip(ordered, ordered[1:]):
            if previous["vram"] + previous["size"] > following["vram"]:
                raise ValueError(
                    f"Overlapping functions in {section}: "
                    f"{previous['name']} and {following['name']}"
                )
    return found


def render(sections: list[dict], functions: list[dict]) -> str:
    by_section = defaultdict(list)
    for function in functions:
        by_section[function["section"]].append(function)
    lines = [
        "# Japanese candidate symbols only; relocations/data symbols not generated.",
        "# Not verified for native N64Recomp; never substitute USA relocations.",
        "",
    ]
    for section in sections:
        lines.extend([
            "[[section]]",
            f'name = ".{section["name"]}"',
            f'rom = 0x{section["start"]:08X}',
            f'vram = 0x{section["vram"]:08X}',
            f'size = 0x{section["end"] - section["start"]:X}',
            "functions = [",
        ])
        section_functions = sorted(by_section[section["name"]],
                                   key=lambda function: function["vram"])
        if section["name"] == "entry":
            if (len(section_functions) != 1
                    or section_functions[0]["vram"] != 0x80000400
                    or section_functions[0]["size"] != 0x38):
                raise ValueError("Japanese entrypoint must be the 0x38-byte function at 0x80000400")
        for function in section_functions:
            # PC runtime exports a fixed entrypoint name. The disassembler's
            # generic name is valid for research but would break native linking.
            name = "recomp_entrypoint" if section["name"] == "entry" else function["name"]
            lines.append(
                f'    {{ name = "{name}", '
                f'vram = 0x{function["vram"]:08X}, '
                f'size = 0x{function["size"]:X} }},'
            )
        lines.extend(["]", ""])
    return "\n".join(lines)


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--japan-splat", type=Path, required=True)
    cli.add_argument("--asm-root", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    candidates = sections(args.japan_splat)
    functions = parse_functions(args.asm_root, candidates)
    source = render(candidates, functions)
    decoded = tomllib.loads(source)
    if len(decoded["section"]) != len(candidates) or sum(
        len(section["functions"]) for section in decoded["section"]
    ) != len(functions):
        raise ValueError("Generated TOML count/structure check failed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source)
    print(json.dumps({
        "section_candidates": len(candidates),
        "function_candidates": len(functions),
        "missing_relocations": True,
        "output": str(args.output),
    }))


if __name__ == "__main__":
    main()
