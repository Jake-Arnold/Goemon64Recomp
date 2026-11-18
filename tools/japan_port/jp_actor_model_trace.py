#!/usr/bin/env python3
"""Opt-in source-only actor-to-graphics trace for private Japanese N64Recomp C.

Requires exact 32-MiB Japanese rev-0 decompressed ROM, including instruction
anchors. Does not modify the ROM. Only changes two privately generated C files;
no game assets, memory snapshots, or binaries are committed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

JP_SHA1 = '6f8745fecc3a5e7d4918c7a73353eb0726116ded'
ROM_BYTES = 0x2000000
# Verified with the original region-specific Japanese file_12 Splat VMA.
ACTOR_VMA = 0x8021D7C4
ACTOR_ROM = 0x5D8D54
DRAW_VMA = 0x800167D4
DRAW_ROM = 0x173D4
ACTOR_SIG = 'RECOMP_FUNC void func_8021D7C4_5D8D54(uint8_t* rdram, recomp_context* ctx) {\n'
DRAW_SIG = 'RECOMP_FUNC void func_800167D4_173D4(uint8_t* rdram, recomp_context* ctx) {\n'
MARKER = 'jp_model_trace_register_actor'
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_UNITS = 256

# The function first moves guest a0 into s0; its sh writes are at +0x50/+0x6c.
# Renderer begins with stack frame setup and Object +0x64 flag read.
ROM_ANCHORS = (
    (ACTOR_ROM, bytes.fromhex('27bdffd8 afb00018 00808025 afbf001c')),
    (ACTOR_ROM + 0x44, bytes.fromhex('94580000')),
    (ACTOR_ROM + 0x50, bytes.fromhex('a618005c')),
    (ACTOR_ROM + 0x6C, bytes.fromhex('a609005e')),
    (DRAW_ROM, bytes.fromhex('27bdff90 afbf001c afb00018 908e0064')),
    (DRAW_ROM + 0x84, bytes.fromhex('8e07002c')),
)

# `MEM_W/MEM_H` are the same macros used in existing Japanese native hooks.
# `ctx->r4` is the guest a0 register at entry to both verified functions.
# A bounded list, no dynamic allocation, no background thread and no writes.
HELPER = r'''// jp_model_trace_register_actor: opt-in Japanese NPC graphics research.
// Compiles into the user's *private* generated C, never into the shipped ROM.
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

#define JP_MODEL_TRACE_MAX 256u
struct jp_model_trace_slot {
    uint32_t actor;
    uint32_t object;
    uint32_t gfx;
    uint16_t model;
    uint8_t seen_target;
    uint8_t bound;
};
static struct jp_model_trace_slot jp_model_trace_slots[JP_MODEL_TRACE_MAX];
static unsigned jp_model_trace_cursor;
static unsigned jp_model_trace_used;
static int jp_model_trace_setting = -1;
static int jp_model_trace_loader_seen;
static int jp_model_trace_draw_seen;

static int jp_model_trace_on(void) {
    if (jp_model_trace_setting < 0) {
        const char* option = getenv("GOEMON_JP_ACTOR_TRACE");
        jp_model_trace_setting = option && option[0] == '1' && option[1] == '\0';
    }
    return jp_model_trace_setting;
}

static int jp_model_trace_guest_ok(uint32_t pointer, unsigned bytes) {
    return (pointer & 3u) == 0u && pointer >= 0x80000000u &&
           pointer <= (0x80800000u - bytes);
}

static gpr jp_model_trace_guest(uint32_t pointer) {
    return (gpr)(int64_t)(int32_t)pointer;
}

void jp_model_trace_register_actor(uint8_t* rdram, recomp_context* ctx) {
    (void)rdram;
    if (!jp_model_trace_on()) return;
    if (!jp_model_trace_loader_seen++) {
        fprintf(stderr, "[JP-MODEL] LOADER_ENTRY JP=0x8021D7C4\n");
    }
    const uint32_t pointer = (uint32_t)ctx->r4;
    if (!jp_model_trace_guest_ok(pointer, 0x60u)) return;
    unsigned index;
    for (index = 0; index < jp_model_trace_used; ++index) {
        if (jp_model_trace_slots[index].actor == pointer) break;
    }
    if (index == jp_model_trace_used) {
        if (jp_model_trace_used < JP_MODEL_TRACE_MAX) {
            ++jp_model_trace_used;
        } else {
            index = jp_model_trace_cursor;
            jp_model_trace_cursor = (jp_model_trace_cursor + 1u) % JP_MODEL_TRACE_MAX;
        }
    }
    struct jp_model_trace_slot* slot = &jp_model_trace_slots[index];
    slot->actor = pointer;
    slot->object = 0;
    slot->gfx = 0;
    slot->model = 0;
    slot->seen_target = 0;
    slot->bound = 0;
}

void jp_model_trace_draw_actor(uint8_t* rdram, recomp_context* ctx) {
    if (!jp_model_trace_on()) return;
    if (!jp_model_trace_draw_seen++) {
        fprintf(stderr, "[JP-MODEL] DRAW_ENTRY JP=0x800167D4\n");
    }
    const uint32_t draw_object = (uint32_t)ctx->r4;
    if (!jp_model_trace_guest_ok(draw_object, 0x68u)) return;
    for (unsigned i = 0; i < jp_model_trace_used; ++i) {
        struct jp_model_trace_slot* slot = &jp_model_trace_slots[i];
        if (!jp_model_trace_guest_ok(slot->actor, 0x60u)) continue;
        const gpr actor_addr = jp_model_trace_guest(slot->actor);
        const uint16_t actor_id = (uint16_t)MEM_H(0x5C, actor_addr);
        if (actor_id != 0x00FBu) continue;
        const uint16_t model_id = (uint16_t)MEM_H(0x5E, actor_addr);
        const uint32_t actor_object = (uint32_t)MEM_W(0x18, actor_addr);
        if (!slot->seen_target || slot->object != actor_object || slot->model != model_id) {
            fprintf(stderr, "[JP-MODEL] TARGET_SEEN actor=0x%08X actor_id=0x%04X model_id=0x%04X object=0x%08X\\n",
                    slot->actor, actor_id, model_id, actor_object);
            slot->seen_target = 1;
            slot->object = actor_object;
            slot->model = model_id;
            slot->bound = 0;
        }
        // Equality is the only live actor/Object association claimed here.
        if (actor_object != draw_object) continue;
        const gpr object_addr = jp_model_trace_guest(draw_object);
        const uint32_t gfx1 = (uint32_t)MEM_W(0x2C, object_addr);
        const uint32_t gfx2 = (uint32_t)MEM_W(0x30, object_addr);
        if (slot->bound && slot->gfx == gfx1) continue;
        slot->bound = 1;
        slot->gfx = gfx1;
        fprintf(stderr, "[JP-MODEL] BOUND actor=0x%08X model_id=0x%04X object=0x%08X gfx1=0x%08X gfx2=0x%08X\\n",
                slot->actor, model_id, draw_object, gfx1, gfx2);
        for (unsigned overlay = 0; overlay < 6u; ++overlay) {
            const uint16_t id = (uint16_t)MEM_H(0x34 + 8u * overlay, object_addr);
            const uint32_t base = (uint32_t)MEM_W(0x38 + 8u * overlay, object_addr);
            fprintf(stderr, "[JP-MODEL] OVERLAY slot=%u file_id=0x%04X vram=0x%08X\\n", overlay, id, base);
        }
        fflush(stderr);
    }
}

'''

# The raw C helper has literal two-character backslash-n in its fprintf format
# in source; the compiler interprets these as newlines when run.


def validate_rom(rom: bytes) -> None:
    if len(rom) != ROM_BYTES or hashlib.sha1(rom).hexdigest() != JP_SHA1:
        raise ValueError('requires exact original Japanese rev-0 decompressed 32-MiB ROM')
    for offset, signature in ROM_ANCHORS:
        actual = rom[offset:offset + len(signature)]
        if actual != signature:
            raise ValueError(f'Japanese instruction mismatch at ROM 0x{offset:X}')


def find_targets(folder: Path) -> tuple[Path, Path]:
    if not folder.is_dir():
        raise ValueError('generated-dir does not exist')
    candidates = sorted(folder.glob('funcs_*.c'))
    if not candidates or len(candidates) > MAX_UNITS:
        raise ValueError('expected 1..256 generated C units named funcs_*.c')
    found = {ACTOR_SIG: [], DRAW_SIG: []}
    for path in candidates:
        if not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError('generated C unit is not a regular bounded source file')
        source = path.read_text(encoding='utf-8')
        for signature in found:
            count = source.count(signature)
            if count:
                found[signature].extend([path] * count)
    for signature, paths in found.items():
        if len(paths) != 1:
            raise ValueError(f'expected one generated function {signature.split("(")[0]}, found {len(paths)}')
    return found[ACTOR_SIG][0], found[DRAW_SIG][0]


def transform(actor_source: str, draw_source: str) -> tuple[str, str]:
    if MARKER in actor_source or MARKER in draw_source or 'jp_model_trace_draw_actor' in draw_source:
        raise ValueError('Japanese actor model trace already applied')
    if actor_source.count(ACTOR_SIG) != 1 or draw_source.count(DRAW_SIG) != 1:
        raise ValueError('missing or ambiguous generated C function signature')
    if '#include "recomp.h"\n' not in actor_source or '#include "recomp.h"\n' not in draw_source:
        raise ValueError('expected original generated N64Recomp includes')
    if actor_source is draw_source or actor_source == draw_source:
        # `apply` coalesces same-file cases; this is the strict replacement path.
        source = actor_source.replace(ACTOR_SIG, HELPER + ACTOR_SIG +
                                      '    jp_model_trace_register_actor(rdram, ctx);\n', 1)
        # Ensure declaration is visible even if renderer precedes initializer.
        source = source.replace('#include "recomp.h"\n',
             '#include "recomp.h"\nextern void jp_model_trace_draw_actor(uint8_t*, recomp_context*);\n', 1)
        source = source.replace(DRAW_SIG, DRAW_SIG +
             '    jp_model_trace_draw_actor(rdram, ctx);\n', 1)
        return source, source
    changed_actor = actor_source.replace(ACTOR_SIG, HELPER + ACTOR_SIG +
                                         '    jp_model_trace_register_actor(rdram, ctx);\n', 1)
    changed_draw = draw_source.replace('#include "recomp.h"\n',
                '#include "recomp.h"\nextern void jp_model_trace_draw_actor(uint8_t*, recomp_context*);\n', 1)
    changed_draw = changed_draw.replace(DRAW_SIG, DRAW_SIG +
                                        '    jp_model_trace_draw_actor(rdram, ctx);\n', 1)
    return changed_actor, changed_draw


def apply(generated: Path, rom: Path) -> dict:
    validate_rom(rom.read_bytes())
    actor_file, draw_file = find_targets(generated)
    actor_source = actor_file.read_text(encoding='utf-8')
    draw_source = draw_file.read_text(encoding='utf-8')
    changed_actor, changed_draw = transform(actor_source, draw_source)
    # All checks and changes staged before any source file is overwritten.
    actor_file.write_text(changed_actor, encoding='utf-8')
    if draw_file != actor_file:
        draw_file.write_text(changed_draw, encoding='utf-8')
    return {'actor_source': str(actor_file), 'renderer_source': str(draw_file),
            'filter_actor_id': '0x00FB', 'runtime_flag': 'GOEMON_JP_ACTOR_TRACE=1',
            'status': 'source-only instrumented (compile and live gameplay NOT verified)'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--generated-dir', type=Path, required=True)
    p.add_argument('--confirm-modify-private-generated-c', action='store_true',
                   help='explicitly permit editing the ignored generated source files')
    args = p.parse_args()
    if not args.confirm_modify_private_generated_c:
        p.error('use --confirm-modify-private-generated-c to modify private generated source')
    try:
        output = apply(args.generated_dir, args.rom)
    except (OSError, ValueError) as error:
        p.error(str(error))
    for key, value in output.items():
        print(f'{key}: {value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())