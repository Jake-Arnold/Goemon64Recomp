#!/usr/bin/env python3
"""Read-only v12 -> v13 probe: sample 8 MiB RDRAM and two address-offset controls.

This is an opt-in source patch for a precisely authenticated private RT64
State file. It does NOT change texture address calculation, loading or drawing.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import jp_rt64_tmem_replay_v12 as v12

STATE = v12.STATE
BACKUP = '.pre-jp-tmem-high-address-v13'
MARKER = 'GOEMON_JP_RT64_TMEM_HIGH_ADDRESS_V13'

OLD_SAMPLE = '''                rec.srcNz64 = 0xFFFFFFFFu; // not sampled (outside conservative 4 MiB bound)
                constexpr uint64_t Conservative4MiB = 4ull * 1024ull * 1024ull;
                if (RDRAM && source <= Conservative4MiB - 64u) {
                    rec.srcNz64 = 0;
                    for (uint32_t i = 0; i < 64u; i++)
                        rec.srcNz64 += RDRAM[size_t(source) + i] != 0;
                }
'''
NEW_SAMPLE = '''                // GOEMON_JP_RT64_TMEM_HIGH_ADDRESS_V13: the pinned runtime
                // reports 8 MiB via osGetMemSize and osMemSize. Only count bytes.
                // 0xFFFFFFFF means not sampled, never "source was zero".
                rec.srcNz64 = 0xFFFFFFFFu;
                rec.candidateNz64 = 0xFFFFFFFFu;
                constexpr uint64_t Runtime8MiB = 8ull * 1024ull * 1024ull;
                if (RDRAM && source <= Runtime8MiB - 64u) {
                    rec.srcNz64 = 0;
                    for (uint32_t i = 0; i < 64u; i++)
                        rec.srcNz64 += RDRAM[size_t(source) + i] != 0;
                }
                // Both failing source addresses differ by 0x003C4000 from
                // previously nonzero load addresses. Compare, do not remap.
                // This is a diagnostic hypothesis, not a proposed fix.
                constexpr uint64_t CandidateBase = 0x003C4000ull;
                if (RDRAM && (source == 0x0078B6E0ull || source == 0x007953D0ull) &&
                    source >= CandidateBase) {
                    const uint64_t candidate = source - CandidateBase;
                    if (candidate <= Runtime8MiB - 64u) {
                        rec.candidateNz64 = 0;
                        for (uint32_t i = 0; i < 64u; i++)
                            rec.candidateNz64 += RDRAM[size_t(candidate) + i] != 0;
                    }
                }
'''

OLD_STRUCT = '            uint32_t index = 0, type = 0, src = 0, srcNz64 = 0xFFFFFFFFu;\n'
NEW_STRUCT = OLD_STRUCT + '            uint32_t candidateNz64 = 0xFFFFFFFFu;\n'
OLD_PRINTF = '"uls=%u ult=%u lrs=%u lrt=%u tmem_nz_before=%u tmem_nz_after=%u\\n",\n'
NEW_PRINTF = '"uls=%u ult=%u lrs=%u lrt=%u tmem_nz_before=%u tmem_nz_after=%u candidate_minus_3c4000_nz64=%u\\n",\n'
OLD_ARGS = '''                            rec.tmemBefore, rec.tmemAfter);
'''
NEW_ARGS = '''                            rec.tmemBefore, rec.tmemAfter, rec.candidateNz64);
'''


def replace_once(s:str,old:str,new:str,label:str)->str:
    c=s.count(old)
    if c!=1:raise ValueError(f'{label}: expected 1 exact v12 anchor; found {c}')
    return s.replace(old,new,1)


def transform_state(s:str)->str:
    if MARKER in s:raise ValueError('v13 already installed')
    if v12.MARKER not in s:raise ValueError('v12 State instrumentation required')
    for old,new,label in [
        (OLD_STRUCT,NEW_STRUCT,'record layout'),
        (OLD_SAMPLE,NEW_SAMPLE,'bounded RDRAM sample'),
        (OLD_PRINTF,NEW_PRINTF,'load output format'),
        (OLD_ARGS,NEW_ARGS,'load output arguments'),
    ]:
        s=replace_once(s,old,new,label)
    return s


def plan(rt64:Path,rom:Path)->tuple[Path,bytes,bytes]:
    v12.v11.v10.v4.validate_rom(rom)
    r=rt64/v12.v11.RENDERER
    c=rt64/v12.v11.v10.CACHE
    s=rt64/STATE
    v8=v12.v11.v10.v8
    v9=v12.v11.v10.v9
    v10=v12.v11.v10
    v11=v12.v11
    pristine_r=r.with_name(r.name+v8.BACKUP_SUFFIX).read_bytes()
    if v10.git_blob_sha(pristine_r)!=v8.RENDER_ORIGINAL_GIT_BLOB:
        raise ValueError('original renderer blob mismatch')
    expected_v8=v8.transform_renderer(pristine_r.decode()).encode()
    if r.with_name(r.name+v9.BACKUP).read_bytes()!=expected_v8:
        raise ValueError('v9 renderer backup mismatch')
    expected_v9=v9.transform(expected_v8.decode()).encode()
    if r.with_name(r.name+v10.RENDER_BACKUP).read_bytes()!=expected_v9:
        raise ValueError('v10 renderer backup mismatch')
    expected_v10=v10.transform_renderer(expected_v9.decode()).encode()
    if r.with_name(r.name+v11.BACKUP).read_bytes()!=expected_v10:
        raise ValueError('v11 renderer backup mismatch')
    if r.read_bytes()!=v11.transform_renderer(expected_v10.decode()).encode():
        raise ValueError('installed renderer differs from exact v11')
    pristine_c=c.with_name(c.name+v10.CACHE_BACKUP).read_bytes()
    if v10.git_blob_sha(pristine_c)!=v10.CACHE_GIT_BLOB:
        raise ValueError('original cache blob mismatch')
    if c.read_bytes()!=v10.transform_cache(pristine_c.decode()).encode():
        raise ValueError('installed texture cache differs from exact v10')
    interpreter=rt64/v10.v4.RELATIVE
    pristine_i=interpreter.with_name(interpreter.name+'.pre-jp-robot-probe').read_bytes()
    if v10.git_blob_sha(pristine_i)!=v10.v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('original interpreter blob mismatch')
    expected_i=v8.transform_interpreter(v10.v7.transform_interpreter(
        v10.v6.transform(v10.v5.transform(v10.v4.transform(pristine_i.decode()))))).encode()
    if interpreter.read_bytes()!=expected_i:
        raise ValueError('installed interpreter differs from exact v8')
    original_s=s.with_name(s.name+v10.v7.BACKUP_SUFFIX).read_bytes()
    if v10.git_blob_sha(original_s)!=v10.v7.STATE_ORIGINAL_GIT_BLOB:
        raise ValueError('original State blob mismatch')
    expected_v7=v10.v7.transform_state(original_s.decode()).encode()
    if s.with_name(s.name+v12.STATE_BACKUP).read_bytes()!=expected_v7:
        raise ValueError('v12 State backup differs from exact v7')
    expected_v12=v12.transform_state(expected_v7.decode()).encode()
    if s.read_bytes()!=expected_v12:
        raise ValueError('installed State differs from exact v12; no modifications')
    if s.with_name(s.name+BACKUP).exists():
        raise ValueError('v13 backup exists; refuse reapply')
    return s, expected_v12, transform_state(expected_v12.decode()).encode()


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',required=True,type=Path)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run',action='store_true')
    g.add_argument('--confirm-modify-private-rt64',action='store_true')
    a=p.parse_args()
    try:
        src,old,new=plan(a.rt64_dir,a.rom)
        if a.confirm_modify_private_rt64:
            backup=src.with_name(src.name+BACKUP)
            backup.write_bytes(old)
            try:src.write_bytes(new)
            except BaseException:
                src.write_bytes(old)
                raise
        print('JP ROM and exact v4-v12 RT64 source/backup chain: PASS')
        print('v13: '+('installed; native rebuild required' if a.confirm_modify_private_rt64 else 'validated only'))
        print('State: '+str(src))
    except (OSError,ValueError,UnicodeError) as exc:p.error(str(exc))
    return 0

if __name__=='__main__':raise SystemExit(main())