#!/usr/bin/env python3
"""Guarded Japanese file 80 overlay data pointer relocation for scene 129.

Only six ROM-validated table pointers are rewritten in the live loaded
file 80 overlay. Source-only change to private generated funcs_8.c; no
ROM bytes or generated game code belong in Git.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

JP_SHA1 = '6f8745fecc3a5e7d4918c7a73353eb0726116ded'
FILE_ID = 80
ROM_START, ROM_END, ROM_DATA_START = 0x741660, 0x742270, 0x741F50
ROM_SIZE = ROM_END - ROM_START
SITE_TARGETS = (
    (0x0B3C, 0x08F0),
    (0x0B40, 0x0920),
    (0x0B44, 0x0974),
    (0x0B48, 0x09B0),
    (0x0B4C, 0x0A28),
    (0x0B50, 0x0A94),
)
MARKER = 'jp_relocate_file_80_data'
BEFORE = 'static void jp_relocate_file_56_data(uint8_t* rdram, uint32_t base) {'
AFTER = '        jp_relocate_file_56_data(rdram, base);\n    }\n'


def validate_rom(data: bytes) -> None:
    if len(data) != 0x2000000 or hashlib.sha1(data).hexdigest() != JP_SHA1:
        raise ValueError('Wrong Japanese decompressed ROM hash or size')
    table = 0x58258 + 4 * (FILE_ID - 1)
    start = int.from_bytes(data[table:table + 4], 'big') & 0x7FFFFFFF
    end = int.from_bytes(data[table + 4:table + 8], 'big') & 0x7FFFFFFF
    if (start, end) != (ROM_START, ROM_END) or not start <= ROM_DATA_START <= end:
        raise ValueError('Japanese file 80 file table or data boundary differs')
    found = {}
    for offset in range(ROM_DATA_START - start, ROM_SIZE, 4):
        value = int.from_bytes(data[start + offset:start + offset + 4], 'big')
        if 0x08000000 <= value < 0x08000000 + ROM_SIZE:
            found[offset] = value - 0x08000000
    if found != dict(SITE_TARGETS):
        raise ValueError('Japanese file 80 pointer inventory differs')


def hook_text() -> str:
    pairs = '\n'.join(
        f'        {{0x{site:04X}u, 0x{target:04X}u}},'
        for site, target in SITE_TARGETS
    )
    return '''// JP file 80: six data-table pointers still use the original 0x0800
// TLB virtual mapping, which the pinned native runtime does not emulate.
// Validate ALL six live pointer words before writing any; idempotent.
static void jp_relocate_file_80_data(uint8_t* rdram, uint32_t base) {
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

''' % pairs


def inject(source: str) -> str:
    if MARKER in source:
        raise ValueError('Japan file 80 fixup already applied')
    if source.count(BEFORE) != 1 or source.count(AFTER) != 1:
        raise ValueError('Missing or ambiguous file 56/callback anchors')
    if source.count('jp_relocate_task_callbacks(rdram, ctx, jp_task);') != 1:
        raise ValueError('Missing Japanese task callback registration')
    with_helper = source.replace(BEFORE, hook_text() + BEFORE, 1)
    call = '''    // JP file 80 table pointers were not translated by osMapTLB.
    if (file_id == 80u && start == 0x00741660u && end == 0x00742270u &&
        base <= 0x80800000u - 0x0C10u) {
        jp_relocate_file_80_data(rdram, base);
    }
'''
    updated = with_helper.replace(AFTER, AFTER + call, 1)
    if updated.count('jp_relocate_file_80_data(rdram, base);') != 1:
        raise ValueError('File 80 relocation hook was not inserted exactly once')
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--in-place', action='store_true')
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() and not args.in_place:
        parser.error('Use --in-place to overwrite private generated C')
    try:
        validate_rom(args.rom.read_bytes())
        updated = inject(args.source.read_text())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(updated)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print('Verified six Japanese file 80 data pointer fixups applied to', args.output)


if __name__ == '__main__':
    main()
