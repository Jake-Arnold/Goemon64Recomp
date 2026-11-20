#!/usr/bin/env python3
"""Complete pinned JP N64Recomp *candidate* metadata without game code.

Two independent observations from the exact decompressed Japanese revision:
* libultra exceptasm contains send_mesg and handle_CpU as separate routines,
  although the original Splat extraction merged both.
* the C-designated wave_uty segment contains 24 game functions; they were
  re-extracted using an asm-only local Splat probe.
Also emit explicit empty reloc arrays for dynamic overlays with no records:
N64Recomp otherwise marks them non-relocatable and rejects the overlay list.

This repairs code-generation metadata; it does NOT prove runtime correctness.
"""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from pathlib import Path

try:
    from .rom import JP_DECOMP, DECOMPRESSED_SIZE, checked
except ImportError:
    from rom import JP_DECOMP, DECOMPRESSED_SIZE, checked

# ROM-offset and size ONLY, never game instructions. All candidate boundaries
# cross-checked against a fresh spimdisasm/Splat asm split of wave_uty at
# ROM [0x140D0, 0x15500) for Japanese decompressed SHA-1 JP_DECOMP.
WAVE_FUNCTIONS = [
    (0x140D0, 0x64), (0x14134, 0x80), (0x141B4, 0xA0),
    (0x14254, 0x50), (0x142A4, 0xF8), (0x1439C, 0x64),
    (0x14400, 0x20), (0x14420, 0x534), (0x14954, 0x54),
    (0x149A8, 0xA4), (0x14A4C, 0x22C), (0x14C78, 0xCC),
    (0x14D44, 0xE4), (0x14E28, 0x184), (0x14FAC, 0x24),
    (0x14FD0, 0x80), (0x15050, 0x30), (0x15080, 0x138),
    (0x151B8, 0x14C), (0x15304, 0x8C), (0x15390, 0x20),
    (0x153B0, 0x34), (0x153E4, 0x70), (0x15454, 0xA4),
]
JP_MAIN_VRAM_OFFSET = 0x80000450 - 0x1050
RAW_FUNCTION_COUNT = 7351
COMPLETE_FUNCTION_COUNT = 7376
EXPECTED_RELOCATIONS = 6414
OVERLAY_START = 24
OVERLAY_END = 80
MERGED_NAME = 'func_80049604_4A204'


def func_name(rom_offset: int) -> str:
    vram = JP_MAIN_VRAM_OFFSET + rom_offset
    return f'func_{vram:08X}_{rom_offset:X}'


def complete(symbol_text: str, rom: bytes) -> tuple[str, dict]:
    # Validate input identity before applying revision-specific address fixes.
    if len(rom) != DECOMPRESSED_SIZE:
        raise ValueError('Japanese ROM must be exactly 32 MiB')
    import hashlib
    if hashlib.sha1(rom).hexdigest() != JP_DECOMP:
        raise ValueError('Japanese ROM revision mismatch')
    if int.from_bytes(rom[0x4A2B8:0x4A2BC], 'big') != 0x3C013000:
        raise ValueError('libultra handle_CpU boundary instruction changed')
    if len(WAVE_FUNCTIONS) != 24:
        raise ValueError('Expected 24 independently extracted wave_uty functions')
    for index, (start, size) in enumerate(WAVE_FUNCTIONS):
        if size <= 0 or (start | size) & 3:
            raise ValueError('Unaligned wave_uty candidate')
        if index and WAVE_FUNCTIONS[index-1][0] + WAVE_FUNCTIONS[index-1][1] != start:
            raise ValueError('Noncontiguous wave_uty candidate code')
    if WAVE_FUNCTIONS[0][0] != 0x140D0 or WAVE_FUNCTIONS[-1][0] + WAVE_FUNCTIONS[-1][1] != 0x154F8:
        raise ValueError('wave_uty segment boundaries changed')

    parsed = tomllib.loads(symbol_text)
    sections = parsed['section']
    if len(sections) != 72 or len({x['name'] for x in sections}) != 72:
        raise ValueError('Unexpected Japanese section inventory')
    lookup = {x['name']: x for x in sections}
    original_count = sum(len(x['functions']) for x in sections)
    original_relocs = sum(len(x.get('relocs', [])) for x in sections)
    if original_count != RAW_FUNCTION_COUNT or original_relocs != EXPECTED_RELOCATIONS:
        raise ValueError(f'Unexpected baseline counts: {original_count} functions, {original_relocs} relocations')
    main = lookup.get('.main')
    if main is None or main['rom'] != 0x1050 or main['vram'] != 0x80000450:
        raise ValueError('Japanese main section mapping differs')
    merged = [x for x in main['functions'] if x['name'] == MERGED_NAME]
    if len(merged) != 1 or (merged[0]['vram'], merged[0]['size']) != (0x80049604, 0xE8):
        raise ValueError('Expected original combined libultra function')
    for start, size in WAVE_FUNCTIONS:
        vram = JP_MAIN_VRAM_OFFSET + start
        if any(f['vram'] < vram + size and vram < f['vram'] + f['size']
               for f in main['functions']):
            raise ValueError('wave_uty candidate overlaps an existing function')
    main_region = re.split(r'(?=^\[\[section\]\]$)', symbol_text, flags=re.M)
    if len(main_region) != len(sections) + 1:
        raise ValueError('Unexpected TOML section structure')
    for index, section in enumerate(sections, 1):
        chunk = main_region[index]
        marker = f'name = "{section["name"]}"'
        if len(re.findall(r'^'+re.escape(marker)+r'$', chunk, flags=re.M)) != 1:
            raise ValueError('TOML section order does not match parsed data')
        if section['name'] == '.main':
            original = '{ name = "func_80049604_4A204", vram = 0x80049604, size = 0xE8 },'
            if chunk.count(original) != 1:
                raise ValueError('Expected exact combined libultra symbol line')
            chunk = chunk.replace(
                original,
                '{ name = "send_mesg", vram = 0x80049604, size = 0xB4 },\n'
                '    { name = "handle_CpU", vram = 0x800496B8, size = 0x34 },'
            )
            before = '{ name = "func_80014900_15500",'
            if chunk.count(before) != 1:
                raise ValueError('Expected following main function after wave_uty')
            lines = ''.join(
                f'{{ name = "{func_name(start)}", '
                f'vram = 0x{JP_MAIN_VRAM_OFFSET+start:08X}, size = 0x{size:X} }},\n    '
                for start, size in WAVE_FUNCTIONS
            )
            chunk = chunk.replace(before, lines + before)
        if section['name'].startswith('.file_'):
            number = int(section['name'].split('_')[-1])
            if OVERLAY_START <= number <= OVERLAY_END and 'relocs' not in section:
                if chunk.count('functions = [') != 1:
                    raise ValueError('Expected one functions array per overlay')
                chunk = chunk.replace('functions = [',
                                      'relocs = [\n]\n\nfunctions = [', 1)
        main_region[index] = chunk

    result = ''.join(main_region)
    checked_sections = tomllib.loads(result)['section']
    functions = sum(len(s['functions']) for s in checked_sections)
    relocs = sum(len(s.get('relocs', [])) for s in checked_sections)
    overlays_with_reloc_tables = 0
    for sec in checked_sections:
        if not sec['name'].startswith('.file_'):
            continue
        num = int(sec['name'].split('_')[-1])
        if OVERLAY_START <= num <= OVERLAY_END:
            if 'relocs' not in sec:
                raise ValueError(f'Missing explicit overlay relocation table: {num}')
            overlays_with_reloc_tables += 1
    if (functions, relocs, overlays_with_reloc_tables) != (
        COMPLETE_FUNCTION_COUNT, EXPECTED_RELOCATIONS, 57
    ):
        raise ValueError('Completed metadata failed count/overlay gates')
    return result, {
        'source_sha1': JP_DECOMP,
        'sections': len(checked_sections),
        'functions': functions,
        'relocations': relocs,
        'dynamic_overlay_tables': overlays_with_reloc_tables,
        'new_wave_functions': len(WAVE_FUNCTIONS),
        'libultra_function_splits': 1,
        'status': 'N64Recomp code-generation candidate; native PC play unverified',
    }


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--candidate-symbols', type=Path, required=True)
    cli.add_argument('--japan-rom', type=Path, required=True)
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    if args.candidate_symbols.resolve() == args.output.resolve():
        cli.error('Output must differ from the uncorrected candidate input')
    try:
        data, stats = complete(args.candidate_symbols.read_text(),
                               checked(args.japan_rom, JP_DECOMP, DECOMPRESSED_SIZE))
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
        cli.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(data)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
