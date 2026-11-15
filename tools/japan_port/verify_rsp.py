#!/usr/bin/env python3
"""Proof that the Japanese ROM uses the same audio RSP program as the USA ROM.

Runs exclusively on locally supplied game ROMs. No ROM bytes are exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from .rom import (JP_NORMAL, USA_SOURCE, COMPRESSED_SIZE, RomError,
                      normalize, sha1)
except ImportError:
    from rom import (JP_NORMAL, USA_SOURCE, COMPRESSED_SIZE, RomError,
                     normalize, sha1)

USA_RSP_OFFSET = 0x546B0
JAPAN_RSP_OFFSET = 0x54930
RSP_SIZE = 0xE20
RSP_SHA1 = '21e05bb9b4b3611e0cc2374c3ad6cc26adf2b385'


def compare_microcode(usa: bytes, japan: bytes, usa_offset: int,
                      japan_offset: int, length: int, expected_sha1: str) -> dict:
    if length <= 0 or min(usa_offset, japan_offset) < 0:
        raise RomError('Invalid RSP code bounds')
    if usa_offset + length > len(usa) or japan_offset + length > len(japan):
        raise RomError('RSP microcode range outside a supplied ROM')
    reference = usa[usa_offset:usa_offset + length]
    candidate = japan[japan_offset:japan_offset + length]
    digest = hashlib.sha1(reference).hexdigest()
    if digest != expected_sha1:
        raise RomError('USA RSP code digest does not match the pinned reference')
    if reference != candidate:
        raise RomError('Japanese audio RSP microcode differs from the USA routine')
    if japan.find(reference) != japan_offset or japan.count(reference) != 1:
        raise RomError('Japanese RSP code is not uniquely located at the expected offset')
    return {
        'usa_offset': f'0x{usa_offset:X}',
        'japan_offset': f'0x{japan_offset:X}',
        'size': f'0x{length:X}',
        'sha1': digest,
        'byte_identical': True,
        'japan_occurrences': 1,
    }


def check_roms(usa_file: Path, japan_file: Path) -> dict:
    usa, _ = normalize(usa_file.read_bytes())
    japan, original_format = normalize(japan_file.read_bytes())
    if len(usa) != COMPRESSED_SIZE or sha1(usa) != USA_SOURCE:
        raise RomError('USA input must be the pinned original 16 MiB ROM revision')
    if len(japan) != COMPRESSED_SIZE or sha1(japan) != JP_NORMAL:
        raise RomError('Japanese input must normalize to the pinned 16 MiB ROM revision')
    result = compare_microcode(
        usa, japan, USA_RSP_OFFSET, JAPAN_RSP_OFFSET, RSP_SIZE, RSP_SHA1
    )
    result['japan_input_format'] = original_format
    result['conclusion'] = 'Reusing the same aspMain RSP recompilation is byte-supported'
    return result


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--usa', type=Path, required=True)
    cli.add_argument('--japan', type=Path, required=True)
    args = cli.parse_args()
    try:
        result = check_roms(args.usa, args.japan)
    except (OSError, RomError) as error:
        cli.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
