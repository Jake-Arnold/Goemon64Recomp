#!/usr/bin/env python3
"""Fail-closed RSP-only texture-image provenance probe for JP native RT64.

Read-only runtime logging. An exact pinned original RT64 RSP source and exact
32 MiB decompressed Japanese ROM are required before any opt-in source edit.
No segment, texture, TMEM, guest memory or renderer state is changed.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

ROM_SIZE = 33554432
ROM_SHA1 = '6f8745fecc3a5e7d4918c7a73353eb0726116ded'
RSP_GIT_BLOB = 'd4d9883e9bab98e0e44988a58ca5f6a06906890e'
RSP = Path('src/hle/rt64_rsp.cpp')
BACKUP = '.pre-jp-texture-segment-v16'
MARKER = 'GOEMON_JP_RT64_TEXTURE_SEGMENT_V16'
INCLUDE_ANCHOR = '#include <cassert>\n'
FUNCTION_ANCHOR = '''    void RSP::setTextureImage(uint8_t fmt, uint8_t siz, uint16_t width, uint32_t segAddress) {
        state->rdp->setTextureImage(fmt, siz, width, fromSegmented(segAddress));
    }
'''
FUNCTION_PATCH = '''    void RSP::setTextureImage(uint8_t fmt, uint8_t siz, uint16_t width, uint32_t segAddress) {
        // GOEMON_JP_RT64_TEXTURE_SEGMENT_V16: leave the original RSP -> RDP
        // address translation and state update unchanged; observe afterwards.
        const uint32_t resolved = fromSegmented(segAddress);
        state->rdp->setTextureImage(fmt, siz, width, resolved);
        static const bool traceEnabled = []() {
            const char *flag = std::getenv("GOEMON_JP_RT64_TEX_TRACE");
            return flag && flag[0] == '1' && flag[1] == '\\0';
        }();
        if (!traceEnabled) return;
        const uint32_t physical = state->rdp->texture.address;
        if (physical != 0x0078B6E0u && physical != 0x007953D0u &&
            physical != 0x003C76E0u && physical != 0x003D13D0u) return;
        const uint32_t segment = (segAddress >> 24u) & 0xFu;
        const uint32_t segmentBase = segments[segment];
        const uint32_t segmentOffset = segAddress & 0x00FFFFFFu;
        struct TraceKey { uint32_t raw, base, physical; };
        static thread_local TraceKey seen[32] = {};
        static thread_local unsigned seenCount = 0;
        for (unsigned i = 0; i < seenCount; ++i) {
            if (seen[i].raw == segAddress && seen[i].base == segmentBase &&
                seen[i].physical == physical) return;
        }
        if (seenCount >= 32u) return;
        seen[seenCount++] = {segAddress, segmentBase, physical};
        std::fprintf(stderr,
            "[JP-RT64] TEX_SEG_V16 raw=0x%08X seg=%u base=0x%08X "
            "offset=0x%06X raw_plus_base=0x%08X resolved=0x%08X "
            "rdp=0x%08X fmt=%u siz=%u width=%u extend=%u\\n",
            segAddress, segment, segmentBase, segmentOffset,
            segmentBase + segmentOffset, resolved, physical,
            unsigned(fmt), unsigned(siz), unsigned(width),
            unsigned(state->extended.extendRDRAM));
    }
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def verify_rom(path: Path) -> None:
    h = hashlib.sha1()
    size = 0
    with path.open('rb') as fp:
        magic = fp.read(4)
        h.update(magic)
        size += len(magic)
        while chunk := fp.read(1024 * 1024):
            size += len(chunk)
            h.update(chunk)
    if size != ROM_SIZE or h.hexdigest() != ROM_SHA1 or magic != bytes.fromhex('80371240'):
        raise ValueError(f'Wrong ROM: expected exact 32 MiB Japanese decompressed SHA1 {ROM_SHA1}; '
                         f'got bytes={size}, sha1={h.hexdigest()}, magic={magic.hex()}')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f'{label}: expected one pinned source anchor; got {count}')
    return text.replace(old, new, 1)


def transform(source: str) -> str:
    if MARKER in source:
        raise ValueError('v16 already installed')
    source = replace_once(source, INCLUDE_ANCHOR,
                          INCLUDE_ANCHOR + '#include <cstdio>\n#include <cstdlib>\n', 'include')
    source = replace_once(source, FUNCTION_ANCHOR, FUNCTION_PATCH, 'RSP texture image')
    return source


def plan(rt64: Path, rom: Path) -> tuple[Path, bytes, bytes]:
    verify_rom(rom)
    rsp = rt64 / RSP
    original = rsp.read_bytes()
    observed = git_blob(original)
    if observed != RSP_GIT_BLOB:
        raise ValueError(f'RSP source drift; expected {RSP_GIT_BLOB}; got {observed}')
    if rsp.with_name(rsp.name + BACKUP).exists():
        raise ValueError('v16 backup already exists; refuse to overwrite')
    updated = transform(original.decode('utf-8')).encode('utf-8')
    return rsp, original, updated


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rt64-dir', type=Path, default=Path('lib/rt64'))
    p.add_argument('--rom', type=Path, required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run', action='store_true')
    g.add_argument('--confirm-modify-private-rt64', action='store_true')
    args = p.parse_args()
    try:
        rsp, original, updated = plan(args.rt64_dir, args.rom)
        if args.confirm_modify_private_rt64:
            backup = rsp.with_name(rsp.name + BACKUP)
            backup.write_bytes(original)
            try:
                rsp.write_bytes(updated)
            except BaseException:
                rsp.write_bytes(original)
                raise
        print('JP v16: exact ROM SHA-1 and original RT64 RSP Git blob PASS')
        print('v16: ' + ('installed; native rebuild required' if args.confirm_modify_private_rt64 else 'validated only'))
        print('source: ' + str(rsp))
    except (OSError, UnicodeError, ValueError) as e:
        p.error(str(e))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
