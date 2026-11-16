#!/usr/bin/env python3
"""Guarded source-only JP N64Recomp task callback relocation injection.

The game stores TLB overlay callbacks as 0x08000000-relative pointers.
The pinned native runtime's osMapTLB is a no-op; schedule-time callback
dispatch needs the *actual* code destination returned by the original
Japanese game loader. This inserts that translation into locally generated C.

No ROM bytes or generated game code belong in version control.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

JP_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
FUNC = "RECOMP_FUNC void func_800143AC_14FAC(uint8_t* rdram, recomp_context* ctx) {"
BODY_START = "    TRACE_ENTRY()\n    // 0x800143AC: addiu       $sp, $sp, -0x18"
HOOK_NAME = "jp_relocate_task_callbacks"
HELPER = r"""
// Japanese only: TLB overlay callback -> actual loaded KSEG0 address.
static void jp_relocate_task_callbacks(uint8_t* rdram, recomp_context* ctx, gpr task) {
    const uint32_t file_id = (uint32_t)MEM_HU(task, 0x28);
    if (file_id == 0 || file_id >= 0x520u) return;
    const uint32_t offsets[] = {0x08u, 0x0Cu, 0x10u};
    int needs_translation = 0;
    for (unsigned i = 0; i < 3; ++i) {
        const uint32_t cb = (uint32_t)MEM_W(offsets[i], task);
        if (cb >= 0x08000000u && cb < 0x08020000u) needs_translation = 1;
    }
    if (!needs_translation) return;

    // Reuse the original Japanese game's destination lookup; save the
    // complete MIPS register set around the call.
    const recomp_context preserved = *ctx;
    ctx->r4 = (gpr)file_id;
    func_80013D54_14954(rdram, ctx);
    uint32_t base = (uint32_t)ctx->r2;
    *ctx = preserved;
    if (base >= 0xC0000000u && base < 0xC0800000u) base -= 0x40000000u;
    if (base < 0x80000000u || base >= 0x80800000u) return;

    // Only rewrite pointers within the actual ROM-backed code for this
    // file, as identified by the validated JP ROM's file table.
    const uint32_t entry = 0x80057658u + (file_id - 1u) * 4u;
    const gpr table = (gpr)(int64_t)(int32_t)entry;
    const uint32_t start = (uint32_t)MEM_W(0, table) & 0x7FFFFFFFu;
    const uint32_t end = (uint32_t)MEM_W(4, table) & 0x7FFFFFFFu;
    if (end <= start || end > 0x02000000u) return;
    for (unsigned i = 0; i < 3; ++i) {
        const uint32_t cb = (uint32_t)MEM_W(offsets[i], task);
        if (cb >= 0x08000000u && cb < 0x08020000u) {
            const uint32_t offset = cb - 0x08000000u;
            if (offset >= end - start || base + offset < base ||
                base + offset >= 0x80800000u) continue;
            MEM_W(offsets[i], task) = base + offset;
        }
    }
}
"""


def validate_rom(data: bytes) -> None:
    if len(data) != 0x2000000 or hashlib.sha1(data).hexdigest() != JP_SHA1:
        raise ValueError("Expected exact 32 MiB Japanese decompressed ROM")
    offset = 0x58258 + (54 - 1) * 4
    start = int.from_bytes(data[offset:offset + 4], "big") & 0x7FFFFFFF
    end = int.from_bytes(data[offset + 4:offset + 8], "big") & 0x7FFFFFFF
    if (start, end) != (0x714B90, 0x716020):
        raise ValueError("Japanese overlay 54 file table differs")


def inject(source: str) -> str:
    if HOOK_NAME in source:
        raise ValueError("Callback relocation hook already exists")
    if source.count(FUNC) != 1 or source.count(BODY_START) != 1:
        raise ValueError("Japanese task setup function layout differs")
    start = source.index(FUNC)
    end = source.find("\nRECOMP_FUNC void ", start + len(FUNC))
    if end < 0:
        end = len(source)
    function = source[start:end]
    label = "after_0:\n"
    if function.count(label) != 1 or function.count(
        "func_80001E50_2A50(rdram, ctx);"
    ) != 1:
        raise ValueError("Japanese task TLB setup call/label differs")

    function = function.replace(
        BODY_START,
        "    TRACE_ENTRY()\n    const gpr jp_task = ctx->r4;\n"
        "    // 0x800143AC: addiu       $sp, $sp, -0x18", 1
    )
    function = function.replace(
        label, label + "    jp_relocate_task_callbacks(rdram, ctx, jp_task);\n", 1
    )
    result = source[:start] + HELPER + "\n" + function + source[end:]
    if result.count("jp_relocate_task_callbacks(rdram, ctx, jp_task);") != 1:
        raise ValueError("Task callback injection did not produce one call")
    return result


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--rom", type=Path, required=True)
    cli.add_argument("--source", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--in-place", action="store_true")
    args = cli.parse_args()
    if args.source.resolve() == args.output.resolve() and not args.in_place:
        cli.error("Use --in-place for private generated C")
    try:
        validate_rom(args.rom.read_bytes())
        modified = inject(args.source.read_text())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(modified)
    except (OSError, ValueError) as err:
        cli.error(str(err))
    print(json.dumps({
        "modified_source": str(args.output),
        "japan_rom_sha1": JP_SHA1,
        "task_setup": "0x800143AC",
        "status": "Generated C translated; native gameplay still requires testing",
    }, indent=2))


if __name__ == "__main__":
    main()
