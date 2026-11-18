#!/usr/bin/env python3
"""Bounded read-only guest Gfx word capture: upgrade an exact Japanese v2 trace.

The user's private generated C is already instrumented with v2. Only the v2
actor-side helper is modified; the renderer wrapper and original code remain
unchanged. Verifies original Japanese ROM and the exact v2 helper bytes.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

JP_SHA1 = '6f8745fecc3a5e7d4918c7a73353eb0726116ded'
ROM_SIZE = 0x2000000
ACTOR_SIG = 'RECOMP_FUNC void func_8021D7C4_5D8D54(uint8_t* rdram, recomp_context* ctx) {\n'
DRAW_SIG = 'RECOMP_FUNC void func_800167D4_173D4(uint8_t* rdram, recomp_context* ctx) {\n'
V2_MARKER = '// jp_model_trace_v2_register_actor: read-only, bounded JP actor/GBI research.\n'
V3_MARKER = '// JP_MODEL_TRACE_V3_GFX_DUMP (exact-v2 read-only augmentation)'
V2_HELPER_SHA256 = '352d3d05117bfb9278ad0315cc551ecf08058a0f5faf61bb08bdcd043f0bb1cc'
V2_CALL = '    jp_model_trace_v2_register_actor(rdram, ctx);\n'
V2_DRAW_WRAPPER = '    jp_model_trace_v2_end(rdram, &frame);\n'
COUNT_ANCHOR = '    const uint32_t count = (end - start) / 8u;\n'
ROM_ANCHORS = (
    (0x5D8D54, bytes.fromhex('27bdffd8 afb00018 00808025 afbf001c')),
    (0x5D8D98, bytes.fromhex('94580000')),
    (0x5D8DA4, bytes.fromhex('a618005c')),
    (0x5D8DC0, bytes.fromhex('a609005e')),
    (0x173D4, bytes.fromhex('27bdff90 afbf001c afb00018 908e0064')),
    (0x17458, bytes.fromhex('8e07002c')),
    (0x17BBC, bytes.fromhex('244c0008')),
)
MAX_UNITS = 256
MAX_SOURCE = 64 * 1024 * 1024

# Only the first two nonempty Gfx windows with <=64 commands per mode are
# dumped. This covers the observed 55-command and 8-command native windows.
# No guest memory writes, malloc, pointers followed, GPU hooks, or threads.
V3_DUMP = r'''    // JP_MODEL_TRACE_V3_GFX_DUMP (exact-v2 read-only augmentation)
    // Two bounded samples per mode; do not infer RT64/RSP submission.
    if (count && count <= 64u && (frame->mode == 1u || frame->mode == 4u)) {
        static unsigned jp_v3_samples_mode1;
        static unsigned jp_v3_samples_mode4;
        unsigned* quota = frame->mode == 1u ? &jp_v3_samples_mode1 : &jp_v3_samples_mode4;
        if (*quota < 2u) {
            const unsigned sample = ++*quota;
            fprintf(stderr, "[JP-MODEL3] BEGIN actor=0x%08X gen=%u model=0x%04X mode=%u sample=%u source=0x%08X start=0x%08X end=0x%08X commands=%u\n",
                    frame->actor, frame->generation, frame->model, frame->mode,
                    sample, frame->source, start, end, count);
            for (uint32_t j = 0; j < count; ++j) {
                const uint32_t w0 = jp_v2_read(rdram, start + 8u * j);
                const uint32_t w1 = jp_v2_read(rdram, start + 8u * j + 4u);
                fprintf(stderr, "[JP-MODEL3] CMD mode=%u sample=%u index=%u w0=%08X w1=%08X\n",
                        frame->mode, sample, j, w0, w1);
            }
            fprintf(stderr, "[JP-MODEL3] END mode=%u sample=%u commands=%u\n",
                    frame->mode, sample, count);
            fflush(stderr);
        }
    }
'''


def validate_rom(rom: bytes) -> None:
    if len(rom) != ROM_SIZE or hashlib.sha1(rom).hexdigest() != JP_SHA1:
        raise ValueError('requires exact original Japanese 32 MiB decompressed ROM')
    for offset, expected in ROM_ANCHORS:
        if rom[offset:offset + len(expected)] != expected:
            raise ValueError(f'original Japanese opcode anchor differs at ROM 0x{offset:X}')


def find_sources(folder: Path) -> tuple[Path, Path]:
    if not folder.is_dir():
        raise ValueError('generated directory missing')
    files = sorted(folder.glob('funcs_*.c'))
    if not files or len(files) > MAX_UNITS:
        raise ValueError('generated sources expected (1..256 funcs_*.c)')
    actor, draw = [], []
    for path in files:
        if not path.is_file() or path.stat().st_size > MAX_SOURCE:
            raise ValueError('unreadable or excessive generated source')
        text = path.read_text(encoding='utf-8')
        actor.extend([path] * text.count(ACTOR_SIG))
        draw.extend([path] * text.count(DRAW_SIG))
    if len(actor) != 1 or len(draw) != 1 or actor[0] == draw[0]:
        raise ValueError(f'exact separate actor/renderer units required: actor={len(actor)} renderer={len(draw)}')
    return actor[0], draw[0]


def upgrade_sources(actor: str, renderer: str) -> tuple[str, str]:
    if V3_MARKER in actor or V3_MARKER in renderer:
        raise ValueError('v3 Gfx dump already installed')
    if actor.count(ACTOR_SIG) != 1 or renderer.count(DRAW_SIG) != 1:
        raise ValueError('unique original function signatures missing')
    if actor.count(V2_MARKER) != 1 or actor.count(V2_CALL) != 1:
        raise ValueError('expected v2 actor helper and entry call missing')
    if renderer.count(V2_DRAW_WRAPPER) != 1 or renderer.count('jp_model_trace_v2_original_draw') != 3:
        raise ValueError('renderer is not the exact v2 wrapper')
    begin = actor.index(V2_MARKER)
    end = actor.index(ACTOR_SIG, begin)
    helper = actor[begin:end]
    if hashlib.sha256(helper.encode('utf-8')).hexdigest() != V2_HELPER_SHA256:
        raise ValueError('modified v2 helper; refusing unreviewed upgrade')
    if helper.count(COUNT_ANCHOR) != 1:
        raise ValueError('missing unique v2 Gfx count anchor')
    new_helper = helper.replace(COUNT_ANCHOR, COUNT_ANCHOR + V3_DUMP, 1)
    updated = actor[:begin] + new_helper + actor[end:]
    if updated.count(V3_MARKER) != 1 or updated.count('jp_model_trace_v2_register_actor') < 2:
        raise ValueError('failed to stage exact v3 helper')
    return updated, renderer


def upgrade(folder: Path, rom_file: Path, dry_run: bool) -> dict:
    validate_rom(rom_file.read_bytes())
    actor_file, draw_file = find_sources(folder)
    actor_text = actor_file.read_text(encoding='utf-8')
    draw_text = draw_file.read_text(encoding='utf-8')
    new_actor, new_draw = upgrade_sources(actor_text, draw_text)
    if new_draw != draw_text:
        raise ValueError('v3 must never modify renderer source')
    backup = actor_file.with_name(actor_file.name + '.pre-model-trace-v3')
    if not dry_run:
        if backup.exists():
            raise ValueError('backup already exists; refusing to overwrite')
        shutil.copy2(actor_file, backup)
        fd, temporary = tempfile.mkstemp(prefix='.jp_actor_model_v3_', suffix='.tmp', dir=actor_file.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as out:
                out.write(new_actor)
            os.replace(temporary, actor_file)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {'actor_source': str(actor_file), 'renderer_unchanged': str(draw_file),
            'backup': str(backup),
            'mode': 'validated only' if dry_run else 'read-only v3 Gfx words installed',
            'rom': 'sha1 plus seven original instruction anchors PASS',
            'runtime': 'not verified until rebuild and user gameplay'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--generated-dir', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true')
    mode.add_argument('--confirm-upgrade-private-generated-c', action='store_true')
    args = parser.parse_args()
    try:
        outcome = upgrade(args.generated_dir, args.rom, args.dry_run)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    for key, value in outcome.items():
        print(f'{key}: {value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())