#!/usr/bin/env python3
"""Insert the Japan-only overlay registration hook into private generated C.

The Japanese original game loader does not notify N64ModernRuntime when an
executable overlay is loaded; the USA port patches this in USA-specific code.
Strictly verify the user's own decompressed Japanese ROM before the operation.
This is a source-only transformation, not ROM data or generated game code.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

JP_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
ROM_TABLE_OFFSET = 0x58258
ROM_TABLE_VRAM = 0x80057658
LOADER = "RECOMP_FUNC void func_80001BA0_27A0(uint8_t* rdram, recomp_context* ctx) {\n"
MARKER = "jp_native_register_file_overlay"
HOOK = """
// Japan-only native overlay registration bridge. Original game loader follows.
extern void load_overlays(uint32_t rom, int32_t ram_addr, uint32_t size);
static void jp_native_register_file_overlay(uint8_t* rdram, recomp_context* ctx) {
    const uint32_t file_id = (uint32_t)ctx->r4;
    if (file_id == 0 || file_id >= 0x520u) return;
    // N64Recomp MEM_W expects a sign-extended 64-bit KSEG0 address.
    const uint32_t raw_addr = 0x80057658u + (file_id - 1u) * 4u;
    const gpr table_addr = (gpr)(int64_t)(int32_t)raw_addr;
    const uint32_t rom_start = (uint32_t)MEM_W(0, table_addr) & 0x7FFFFFFFu;
    const uint32_t rom_end = (uint32_t)MEM_W(4, table_addr) & 0x7FFFFFFFu;
    if (rom_start >= 0x1000u && rom_end > rom_start && rom_end <= 0x2000000u) {
        load_overlays(rom_start, (int32_t)ctx->r5, rom_end - rom_start);
    }
}

"""


def check_rom(data: bytes) -> None:
    if len(data) != 0x2000000 or hashlib.sha1(data).hexdigest() != JP_SHA1:
        raise ValueError("Requires exact Japanese 32 MiB decompressed ROM")
    for file_id, expected in ((22, 0x6A2B70), (23, 0x6AE410)):
        index = ROM_TABLE_OFFSET + (file_id - 1) * 4
        actual = int.from_bytes(data[index:index + 4], "big") & 0x7FFFFFFF
        if actual != expected:
            raise ValueError(f"Japanese file table differs at file {file_id}")
    if ROM_TABLE_VRAM != 0x80000450 + ROM_TABLE_OFFSET - 0x1050:
        raise ValueError("Japanese main ROM-to-VRAM mapping changed")


def inject(source: str) -> str:
    if MARKER in source:
        raise ValueError("Japanese native loader hook already present")
    if source.count(LOADER) != 1:
        raise ValueError("Missing unique Japanese func_80001BA0_27A0 definition")
    if '#include "recomp.h"\n' not in source:
        raise ValueError("Expected N64Recomp generated C source")
    modified = source.replace(LOADER, HOOK + LOADER +
                              "    jp_native_register_file_overlay(rdram, ctx);\n", 1)
    if modified.count("jp_native_register_file_overlay(rdram, ctx);") != 1:
        raise ValueError("Japanese loader hook injection failed")
    return modified


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--rom", type=Path, required=True)
    cli.add_argument("--source", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--in-place", action="store_true",
                     help="Explicitly permit updating private generated C")
    args = cli.parse_args()
    if args.source.resolve() == args.output.resolve() and not args.in_place:
        cli.error("Use --in-place to overwrite private generated C source")
    try:
        check_rom(args.rom.read_bytes())
        result = inject(args.source.read_text())
    except (ValueError, OSError) as error:
        cli.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result)
    print(json.dumps({
        "updated_c_source": str(args.output),
        "source_sha1": JP_SHA1,
        "loader_vram": "0x80001BA0",
        "file_table_vram": f"0x{ROM_TABLE_VRAM:08X}",
    }, indent=2))


if __name__ == "__main__":
    main()
