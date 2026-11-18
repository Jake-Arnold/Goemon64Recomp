#!/usr/bin/env python3
"""Upgrade exactly the first read-only JP native tracer to generation + Gfx-window v2.

The user's private generated C is already instrumented by v1. This script
verifies the original exact v1 code before replacing it; it never touches ROMs,
shipped game sources, object files, or any other generated function.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

JP_SHA1 = '6f8745fecc3a5e7d4918c7a73353eb0726116ded'
ROM_LENGTH = 0x2000000
ACTOR_SIG = 'RECOMP_FUNC void func_8021D7C4_5D8D54(uint8_t* rdram, recomp_context* ctx) {\n'
DRAW_SIG = 'RECOMP_FUNC void func_800167D4_173D4(uint8_t* rdram, recomp_context* ctx) {\n'
V1_MARKER = '// jp_model_trace_register_actor: opt-in Japanese NPC graphics research.\n'
V2_MARKER = 'jp_model_trace_v2_register_actor'
V1_HELPER_SHA256 = 'c04c72af2c20ffbdd4864e33b0ffdc00eb71ad57a29f812655e574881ff49a9f'
V1_LOADER_CALL = '    jp_model_trace_register_actor(rdram, ctx);\n'
V1_DRAW_CALL = '    jp_model_trace_draw_actor(rdram, ctx);\n'
V1_DRAW_EXTERN = 'extern void jp_model_trace_draw_actor(uint8_t*, recomp_context*);\n'
GFX_TAIL_VMA = 0x80161DBC  # original JP 0x80016FBC/0x8001990C writes through this global
ROM_ANCHORS = (
    (0x5D8D54, bytes.fromhex('27bdffd8 afb00018 00808025 afbf001c')),
    (0x5D8D98, bytes.fromhex('94580000')),
    (0x5D8DA4, bytes.fromhex('a618005c')),
    (0x5D8DC0, bytes.fromhex('a609005e')),
    (0x173D4, bytes.fromhex('27bdff90 afbf001c afb00018 908e0064')),
    (0x17458, bytes.fromhex('8e07002c')),
    (0x17BBC, bytes.fromhex('244c0008')),  # 0x80016FBC: pointer increment before store
)
MAX_UNITS = 256
MAX_SOURCE_BYTES = 64 * 1024 * 1024

# This structure is deliberately shared by the two private C translation units.
# Individual call-local windows avoid nested-function/global-context confusion.
FRAME_TYPE = r'''struct jp_model_trace_v2_frame {
    uint32_t actor, object, generation, model, mode, source, gfx_begin, valid;
};
'''

HELPER = r'''// jp_model_trace_v2_register_actor: read-only, bounded JP actor/GBI research.
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define JP_V2_SLOTS 256u
#define JP_V2_MAX_GFX_COMMANDS 256u
#define JP_V2_MAX_WINDOWS 6u
struct jp_model_trace_v2_frame {
    uint32_t actor, object, generation, model, mode, source, gfx_begin, valid;
};
struct jp_v2_slot {
    uint32_t actor, generation, object, source;
    uint16_t model;
    uint8_t seen, windows;
};
static struct jp_v2_slot jp_v2_slots[JP_V2_SLOTS];
static uint32_t jp_v2_count, jp_v2_eviction, jp_v2_sequence;
static int jp_v2_enabled_state = -1;
static int jp_v2_loader_logged, jp_v2_draw_logged;

static int jp_v2_enabled(void) {
    if (jp_v2_enabled_state == -1) {
        const char* value = getenv("GOEMON_JP_ACTOR_TRACE");
        jp_v2_enabled_state = value && value[0] == '1' && value[1] == '\0';
    }
    return jp_v2_enabled_state;
}
static int jp_v2_valid(uint32_t addr, uint32_t bytes) {
    const uint32_t canon = (addr & 0x1FFFFFFFu);
    const uint32_t segment = addr & 0xE0000000u;
    return (segment == 0x80000000u || segment == 0xA0000000u) &&
           (addr & 3u) == 0u && bytes != 0 && canon <= 0x800000u - bytes;
}
static gpr jp_v2_addr(uint32_t addr) {
    return (gpr)(int64_t)(int32_t)addr;
}
static uint32_t jp_v2_read(uint8_t* rdram, uint32_t addr) {
    return (uint32_t)MEM_W(0, jp_v2_addr(addr));
}

void jp_model_trace_v2_register_actor(uint8_t* rdram, recomp_context* ctx) {
    (void)rdram;
    if (!jp_v2_enabled()) return;
    if (!jp_v2_loader_logged++) fprintf(stderr, "[JP-MODEL2] LOADER JP=0x8021D7C4\n");
    const uint32_t actor = (uint32_t)ctx->r4;
    if (!jp_v2_valid(actor, 0x60u)) return;
    uint32_t i;
    for (i = 0; i < jp_v2_count; i++) {
        if (jp_v2_slots[i].actor == actor) break;
    }
    if (i == jp_v2_count) {
        if (jp_v2_count < JP_V2_SLOTS) ++jp_v2_count;
        else { i = jp_v2_eviction; jp_v2_eviction = (jp_v2_eviction + 1u) % JP_V2_SLOTS; }
    } else if (jp_v2_slots[i].seen) {
        fprintf(stderr, "[JP-MODEL2] REINIT actor=0x%08X previous_gen=%u previous_model=0x%04X\n",
                actor, jp_v2_slots[i].generation, jp_v2_slots[i].model);
    }
    struct jp_v2_slot* slot = &jp_v2_slots[i];
    slot->actor = actor;
    slot->generation = ++jp_v2_sequence;
    slot->object = slot->source = 0;
    slot->model = 0;
    slot->seen = slot->windows = 0;
}

// Model source address uses original game 0x80016968/0x80017010
// segmented source translator, not a guessed RT64 display-list root.
static uint32_t jp_v2_source(uint8_t* rdram, uint32_t object, uint32_t gfx, uint32_t* segment) {
    const uint32_t ptr = gfx & 0x8FFFFFFEu;
    *segment = 0xFFu;
    if (jp_v2_valid(ptr, 8u)) return ptr;
    if (ptr == 0 || (ptr & 0x80000000u) || !jp_v2_valid(object, 0x64u)) return 0;
    if (ptr >= 0x08000001u) {
        const uint32_t seg = (ptr >> 24u) & 0xFu;
        if (seg < 8u || seg > 13u) return 0;
        const uint32_t offset = 0x38u + 8u * (seg - 8u);
        const uint32_t base = jp_v2_read(rdram, object + offset);
        const uint32_t source = base + (ptr & 0xFFFFFFu);
        if (source < base || !jp_v2_valid(source, 8u)) return 0;
        *segment = seg;
        return source;
    }
    const uint32_t base = jp_v2_read(rdram, object + 0x38u);
    const uint32_t source = base + ptr;
    if (source < base || !jp_v2_valid(source, 8u)) return 0;
    *segment = 0;
    return source;
}

void jp_model_trace_v2_begin(uint8_t* rdram, recomp_context* ctx,
                             struct jp_model_trace_v2_frame* frame) {
    frame->valid = 0;
    if (!jp_v2_enabled()) return;
    if (!jp_v2_draw_logged++) fprintf(stderr, "[JP-MODEL2] DRAW JP=0x800167D4\n");
    const uint32_t draw_object = (uint32_t)ctx->r4;
    if (!jp_v2_valid(draw_object, 0x64u)) return;
    struct jp_v2_slot* found = NULL;
    for (uint32_t i = 0; i < jp_v2_count; i++) {
        struct jp_v2_slot* slot = &jp_v2_slots[i];
        if (!jp_v2_valid(slot->actor, 0x60u)) continue;
        const gpr a = jp_v2_addr(slot->actor);
        const uint16_t actor_id = (uint16_t)MEM_H(0x5Cu, a);
        if (actor_id != 0xFBu) continue;
        const uint16_t model = (uint16_t)MEM_H(0x5Eu, a);
        const uint32_t object = (uint32_t)MEM_W(0x18u, a);
        if (!slot->seen) {
            fprintf(stderr, "[JP-MODEL2] TARGET actor=0x%08X gen=%u model=0x%04X object=0x%08X\n",
                    slot->actor, slot->generation, model, object);
            slot->seen = 1;
            slot->model = model;
            slot->object = object;
        } else if (slot->model != model || slot->object != object) {
            fprintf(stderr, "[JP-MODEL2] STATE_CHANGE actor=0x%08X gen=%u model=0x%04X->0x%04X object=0x%08X->0x%08X\n",
                    slot->actor, slot->generation, slot->model, model, slot->object, object);
            slot->model = model;
            slot->object = object;
            slot->windows = 0;
            slot->source = 0;
        }
        if (object == draw_object) {
            if (found) {
                fprintf(stderr, "[JP-MODEL2] AMBIGUOUS_OBJECT object=0x%08X\n", draw_object);
                return;
            }
            found = slot;
        }
    }
    if (!found) return;
    const uint32_t gfx = jp_v2_read(rdram, draw_object + 0x2Cu);
    const uint32_t gfx2 = jp_v2_read(rdram, draw_object + 0x30u);
    const uint32_t mode = (gfx >> 28u) & 7u;
    uint32_t segment = 0;
    const uint32_t source = jp_v2_source(rdram, draw_object, gfx, &segment);
    if (source != found->source) {
        found->source = source;
        found->windows = 0;
        fprintf(stderr, "[JP-MODEL2] SOURCE actor=0x%08X gen=%u model=0x%04X mode=%u gfx1=0x%08X gfx2=0x%08X seg=%u address=0x%08X",
                found->actor, found->generation, found->model, mode, gfx, gfx2, segment, source);
        if (source) fprintf(stderr, " words=%08X,%08X", jp_v2_read(rdram, source), jp_v2_read(rdram, source + 4u));
        fprintf(stderr, "\n");
    }
    if (found->windows >= JP_V2_MAX_WINDOWS) return;
    const uint32_t start = jp_v2_read(rdram, 0x80161DBCu);
    frame->actor = found->actor;
    frame->object = draw_object;
    frame->generation = found->generation;
    frame->model = found->model;
    frame->mode = mode;
    frame->source = source;
    frame->gfx_begin = start;
    frame->valid = 1;
    ++found->windows;
}

void jp_model_trace_v2_end(uint8_t* rdram, const struct jp_model_trace_v2_frame* frame) {
    if (!frame->valid) return;
    const uint32_t start = frame->gfx_begin;
    const uint32_t end = jp_v2_read(rdram, 0x80161DBCu);
    if (!jp_v2_valid(start, 8u) || !jp_v2_valid(end, 8u) ||
        (start >> 29u) != (end >> 29u) || end < start ||
        (end - start) > JP_V2_MAX_GFX_COMMANDS * 8u || ((end - start) & 7u)) {
        fprintf(stderr, "[JP-MODEL2] GFX_WINDOW_UNAVAILABLE actor=0x%08X gen=%u start=0x%08X end=0x%08X\n",
                frame->actor, frame->generation, start, end);
        return;
    }
    const uint32_t count = (end - start) / 8u;
    uint32_t digest = 2166136261u; // FNV-1a over actual command bytes
    uint32_t op06 = 0, opDE = 0, op01 = 0, opDA = 0;
    for (uint32_t i = 0; i < count; i++) {
        const uint32_t w0 = jp_v2_read(rdram, start + 8u * i);
        const uint32_t w1 = jp_v2_read(rdram, start + 8u * i + 4u);
        const uint32_t op = w0 >> 24u;
        op06 += op == 0x06u; opDE += op == 0xDEu;
        op01 += op == 0x01u; opDA += op == 0xDAu;
        for (unsigned j = 0; j < 8u; j++) {
            const uint32_t w = j < 4u ? w0 : w1;
            const uint8_t b = (uint8_t)(w >> (24u - 8u * (j % 4u)));
            digest = (digest ^ b) * 16777619u;
        }
    }
    fprintf(stderr, "[JP-MODEL2] GFX_WINDOW actor=0x%08X gen=%u model=0x%04X mode=%u source=0x%08X commands=%u fnv32=%08X op06=%u opDE=%u op01=%u opDA=%u\n",
            frame->actor, frame->generation, frame->model, frame->mode,
            frame->source, count, digest, op06, opDE, op01, opDA);
}

'''

# The wrapper is an isolated host-C boundary around the *same* recompiled
# dispatcher. It never intercepts CPU or RSP execution via emulator hooks.
DRAW_DECL = FRAME_TYPE + '''extern void jp_model_trace_v2_begin(uint8_t*, recomp_context*, struct jp_model_trace_v2_frame*);
extern void jp_model_trace_v2_end(uint8_t*, const struct jp_model_trace_v2_frame*);
'''
DRAW_WRAPPER = '''RECOMP_FUNC void jp_model_trace_v2_original_draw(uint8_t* rdram, recomp_context* ctx);
RECOMP_FUNC void func_800167D4_173D4(uint8_t* rdram, recomp_context* ctx) {
    struct jp_model_trace_v2_frame frame = {0};
    jp_model_trace_v2_begin(rdram, ctx, &frame);
    jp_model_trace_v2_original_draw(rdram, ctx);
    jp_model_trace_v2_end(rdram, &frame);
}
RECOMP_FUNC void jp_model_trace_v2_original_draw(uint8_t* rdram, recomp_context* ctx) {
'''


def validate_rom(data: bytes) -> None:
    if len(data) != ROM_LENGTH or hashlib.sha1(data).hexdigest() != JP_SHA1:
        raise ValueError('requires exact 32-MiB decompressed original Japanese ROM')
    for offset, expected in ROM_ANCHORS:
        if data[offset:offset + len(expected)] != expected:
            raise ValueError(f'Japanese MIPS instruction drift at ROM 0x{offset:X}')


def find_targets(folder: Path) -> tuple[Path, Path]:
    if not folder.is_dir():
        raise ValueError('missing private generated dir')
    files = sorted(folder.glob('funcs_*.c'))
    if not files or len(files) > MAX_UNITS:
        raise ValueError('expected 1..256 private generated C units')
    found = {ACTOR_SIG: [], DRAW_SIG: []}
    for f in files:
        if not f.is_file() or f.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError('source too large or not regular file')
        source = f.read_text(encoding='utf-8')
        for signature in found:
            if signature in source:
                found[signature].extend([f] * source.count(signature))
    for signature, matches in found.items():
        if len(matches) != 1:
            raise ValueError(f'missing/duplicated private generated function: {signature} (found {len(matches)})')
    if found[ACTOR_SIG][0] == found[DRAW_SIG][0]:
        raise ValueError('v2 upgrade deliberately requires the user-verified two C units')
    return found[ACTOR_SIG][0], found[DRAW_SIG][0]


def upgrade_sources(actor: str, renderer: str) -> tuple[str, str]:
    if V2_MARKER in actor or 'jp_model_trace_v2_original_draw' in renderer:
        raise ValueError('v2 already installed')
    if actor.count(ACTOR_SIG) != 1 or renderer.count(DRAW_SIG) != 1:
        raise ValueError('unexpected compiled function signatures')
    if actor.count(V1_MARKER) != 1 or actor.count(V1_LOADER_CALL) != 1:
        raise ValueError('v1 actor instrumentation not found uniquely')
    if renderer.count(V1_DRAW_CALL) != 1 or renderer.count(V1_DRAW_EXTERN) != 1:
        raise ValueError('v1 renderer instrumentation not found uniquely')
    begin = actor.index(V1_MARKER)
    end = actor.index(ACTOR_SIG)
    old_helper = actor[begin:end]
    if hashlib.sha256(old_helper.encode()).hexdigest() != V1_HELPER_SHA256:
        raise ValueError('v1 actor helper differs: refusing unreviewed replacement')
    actor = actor[:begin] + HELPER + actor[end:]
    actor = actor.replace(ACTOR_SIG + V1_LOADER_CALL,
                          ACTOR_SIG + '    jp_model_trace_v2_register_actor(rdram, ctx);\n', 1)
    renderer = renderer.replace(V1_DRAW_EXTERN, DRAW_DECL, 1)
    renderer = renderer.replace(DRAW_SIG + V1_DRAW_CALL, DRAW_WRAPPER, 1)
    if actor.count(V2_MARKER) < 2 or renderer.count('jp_model_trace_v2_original_draw') != 3:
        raise ValueError('v2 staging assertions failed')
    return actor, renderer


def upgrade(generated: Path, rom: Path, dry_run: bool) -> dict:
    validate_rom(rom.read_bytes())
    actor_file, draw_file = find_targets(generated)
    source_a = actor_file.read_text(encoding='utf-8')
    source_d = draw_file.read_text(encoding='utf-8')
    changed_a, changed_d = upgrade_sources(source_a, source_d)
    if not dry_run:
        actor_file.write_text(changed_a, encoding='utf-8')
        draw_file.write_text(changed_d, encoding='utf-8')
    return {
        'actor_file': str(actor_file), 'draw_file': str(draw_file),
        'rom': 'SHA-1 and seven original opcode anchors PASS',
        'mode': 'validated only' if dry_run else 'v1 upgraded in private generated C',
        'runtime_enable': 'GOEMON_JP_ACTOR_TRACE=1',
        'live_native_gameplay': 'NOT RUN',
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--generated-dir', type=Path, required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--confirm-upgrade-private-generated-c', action='store_true')
    a = p.parse_args()
    try:
        result = upgrade(a.generated_dir, a.rom, a.dry_run)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    for key, value in result.items():
        print(f'{key}: {value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())