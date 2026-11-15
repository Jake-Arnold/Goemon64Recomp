#!/usr/bin/env python3
"""Correct a specific, ROM-verified Japanese libultra exception symbol split.

Splat's generic exception assembly labels combine two *known* libultra
functions into one 0xE8-byte candidate. The pinned N64Recomp runtime
identifies send_mesg and handle_CpU as built-in OS routines, rather
than recompiling their handwritten exception-handler branches.

The correction is SHA-1-scoped and checks the exact instruction words at
the split. It never edits or distributes the underlying Japanese ROM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path

SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
ORIGINAL = '    { name = "func_80049604_4A204", vram = 0x80049604, size = 0xE8 },'
CORRECTED = (
    '    { name = "send_mesg", vram = 0x80049604, size = 0xB4 },\n'
    '    { name = "handle_CpU", vram = 0x800496B8, size = 0x34 },'
)
ROM_WORDS = {
    0x4A204: 0x3C0A801D,  # start of send_mesg
    0x4A2B8: 0x3C013000,  # start of handle_CpU
    0x4A2E8: 0xAF5B0118,  # final instruction of handle_CpU
}


def refine(source: str, rom: bytes) -> tuple[str, dict]:
    if len(rom) != 0x2000000 or hashlib.sha1(rom).hexdigest() != SHA1:
        raise ValueError("Expected exact Japanese decompressed 32 MiB ROM")
    for position, word in ROM_WORDS.items():
        actual = int.from_bytes(rom[position:position+4], "big")
        if actual != word:
            raise ValueError(f"Unexpected libultra instruction at ROM 0x{position:X}")
    data = tomllib.loads(source)
    sections = data.get("section", [])
    main = next((s for s in sections if s.get("name") == ".main"), None)
    if main is None:
        raise ValueError("Missing Japanese main section")
    original = [f for f in main["functions"]
                if f.get("vram") == 0x80049604]
    if (len(original) != 1
            or original[0] != {
                "name": "func_80049604_4A204",
                "vram": 0x80049604,
                "size": 0xE8,
            }):
        raise ValueError("Expected generic Japanese exception function boundary")
    if any(f.get("vram") == 0x800496B8 for f in main["functions"]):
        raise ValueError("Split address is already a function")
    if source.count(ORIGINAL) != 1:
        raise ValueError("Expected one exact libultra declaration in source")
    result = source.replace(ORIGINAL, CORRECTED)
    reparsed = tomllib.loads(result)
    adjusted = next(s for s in reparsed["section"] if s["name"] == ".main")
    replacement = [f for f in adjusted["functions"]
                   if 0x80049604 <= f["vram"] < 0x800496EC]
    if (len(replacement) != 2
            or replacement[0]["size"] + replacement[1]["size"] != 0xE8):
        raise ValueError("Libultra function partition is not contiguous")
    counts = {
        "original_function_count": sum(len(s["functions"]) for s in sections),
        "revised_function_count": sum(len(s["functions"]) for s in reparsed["section"]),
        "two_runtime_supplied_libultra_symbols": ["send_mesg", "handle_CpU"],
        "source_rom_sha1": SHA1,
    }
    if counts["revised_function_count"] != counts["original_function_count"] + 1:
        raise ValueError("Unexpected function inventory change")
    return result, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--candidate-symbols", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.rom.resolve(), args.candidate_symbols.resolve()):
        parser.error("Refusing to overwrite an input")
    try:
        source, counts = refine(args.candidate_symbols.read_text(), args.rom.read_bytes())
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source)
    print(json.dumps({**counts, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
