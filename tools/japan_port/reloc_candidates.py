#!/usr/bin/env python3
"""Recover *candidates* for N64Recomp overlay relocations from Splat asm.

Conservative: only symbolically annotated, in-overlay HI16/LO16 references
and direct MIPS J/JAL targets. Cross-check with source ROM words and verify
Splat's declared decompressed SHA-1. Not a complete relocation analysis.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ANNOTATION = re.compile(
    r'/\*\s*([0-9A-Fa-f]{3,8})\s+([0-9A-Fa-f]{8})\s+'
    r'([0-9A-Fa-f]{8})\s*\*/\s*(\w+)\s*(.*)'
)
REFERENCE = re.compile(r'%(hi|lo)\(([^)]+)\)')
TARGET = re.compile(r'(?:^|_)(080[0-9A-Fa-f]{5})(?:_|$)')
OFFSET = re.compile(r'\s*([+-])\s*(0x[0-9A-Fa-f]+|[0-9]+)\s*$')


def symbol_address(expr: str) -> int | None:
    match = TARGET.search(expr)
    if not match:
        return None
    base = int(match[1], 16)
    offset = OFFSET.search(expr)
    if offset:
        magnitude = int(offset[2], 0)
        base += magnitude if offset[1] == "+" else -magnitude
    return base


def overlay_sections(splat: dict) -> list[dict]:
    result = []
    segments = splat['segments']
    for i, seg in enumerate(segments[:-1]):
        if not isinstance(seg, dict) or seg.get('type') != 'code':
            continue
        name = seg.get('name', '')
        if not (seg.get('overlay') and name.startswith('file_')
                and seg.get('vram') == 0x08000000):
            continue
        kinds = {sub[1] for sub in seg.get('subsegments', [])
                 if isinstance(sub, list) and len(sub) > 1}
        if not kinds.intersection({'asm', 'hasm', 'c'}):
            continue
        stop = segments[i+1]
        if not isinstance(stop, dict):
            raise ValueError(f'Bad section end for {name}')
        result.append({'name':name,'start':seg['start'],
                       'end':stop['start'],'vram':seg['vram']})
    if not result:
        raise ValueError('No relocatable overlay candidates')
    return result


def parse(asm_root: Path, splat_path: Path, rom_path: Path) -> dict:
    splat = yaml.safe_load(splat_path.read_text())
    raw = rom_path.read_bytes()
    expected_sha1 = splat['sha1']
    digest = hashlib.sha1(raw).hexdigest()
    if digest.lower() != expected_sha1.lower():
        raise ValueError(f'Decompressed ROM SHA-1 mismatch: {digest} != {expected_sha1}')
    regions = overlay_sections(splat)
    relocs = defaultdict(list)
    sites = set()
    checked_words = 0
    for asm in sorted(asm_root.rglob('*.s')):
        if 'data' in asm.relative_to(asm_root).parts:
            continue
        for line_number, line in enumerate(asm.read_text(errors='replace').splitlines(), 1):
            m = ANNOTATION.search(line)
            if not m:
                continue
            rom, pc, word = (int(m[i], 16) for i in (1, 2, 3))
            # Most functions are statically loaded main/early overlays. Ignore them.
            sec = next((s for s in regions
                        if s['start'] <= rom < s['end']
                        and s['vram'] + rom - s['start'] == pc), None)
            if sec is None:
                continue
            if rom + 4 > len(raw) or int.from_bytes(raw[rom:rom+4], 'big') != word:
                raise ValueError(f'Assembly/ROM disagreement: {asm}:{line_number}')
            checked_words += 1
            opcode, mnemonic, operands = word >> 26, m[4], m[5]
            symbol = REFERENCE.search(operands)
            relocation_type = None
            target_vram = None
            if symbol:
                target_vram = symbol_address(symbol[2])
                if target_vram is not None:
                    relocation_type = {
                        'hi': 'R_MIPS_HI16', 'lo': 'R_MIPS_LO16'
                    }[symbol[1]]
                    if symbol[1] == 'hi' and (mnemonic != 'lui' or opcode != 0x0F):
                        raise ValueError(f'HI16 not a LUI: {asm}:{line_number}')
                    if symbol[1] == 'lo' and opcode in (2, 3, 15):
                        raise ValueError(f'LO16 impossible opcode: {asm}:{line_number}')
                    if symbol[1] == 'hi' and (word & 0xFFFF) not in (((target_vram + 0x8000) >> 16) & 0xFFFF, (target_vram >> 16) & 0xFFFF):
                        raise ValueError(f'HI16 immediate mismatch: {asm}:{line_number}')
                    if symbol[1] == 'lo' and (word & 0xFFFF) != (target_vram & 0xFFFF):
                        raise ValueError(f'LO16 immediate mismatch: {asm}:{line_number}')
            elif mnemonic in ('j', 'jal'):
                target_vram = symbol_address(operands)
                if target_vram is not None:
                    relocation_type = 'R_MIPS_26'
                    if opcode not in (2,3) or (word & 0x03FFFFFF) != ((target_vram >> 2) & 0x03FFFFFF):
                        raise ValueError(f'R_MIPS_26 encoding mismatch: {asm}:{line_number}')
            if relocation_type is None or target_vram is None:
                continue
            if not sec['vram'] <= target_vram < sec['vram'] + sec['end'] - sec['start']:
                continue  # An absolute reference to a different overlay/game section.
            site=(sec['name'],pc)
            if site in sites:
                raise ValueError(f'Duplicate relocation site {site} at {asm}:{line_number}')
            sites.add(site)
            relocs[sec['name']].append({
                'type': relocation_type,
                'vram': f'0x{pc:08X}',
                'target_vram': f'0x{target_vram:08X}',
            })
    # HI16 and LO16 must pair for each target in each overlay.
    for section, records in relocs.items():
        totals = defaultdict(Counter)
        for record in records:
            if record['type'] in ('R_MIPS_HI16', 'R_MIPS_LO16'):
                totals[record['target_vram']][record['type']] += 1
        for target, amounts in totals.items():
            if amounts['R_MIPS_HI16'] != amounts['R_MIPS_LO16']:
                raise ValueError(f'{section}: unpaired HI16/LO16 for {target}: {amounts}')
        records.sort(key=lambda item: int(item['vram'],16))
    counts = Counter(record['type'] for records in relocs.values() for record in records)
    return {
        'source_sha1': digest,
        'relocatable_sections': len(regions),
        'sections_with_candidates': len(relocs),
        'checked_instruction_words': checked_words,
        'candidate_relocations': sum(counts.values()),
        'types': dict(sorted(counts.items())),
        'per_section': dict(sorted(((name,len(items)) for name,items in relocs.items()),
                                   key=lambda item:int(item[0].split('_')[1]))),
        'caveat': 'Conservative symbol-based candidates only; not an authoritative relocation table.',
        'relocations': dict(sorted(relocs.items(),key=lambda item:int(item[0].split('_')[1])))
    }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--asm-root', type=Path, required=True)
    cli.add_argument('--splat', type=Path, required=True)
    cli.add_argument('--rom', type=Path, required=True)
    cli.add_argument('--output', type=Path, required=True)
    args=cli.parse_args()
    output=parse(args.asm_root,args.splat,args.rom)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k!='relocations'},indent=2))


if __name__=='__main__':
    main()
