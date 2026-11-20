#!/usr/bin/env python3
"""Guarded v16 -> v18 RSP-only texture alias sampling (no address remapping).

Authenticates original JP decompressed ROM, pristine pinned RT64 RSP source,
exact installed v16 transformation, and all source backups before any edit.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import jp_rt64_texture_segment_v16 as v16

MARKER = 'GOEMON_JP_RT64_TEXTURE_ALIAS_V18'
BACKUP = '.pre-jp-texture-alias-v18'
RSP = v16.RSP
OLD_GUARD = '''        if (physical != 0x0078B6E0u && physical != 0x007953D0u &&
            physical != 0x003C76E0u && physical != 0x003D13D0u) return;
'''
NEW_GUARD = '''        if (physical != 0x0078B6E0u && physical != 0x007953D0u &&
            physical != 0x003C76E0u && physical != 0x003D13D0u &&
            physical != 0x007CA950u) return;
'''
OLD_TAIL = '''            unsigned(state->extended.extendRDRAM));
    }
'''
NEW_TAIL = '''            unsigned(state->extended.extendRDRAM));
        // GOEMON_JP_RT64_TEXTURE_ALIAS_V18: scalar counts only, never read
        // outside pinned runtime 8 MiB. This is NOT an address replacement.
        if (physical == 0x007CA950u && state->RDRAM != nullptr) {
            constexpr uint32_t SampleBytes = 4096u;
            constexpr uint32_t RDRAMBytes = 8u * 1024u * 1024u;
            constexpr uint32_t addresses[3] = {
                0x007CA950u, 0x003CA950u, 0x00406950u
            };
            static_assert(0x007CA950u + SampleBytes <= RDRAMBytes,
                          "RDRAM high source out of range");
            uint32_t nonzero64[3] = {};
            uint32_t nonzero4096[3] = {};
            for (unsigned a = 0; a < 3u; ++a) {
                for (uint32_t i = 0; i < SampleBytes; ++i) {
                    const bool nonzero = state->RDRAM[addresses[a] + i] != 0;
                    nonzero4096[a] += unsigned(nonzero);
                    if (i < 64u) nonzero64[a] += unsigned(nonzero);
                }
            }
            std::fprintf(stderr,
                "[JP-RT64] TEX_ALIAS_V18 addr=0x%08X high_nz64=%u "
                "high_nz4096=%u minus_4MiB=0x003CA950 minus_4MiB_nz64=%u "
                "minus_4MiB_nz4096=%u minus_3C4000=0x00406950 "
                "minus_3C4000_nz64=%u minus_3C4000_nz4096=%u\\n",
                physical, nonzero64[0], nonzero4096[0],
                nonzero64[1], nonzero4096[1], nonzero64[2], nonzero4096[2]);
        }
    }
'''


def one(s: str, old: str, new: str, desc: str) -> str:
    n = s.count(old)
    if n != 1:
        raise ValueError(f'{desc}: expected one exact v16 anchor; found {n}')
    return s.replace(old, new, 1)


def transform(source: str) -> str:
    if MARKER in source:
        raise ValueError('v18 already installed')
    if v16.MARKER not in source:
        raise ValueError('v16 source required')
    source = one(source, OLD_GUARD, NEW_GUARD, 'v16 source address filter')
    source = one(source, OLD_TAIL, NEW_TAIL, 'v16 logging function ending')
    return source


def plan(rt64: Path, rom: Path) -> tuple[Path, bytes, bytes]:
    v16.verify_rom(rom)
    source = rt64 / RSP
    original = source.with_name(source.name + v16.BACKUP).read_bytes()
    if v16.git_blob(original) != v16.RSP_GIT_BLOB:
        raise ValueError('original RSP backup does not match pinned Git blob')
    expected_v16 = v16.transform(original.decode('utf-8')).encode('utf-8')
    actual = source.read_bytes()
    if actual != expected_v16:
        raise ValueError('installed RSP source differs from exact v16; no modifications')
    if source.with_name(source.name + BACKUP).exists():
        raise ValueError('v18 backup already exists; refuse to reapply')
    return source, actual, transform(actual.decode('utf-8')).encode('utf-8')


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', required=True, type=Path)
    p.add_argument('--rt64-dir', type=Path, default=Path('lib/rt64'))
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--dry-run', action='store_true')
    modes.add_argument('--confirm-modify-private-rt64', action='store_true')
    args = p.parse_args()
    try:
        src, previous, modified = plan(args.rt64_dir, args.rom)
        if args.confirm_modify_private_rt64:
            backup = src.with_name(src.name + BACKUP)
            backup.write_bytes(previous)
            try:
                src.write_bytes(modified)
            except BaseException:
                src.write_bytes(previous)
                raise
        print('v18: pinned ROM, original RSP backup and installed v16 source PASS')
        print('v18: ' + ('installed; native rebuild required' if args.confirm_modify_private_rt64 else 'validated only'))
    except (OSError, ValueError, UnicodeError) as e:
        p.error(str(e))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
