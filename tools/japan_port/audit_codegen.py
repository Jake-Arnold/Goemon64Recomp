#!/usr/bin/env python3
"""Audit generated Japanese N64Recomp C without executing game code.

Checks emitted function symbols, runtime-provided references, all section and
relocation metadata, and overlay indices against the local provisional Japanese
symbol TOML. Does not prove C compilation, linkability or game playability.
"""
from __future__ import annotations

import argparse
import json
import re
import tomllib
from collections import Counter
from pathlib import Path

DEFINITION = re.compile(
    r'^RECOMP_FUNC void (\w+)\(uint8_t\* rdram, recomp_context\* ctx\)\s*\{',
    re.M,
)
DECLARATION = re.compile(
    r'^void (\w+)\(uint8_t\* rdram, recomp_context\* ctx\);', re.M
)
REGISTERED = re.compile(r'\.func = (\w+),')
RELOC_ROW = re.compile(
    r'\.offset = 0x([0-9A-F]+), '
    r'\.target_section_offset = 0x([0-9A-F]+), '
    r'\.target_section = (\d+), \.type = (R_MIPS_\w+)'
)
ROM_ROW = re.compile(
    r'\.rom_addr = 0x([0-9A-F]+), \.ram_addr = 0x([0-9A-F]+), '
    r'\.size = 0x([0-9A-F]+), .*?\.index = (\d+)'
)


def verify(root: Path, symbols: Path) -> dict:
    root = Path(root)
    sections = tomllib.loads(Path(symbols).read_text())['section']
    if (len(sections) != 72 or sections[0]['name'] != '.entry'
            or sections[1]['name'] != '.main'):
        raise ValueError('Expected 72 Japanese sections with entry/main first')
    overlay = (root / 'recomp_overlays.inl').read_text()
    header = (root / 'funcs.h').read_text()
    lookup = (root / 'lookup.cpp').read_text()
    files = sorted(root.glob('funcs_*.c'))
    if not files:
        raise ValueError('No generated functions')
    prototypes = DECLARATION.findall(header)
    defined = []
    for file in files:
        defined.extend(DEFINITION.findall(file.read_text()))
    registered = REGISTERED.findall(overlay)
    for label, values in (
        ('declarations', prototypes),
        ('definitions', defined),
        ('registrations', registered),
    ):
        duplicates = [name for name, count in Counter(values).items() if count > 1]
        if duplicates:
            raise ValueError(f'Duplicate {label}: {duplicates[:5]}')
    if set(prototypes) != set(registered):
        raise ValueError('Generated header and overlay table register different functions')
    if not set(defined) <= set(prototypes):
        raise ValueError('Native C function definitions absent from generated header')
    externals = sorted(set(prototypes) - set(defined))
    if any(not name.endswith('_recomp') for name in externals):
        raise ValueError('Unexpected undefined generated C symbol: ' + str(externals[:10]))
    if 'gpr get_entrypoint_address() { return (gpr)(int32_t)0x80000400u; }' not in lookup:
        raise ValueError('Japanese entrypoint lookup missing or wrong address')
    rows = ROM_ROW.findall(overlay)
    if len(rows) != len(sections):
        raise ValueError(f'Section table count differs: {len(rows)} != {len(sections)}')
    for index, (row, section) in enumerate(zip(rows, sections)):
        rom, ram, size, entry_index = (
            int(value, 16) if item < 3 else int(value)
            for item, value in enumerate(row)
        )
        if (rom, ram, size, entry_index) != (
            section['rom'], section['vram'], section['size'], index
        ):
            raise ValueError(f'Section mismatch at {index} {section["name"]}')
    marker = re.search(r'const size_t num_sections = (\d+);', overlay)
    if marker is None or int(marker[1]) != len(sections):
        raise ValueError('Section count constant mismatches metadata')
    table = re.search(
        r'static int overlay_sections_by_index\[\] = \{(.*?)\};',
        overlay, re.S
    )
    if table is None:
        raise ValueError('Missing overlay load index table')
    overlay_indices = [int(value) for value in re.findall(r'\b\d+\b', table[1])]
    if overlay_indices != list(range(15, 72)):
        raise ValueError('Expected 57 Japanese file_24..file_80 overlay mappings')
    relocation_total = 0
    for index, section in enumerate(sections):
        name = section['name'].lstrip('.')
        matches = re.search(
            r'static RelocEntry section_' + str(index) + '_' +
            re.escape(name) + r'_relocs\[\] = \{(.*?)\};',
            overlay, re.S
        )
        expected = section.get('relocs', [])
        if expected and matches is None:
            raise ValueError(f'No emitted relocation array for {name}')
        actual = RELOC_ROW.findall(matches[1]) if matches else []
        if len(actual) != len(expected):
            raise ValueError(
                f'Relocation count mismatch in {name}: {len(actual)} != {len(expected)}'
            )
        for row, item in zip(actual, expected):
            offset, target, target_section, relocation_type = row
            observed = (
                int(offset, 16), int(target, 16),
                int(target_section), relocation_type
            )
            correct = (
                item['vram'] - section['vram'],
                item['target_vram'] - section['vram'],
                index, item['type']
            )
            if observed != correct:
                raise ValueError(
                    f'Relocation entry disagrees with symbol map in {name}: '
                    f'{observed} != {correct}'
                )
        relocation_total += len(actual)
    return {
        'metadata_functions': sum(len(s['functions']) for s in sections),
        'emitted_c_function_definitions': len(defined),
        'header_and_registered_functions': len(prototypes),
        'externally_provided_runtime_functions': len(externals),
        'sections': len(sections),
        'relocatable_overlay_slots': len(overlay_indices),
        'validated_relocation_records': relocation_total,
        'generated_c_files': len(files),
        'status': 'Generated output internally consistent; native compilation/gameplay unverified',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated', type=Path, required=True)
    parser.add_argument('--symbols', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.generated, args.symbols), indent=2))


if __name__ == '__main__':
    main()
