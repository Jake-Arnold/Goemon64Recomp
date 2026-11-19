#!/usr/bin/env python3
"""Read-only v15 provenance analysis of existing v12/v13 JP RT64 replay logs.

Classifies whether each suspicious high source_start already has a high
setTextureImage-derived source_tex or instead acquires the high address through
its LoadTile/LoadBlock byte offset. No ROM, runtime source or asset mutations.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re

TARGETS = (0x0078B6E0, 0x007953D0)
BASE_DELTA = 0x003C4000
REPLAY = re.compile(r'^\[JP-RT64\] TEX_REPLAY_LOAD\s+(.*)$')
FIELD = re.compile(r'([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)')
TYPE = {0: 'Tile', 1: 'Block', 2: 'TLUT'}
UNKNOWN = 0xFFFFFFFF


def integer(fields: dict[str, str], name: str) -> int | None:
    value = fields.get(name)
    if value is None:
        return None
    try:
        result = int(value, 0)
        return result if result >= 0 else None
    except ValueError:
        return None


def nz(fields: dict[str, str], field: str) -> str:
    n = integer(fields, field)
    return 'NOT_LOGGED' if n is None else ('UNREAD' if n == UNKNOWN else f'{n}/64')


def byte_offset(fields: dict[str, str]) -> int | None:
    type_ = integer(fields, 'type')
    width = integer(fields, 'width')
    siz = integer(fields, 'load_siz')
    uls = integer(fields, 'uls')
    ult = integer(fields, 'ult')
    if None in (type_, width, siz, uls, ult) or type_ not in TYPE or siz > 3:
        return None
    bytes_per_row = (width << siz) >> 1
    if type_ == 1:
        return ((uls << siz) >> 1) + bytes_per_row * ult
    return (((uls >> 2) << siz) >> 1) + bytes_per_row * (ult >> 2)


def summarize(lines) -> str:
    matched = defaultdict(list)
    for line in lines:
        match = REPLAY.match(line)
        if match is None:
            continue
        fields = dict(FIELD.findall(match.group(1)))
        start = integer(fields, 'source_start')
        if start in TARGETS:
            matched[start].append(fields)

    result = [
        'JP v15 address provenance (read-only; original v13 replay log)',
        'RT64 path: RSP::fromSegmented -> RDP::setTextureImage -> RDP::load{Block,Tile,TLUT}Operation',
    ]
    for target in TARGETS:
        records = matched[target]
        result.append(f'0x{target:08X}: {len(records)} replay records')
        if not records:
            result.append('  NO DATA; no address conclusion from this target')
            continue
        configurations = defaultdict(list)
        for fields in records:
            key = tuple(fields.get(k) for k in ('hash', 'type', 'source_tex', 'width', 'load_siz', 'uls', 'ult', 'load_fmt', 'tile_fmt', 'tile_siz'))
            configurations[key].append(fields)
        result.append(f'  distinct load configurations: {len(configurations)}')
        for key, grouped in sorted(configurations.items(), key=lambda entry: repr(entry[0])):
            f = grouped[0]
            base = integer(f, 'source_tex')
            offset = byte_offset(f)
            kind = TYPE.get(integer(f, 'type'), 'UNKNOWN')
            base_text = f'0x{base:08X}' if base is not None else 'NOT_LOGGED'
            offset_text = f'0x{offset:X}' if offset is not None else 'NOT_LOGGED'
            reconstructed = ((base + offset) & 0xFFFFFFFF) if base is not None and offset is not None else None
            comparison = 'NOT_CHECKED' if reconstructed is None else ('MATCH' if reconstructed == target else f'MISMATCH:0x{reconstructed:08X}')
            result.append(f'  x{len(grouped)} {kind}: source_tex={base_text} byte_offset={offset_text} source_start=0x{target:08X} formula={comparison}')
            result.append(f"    width={f.get('width', '?')} siz={f.get('load_siz', '?')} uls={f.get('uls', '?')} ult={f.get('ult', '?')} hash={f.get('hash', '?')}")
            observations = sorted({
                (nz(x, 'source_nonzero64'), nz(x, 'candidate_minus_3c4000_nz64'),
                 x.get('tmem_nz_before', '?'), x.get('tmem_nz_after', '?')) for x in grouped
            })
            for upper, lower, before, after in observations:
                result.append(f'    first64 high={upper} lower={lower}; whole TMEM={before}->{after}')
            if base is None:
                result.append('    ORIGIN: source_tex missing; cannot classify')
            elif base >= BASE_DELTA and offset is not None and offset < BASE_DELTA:
                result.append(f'    ORIGIN: high image base precedes load offset; candidate image base=0x{base - BASE_DELTA:08X}')
            elif offset is not None and offset >= BASE_DELTA:
                result.append('    ORIGIN: load tile offset is at least 0x003C4000; investigate tile width/uls/ult')
            else:
                result.append('    ORIGIN: image base plus modest load offset; inspect segmentation and expected segment base')
    result.append('Read-only counts do not identify the correct texture or prove a duplicated segment base.')
    return '\n'.join(result)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    args = p.parse_args()
    with args.log.open('r', encoding='utf-8', errors='replace') as f:
        print(summarize(f))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
