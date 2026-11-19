#!/usr/bin/env python3
"""Opt-in v5 RT64 triangle cull-gate instrumentation for authenticated JP robot lists.

Requires the exact installed v4 RT64 probe plus its pristine backed-up pinned
RT64 interpreter. Does not change the original ROM or renderer's behaviour.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
import jp_rt64_robot_probe as v4

V5_MARKER = 'GOEMON_JP_RT64_TRI_GATE_V5'
TARGET = v4.RELATIVE
RECORD_OLD = '            uint32_t counter_resets = 0;\n'
RECORD_NEW = RECORD_OLD + '            uint32_t gate_pass = 0; // Expected RSP drawIndexedTri calls that pass early cull gate.\n' + '            uint32_t gate_skip = 0; // Calls that hit the both-faces-culling early return.\n'
BEFORE_OLD = '                record.expected_tris += opcode == 0xB1 ? 2u : opcode == 0xBF ? 1u : 0u;\n'
BEFORE_NEW = BEFORE_OLD + '''                // GOEMON_JP_RT64_TRI_GATE_V5: count RSP::drawIndexedTri's exact\n                // early-return condition, BEFORE invoking the GBI handler.\n                // GBI_F3DEX::tri2 calls RSP::drawIndexedTri twice; tri1 once.\n                const unsigned tri_calls = opcode == 0xB1 ? 2u : opcode == 0xBF ? 1u : 0u;\n                if (tri_calls != 0u) {\n                    const uint32_t geom = state->rsp->geometryModeStack[\n                        state->rsp->geometryModeStackSize - 1];\n                    const uint32_t both_mask = state->rsp->cullBothMask;\n                    const bool skipped = (geom & both_mask) == both_mask;\n                    record.gate_pass += skipped ? 0u : tri_calls;\n                    record.gate_skip += skipped ? tri_calls : 0u;\n                    if (skipped && record.gate_skip == tri_calls) {\n                        std::fprintf(stderr, "[JP-RT64] CULL_GATE root=0x%04X sample=%u "\n                                             "geometry=0x%08X both_mask=0x%08X calls=%u\\n",\n                                     range.first, goemonProbeCompleted[i] + 1u,\n                                     geom, both_mask, tri_calls);\n                    }\n                }\n'''
END_OLD = '                                     "vertices=%u matrices=%u\\n",\n'
END_NEW = '                                     "vertices=%u matrices=%u gate_pass=%u gate_skip=%u\\n",\n'
ARGS_OLD = '                             record.vertices, record.matrices);\n'
ARGS_NEW = '                             record.vertices, record.matrices,\n                             record.gate_pass, record.gate_skip);\n'


def replace_one(source: str, old: str, new: str, what: str) -> str:
    n=source.count(old)
    if n != 1:
        raise ValueError(f'expected exactly one {what} anchor, found {n}')
    return source.replace(old,new,1)


def transform(source: str) -> str:
    if V5_MARKER in source:
        raise ValueError('v5 triangle gate probe already installed')
    if 'goemon_jp_rt64_probe_before' not in source or 'goemon_jp_rt64_probe_after' not in source:
        raise ValueError('v4 RT64 robot probe not installed')
    for old,new,name in ((RECORD_OLD,RECORD_NEW,'record'),
                         (BEFORE_OLD,BEFORE_NEW,'pre-dispatch tri gate'),
                         (END_OLD,END_NEW,'END log format'),
                         (ARGS_OLD,ARGS_NEW,'END log arguments')):
        source=replace_one(source,old,new,name)
    return source


def plan(rt64: Path, rom: Path) -> tuple[Path,bytes,str]:
    v4.validate_rom(rom)
    target=rt64/TARGET
    original_backup=target.with_name(target.name+'.pre-jp-robot-probe')
    v4_backup=target.with_name(target.name+'.pre-jp-tri-gate-v5')
    pristine=original_backup.read_bytes()
    if v4.blob_hash(pristine)!=v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('pristine RT64 backup does not match pinned Git blob')
    installed=target.read_bytes()
    expected=v4.transform(pristine.decode('utf-8')).encode('utf-8')
    if installed!=expected:
        raise ValueError('installed RT64 v4 differs from exact pinned transformed source; no changes made')
    if v4_backup.exists():
        raise ValueError('v5 RT64 backup already exists; refuse repeated modification')
    changed=transform(installed.decode('utf-8'))
    return target,installed,changed


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    p.add_argument('--rom',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run',action='store_true')
    group.add_argument('--confirm-modify-private-rt64',action='store_true')
    args=p.parse_args()
    try:
        target,current,changed=plan(args.rt64_dir,args.rom)
        backup=target.with_name(target.name+'.pre-jp-tri-gate-v5')
        if args.confirm_modify_private_rt64:
            backup.write_bytes(current)
            try:
                target.write_text(changed,encoding='utf-8')
            except BaseException:
                target.write_bytes(current)
                raise
        print('pinned original RT64 Git blob + precise v4 installed source: PASS')
        print('exact original JP ROM SHA-1: PASS')
        print('mode: '+('v5 culling-gate trace installed (rebuild required)' if args.confirm_modify_private_rt64 else 'validated only'))
        print('source: '+str(target))
        print('backup: '+str(backup))
    except (OSError,UnicodeError,ValueError) as e:
        p.error(str(e))
    return 0

if __name__=='__main__':
    raise SystemExit(main())