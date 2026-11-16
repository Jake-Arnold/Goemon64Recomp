#!/usr/bin/env python3
"""Fix the JP Sasuke bomb camera argument in private N64Recomp C output.

On Yamato scene 307 bomb detonation, a stale physical/segmented 0x202119E0
argument reaches func_8000FBDC_107DC and crashes at MEM_W(ctx->r5).
The corresponding USA routine already has a direct camera-address patch.
The Japanese counterpart is proven by exact ROM bytes and the live GDB
call stack, not by assuming USA addresses also work in Japan.

Only modifies build-generated/japan/RecompiledFuncs/funcs_32.c after
verifying the complete decompressed Japanese ROM and unique callsite.
Neither original ROM nor USA game code is modified.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

JP_SHA1 = "6f8745fecc3a5e7d4918c7a73353eb0726116ded"
ROM_SIZE = 0x2000000
FUNC = "func_801F0FB0_5ACF80"
CALLEE = "func_8000F1E0_FDE0"
JP_CAMERA = 0x802119E0
MARKER = "jp_sasuke_bomb_camera_fix"
# Original JP MIPS: jal func_8000F1E0 ; delay slot lw a1, 0x2C(t7).
# USA counterpart: ROM 0x5A8158 jal func_8000F420 ; 0x5A815C same lw.
ROM_EXPECTED = {
    0x5ACF80: bytes.fromhex(
        "27BDFF20 AFBF003C AFB20038 AFB10034 AFB00030 AFA500E4 "
        "AFA600E8 AFA700EC 8C900018 8C83005C 00808825 8E0E0000 "
        "8C720018 8DCF0000"
    ),
    0x5AD280: bytes.fromhex("0C003C78 8DE5002C"),
    # Independent direct JP camera pointer already used by bomb logic.
    0x5ADE24: bytes.fromhex("3C058021 24A519E0"),
    # Another independent direct use of the JP camera object.
    0x5D17B4: bytes.fromhex("3C058021 24A519E0"),
}

FUNCTION_HEADER = (
    "RECOMP_FUNC void func_801F0FB0_5ACF80(uint8_t* rdram, "
    "recomp_context* ctx) {"
)
NEXT_FUNCTION = "\nRECOMP_FUNC void "
LOAD = re.compile(
    r"ctx->r5\s*=\s*MEM_W\(\s*ctx->r15\s*,\s*0[xX]0*2[cC]\s*\)\s*;"
)
CALL = re.compile(r"\bfunc_8000F1E0_FDE0\s*\(\s*rdram\s*,\s*ctx\s*\)\s*;")
PATCH_LINE = "ctx->r5 = (gpr)(int64_t)(int32_t)0x802119E0u;"


def validate_rom(data: bytes) -> None:
    if len(data) != ROM_SIZE or hashlib.sha1(data).hexdigest() != JP_SHA1:
        raise ValueError("Expected exact 32 MiB Japanese decompressed ROM SHA-1")
    for at, expected in ROM_EXPECTED.items():
        actual = data[at:at + len(expected)]
        if actual != expected:
            raise ValueError(
                f"Japanese Sasuke camera code changed at ROM 0x{at:06X}"
            )


def find_function(source: str) -> tuple[int, int]:
    if source.count(FUNCTION_HEADER) != 1:
        raise ValueError("Missing or duplicate Japanese Sasuke bomb function header")
    start = source.index(FUNCTION_HEADER)
    end = source.find(NEXT_FUNCTION, start + len(FUNCTION_HEADER))
    if end < 0:
        raise ValueError("Missing end of Japanese Sasuke bomb function")
    return start, end


def inject(source: str) -> str:
    if '#include "recomp.h"' not in source:
        raise ValueError("Not a generated N64Recomp C file")
    start, end = find_function(source)
    body = source[start:end]
    if MARKER in source:
        # Repeated builds must not accept a marker that was moved away from
        # the exact camera call, or a partial edit to the original delay slot.
        calls = list(CALL.finditer(body))
        loads = list(LOAD.finditer(body))
        marker_at = body.find(MARKER)
        patch_at = body.find(PATCH_LINE)
        if (source.count(MARKER) == 1 and body.count(PATCH_LINE) == 1
                and len(calls) == 1 and len(loads) >= 1
                and loads[-1].end() < marker_at < patch_at < calls[0].start()
                and calls[0].start() - patch_at < 250):
            return source  # Exact patch still at its verified location.
        raise ValueError("Malformed or duplicated Sasuke bomb camera patch")
    if PATCH_LINE in source:
        raise ValueError("Camera fix already applied without verified marker")
    calls = list(CALL.finditer(body))
    if len(calls) != 1:
        raise ValueError("Expected exactly one Japanese camera call in bomb function")
    call = calls[0]
    # In N64Recomp the MIPS jal delay-slot load is emitted immediately before
    # the C call; check it to reject changed/incompatible generated layouts.
    prefix = body[max(0, call.start() - 500):call.start()]
    matches = list(LOAD.finditer(prefix))
    if len(matches) != 1:
        raise ValueError("Cannot verify expected lw a1, 0x2C(t7) before camera call")
    if prefix[ matches[0].end(): ].count("\n") > 10:
        raise ValueError("Camera argument load is too far from patched call")
    line_start = body.rfind("\n", 0, call.start()) + 1
    indent = re.match(r"[ \t]*", body[line_start:]).group(0)
    # Keep the original load and replace only the *argument* immediately
    # before the verified camera callee, equivalent to the USA patch.
    # Sign-extension matches a MIPS KSEG0 pointer while leaving registers
    # and other explosion effects unchanged.
    insertion = (
        f"{indent}// {MARKER}: JP direct camera object; USA equivalent"
        " D_8020CBF0.\n"
        f"{indent}{PATCH_LINE}\n"
    )
    patched = source[:start + line_start] + insertion + source[start + line_start:]
    pstart, pend = find_function(patched)
    if patched[pstart:pend].count(PATCH_LINE) != 1:
        raise ValueError("Sasuke bomb camera callsite was not patched uniquely")
    return patched


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() and not args.in_place:
        parser.error("Use --in-place for existing private generated C files")
    try:
        validate_rom(args.rom.read_bytes())
        original = args.source.read_text(encoding="utf-8")
        updated = inject(original)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not args.output.exists() or (
            args.output.resolve() != args.source.resolve() or updated != original
        ):
            args.output.write_text(updated, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        "[JP Sasuke camera] "
        + ("Unchanged (already patched)" if updated == original else "Patched")
        + f": {args.output} (function {FUNC}, camera 0x{JP_CAMERA:08X})"
    )


if __name__ == "__main__":
    main()
