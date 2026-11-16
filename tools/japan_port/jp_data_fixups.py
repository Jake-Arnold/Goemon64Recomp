#!/usr/bin/env python3
"""Guarded JP file 56 data pointer fixups for privately generated N64Recomp C.

N64ModernRuntime's pinned osMapTLB no-op does not remap guest data pointers.
Overlay 56 contains two 32-bit pointer tables used by native game functions.
All 15 sites and their targets are verified against the exact Japanese ROM.
No ROM bytes or generated game source are included in the repository.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

JP_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
FILE_ID = 56
ROM_START, ROM_END, ROM_DATA_START = 0x7174A0, 0x71B3C0, 0x71AE90
ROM_SIZE = ROM_END - ROM_START
SITE_TARGETS = (
    (0x3AB0, 0x39F0), (0x3AB4, 0x3A08), (0x3AB8, 0x3A2C),
    (0x3ABC, 0x3A44), (0x3AC0, 0x3A5C), (0x3AC4, 0x3A74),
    (0x3AC8, 0x3A8C), (0x3ACC, 0x3A98), (0x3AD0, 0x3AA4),
    (0x3ECC, 0x244C), (0x3ED0, 0x249C), (0x3ED4, 0x24F8),
    (0x3ED8, 0x2554), (0x3EDC, 0x25B0), (0x3EE0, 0x2600),
)
MARKER = "jp_relocate_file_56_data"
BEFORE = "static void jp_relocate_task_callbacks(uint8_t* rdram, recomp_context* ctx, gpr task) {"
AFTER = "    if (end <= start || end > 0x02000000u) return;"


def validate_rom(data: bytes) -> None:
    if len(data) != 0x2000000 or hashlib.sha1(data).hexdigest() != JP_SHA1:
        raise ValueError("Wrong Japanese decompressed ROM hash or size")
    table = 0x58258 + 4 * (FILE_ID - 1)
    start = int.from_bytes(data[table:table + 4], "big") & 0x7FFFFFFF
    end = int.from_bytes(data[table + 4:table + 8], "big") & 0x7FFFFFFF
    if (start, end) != (ROM_START, ROM_END) or not start <= ROM_DATA_START <= end:
        raise ValueError("Japanese overlay 56 file table/data boundary differs")
    observed = {}
    for site in range(ROM_DATA_START - start, ROM_SIZE, 4):
        word = int.from_bytes(data[start + site:start + site + 4], "big")
        if 0x08000000 <= word < 0x08000000 + ROM_SIZE:
            observed[site] = word - 0x08000000
    if observed != dict(SITE_TARGETS):
        raise ValueError("Japanese overlay 56 data pointer inventory differs")


def hook_text() -> str:
    pairs = "\n".join(
        "        {%#06xu, %#06xu}," % (site, target)
        for site, target in SITE_TARGETS
    )
    return """// JP file 56: the original data pointer tables contain TLB-relative
// pointers, but this host runtime does not emulate data TLB translation.
// Validate ALL 15 expected live words before writing any; retry safe.
static void jp_relocate_file_56_data(uint8_t* rdram, uint32_t base) {
    static const struct { uint16_t site, target; } pointers[] = {
%s
    };
    const gpr dst = (gpr)(int64_t)(int32_t)base;
    for (unsigned i = 0; i < sizeof(pointers) / sizeof(pointers[0]); ++i) {
        const uint32_t current = (uint32_t)MEM_W(pointers[i].site, dst);
        const uint32_t original = 0x08000000u + pointers[i].target;
        const uint32_t relocated = base + pointers[i].target;
        if (current != original && current != relocated) return;
    }
    for (unsigned i = 0; i < sizeof(pointers) / sizeof(pointers[0]); ++i) {
        const uint32_t current = (uint32_t)MEM_W(pointers[i].site, dst);
        if (current == 0x08000000u + pointers[i].target)
            MEM_W(pointers[i].site, dst) = base + pointers[i].target;
    }
}

""" % pairs


def inject(source: str) -> str:
    if MARKER in source:
        raise ValueError("Japan file 56 data fixup already applied")
    if source.count(BEFORE) != 1 or source.count(AFTER) != 1:
        raise ValueError("Japanese callback relocation anchors missing or ambiguous")
    if source.count("jp_relocate_task_callbacks(rdram, ctx, jp_task);") != 1:
        raise ValueError("Japanese task callback registration missing")
    with_helper = source.replace(BEFORE, hook_text() + BEFORE, 1)
    anchor = AFTER + "\n"
    replacement = (
        anchor
        + "    // Relocate only the independently verified file 56 data section.\n"
        + "    if (file_id == 56u && start == 0x007174A0u && end == 0x0071B3C0u &&\n"
        + "        base <= 0x80800000u - 0x3F20u) {\n"
        + "        jp_relocate_file_56_data(rdram, base);\n"
        + "    }\n"
    )
    if with_helper.count(anchor) != 1:
        raise ValueError("Expected unique callback ROM-span gate")
    modified = with_helper.replace(anchor, replacement, 1)
    if modified.count("jp_relocate_file_56_data(rdram, base);") != 1:
        raise ValueError("Failed to inject exactly one file 56 fixup")
    return modified


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() and not args.in_place:
        parser.error("Use --in-place to overwrite private generated C")
    try:
        validate_rom(args.rom.read_bytes())
        modified = inject(args.source.read_text())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(modified)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print("Verified Japanese file 56 data fixups applied to", args.output)


if __name__ == "__main__":
    main()
