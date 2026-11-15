#!/usr/bin/env python3
"""Audit every recovered USA relocation against the pinned authoritative map.

The USA reference map is from the Goemon64RecompSyms Git submodule. The
Japanese ROM has no equivalent authoritative map yet; this USA regression
gate is a check on the extractor, not a claim of Japanese completeness.
"""
from __future__ import annotations

import argparse
import json
import tomllib
from collections import Counter
from pathlib import Path

USA_ROM_SHA1 = '6ea0ed71032ce08fc2745f412d84936382197494'
VALID_KINDS = {'R_MIPS_HI16', 'R_MIPS_LO16', 'R_MIPS_26'}


def normalized(record: dict) -> tuple[str, int, int]:
    def address(value: int | str) -> int:
        return int(value, 0) if isinstance(value, str) else value

    kind = record['type']
    if kind not in VALID_KINDS:
        raise ValueError('Unknown relocation record kind: '+str(kind))
    return kind, address(record['vram']), address(record['target_vram'])


def audit(usa_candidates: dict, authoritative_sections: list[dict],
          first_overlay: int = 11, last_overlay: int = 80) -> dict:
    if usa_candidates.get('source_sha1') != USA_ROM_SHA1:
        raise ValueError('Candidate relocation JSON is not for the pinned USA ROM')
    reference = {section['name']: section for section in authoritative_sections}
    if len(reference) != len(authoritative_sections):
        raise ValueError('Duplicate reference section names')
    candidate_map = usa_candidates.get('relocations', {})
    errors = []
    count = 0
    for number in range(first_overlay, last_overlay + 1):
        name = f'file_{number}'
        section = reference.get('.' + name)
        if section is None:
            raise ValueError(f'Missing expected USA section {name}')
        expected = Counter(normalized(row) for row in section.get('relocs', []))
        actual = Counter(normalized(row) for row in candidate_map.get(name, []))
        count += sum(actual.values())
        if expected != actual:
            errors.append({
                'section': name,
                'missing_count': sum((expected - actual).values()),
                'extra_count': sum((actual - expected).values()),
                'missing_first': sorted((expected - actual).elements())[:3],
                'extra_first': sorted((actual - expected).elements())[:3],
            })
    if errors:
        raise ValueError('Relocation mismatch: ' + json.dumps(errors, default=str))
    return {'matched_sections': last_overlay-first_overlay+1,
            'matched_records': count,
            'exact_type_site_target_match': True,
            'source_sha1': USA_ROM_SHA1}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--usa-relocations', type=Path, required=True)
    cli.add_argument('--reference-symbols', type=Path, required=True)
    args = cli.parse_args()
    inventory = json.loads(args.usa_relocations.read_text())
    sections = tomllib.loads(args.reference_symbols.read_text())['section']
    stats = audit(inventory, sections)
    if stats['matched_sections'] != 70 or stats['matched_records'] != 6351:
        raise ValueError('Expected 70 USA overlays and 6351 exact relocation records')
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
