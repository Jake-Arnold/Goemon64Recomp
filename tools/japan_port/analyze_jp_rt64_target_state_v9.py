#!/usr/bin/env python3
"""Summarize read-only RT64 robot render-target and alpha/depth context logs.

Counts unique guest-CPU source GameCalls separately from repeated host draws.
No GPU execution, depth/stencil pass, shader output or pixel visibility claim.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re

MAX_BYTES=32*1024*1024
RECORD=re.compile(r'^.*\[JP-RT64\] TARGET_STATE root=0x(?P<root>[0-9A-Fa-f]{4}) sample=(?P<sample>[12]) '
    r'frame=(?P<frame>\d+) source_frame=(?P<source_frame>\d+) call=(?P<call>\d+) target=(?P<target>\d+) '
    r'fbpair=(?P<fbpair>\d+) instance=(?P<instance>\d+) color=0x(?P<color>[0-9A-Fa-f]{8}) '
    r'depth=0x(?P<depth>[0-9A-Fa-f]{8}) color_target=0x(?P<color_target>[0-9A-Fa-f]{8}) '
    r'depth_target=0x(?P<depth_target>[0-9A-Fa-f]{8}) overlap_tri=(?P<overlap_tri>\d+) '
    r'face_count=(?P<face_count>\d+) other_h=0x(?P<other_h>[0-9A-Fa-f]{8}) '
    r'other_l=0x(?P<other_l>[0-9A-Fa-f]{8}) alpha_compare=0x(?P<alpha_compare>[0-9A-Fa-f]{8}) '
    r'force_blend=(?P<force_blend>[01]) cvg_x_alpha=(?P<cvg_x_alpha>[01]) '
    r'alpha_cvg_sel=(?P<alpha_cvg_sel>[01]) zcmp=(?P<zcmp>[01]) zupd=(?P<zupd>[01]) '
    r'zmode=0x(?P<zmode>[0-9A-Fa-f]{8}) culling=(?P<culling>[01]) '
    r'scissor=(?P<scissor>-?\d+,-?\d+,-?\d+,-?\d+)$')
EXPECTED={0x12F0:8,0x1420:8,0x1538:10,0x1640:2,0x1708:10,0x1810:2,0x1938:64}


def parse(text:str)->tuple[list[dict],int]:
    parsed=[]; bad=0
    for line in text.splitlines():
        if '[JP-RT64] TARGET_STATE' not in line:continue
        m=RECORD.match(line)
        if not m:bad+=1;continue
        row=m.groupdict()
        for key in row:
            if key=='scissor':continue
            row[key]=int(row[key],16 if key in (
                'root','color','depth','color_target','depth_target','other_h',
                'other_l','alpha_compare','zmode') else 10)
        if row['root'] not in EXPECTED or row['frame']!=row['source_frame'] or row['overlap_tri']<1 or row['overlap_tri']>row['face_count']:
            bad+=1
            continue
        parsed.append(row)
    return parsed,bad


def summarize(text:str)->str:
    rows,bad=parse(text)
    if not rows:
        return f'No valid v9 target-state records. Invalid/mismatched: {bad}'
    group=defaultdict(list)
    for row in rows:group[(row['sample'],row['root'])].append(row)
    out=[]
    for sample in (1,2):
        present=[(root,group[(sample,root)]) for root in EXPECTED if group[(sample,root)]]
        if not present:continue
        out.append(f'Sample {sample}:')
        for root, rrows in present:
            # Same GameCall can be rendered repeatedly, and multiple GameCalls can share an instance ID.
            source={}
            inconsistent=0
            for r in rrows:
                key=(r['frame'],r['call'])
                if key in source and source[key]['overlap_tri']!=r['overlap_tri']:
                    inconsistent+=1
                else:source[key]=r
            unique=sum(r['overlap_tri'] for r in source.values())
            raw=sum(r['overlap_tri'] for r in rrows)
            targets=sorted({(r['target'],r['fbpair'],r['color'],r['depth']) for r in rrows})
            materials=sorted({(r['other_h'],r['other_l'],r['alpha_compare'],r['force_blend'],r['cvg_x_alpha'],r['alpha_cvg_sel'],r['zcmp'],r['zupd'],r['zmode'],r['culling']) for r in rrows})
            by_source=defaultdict(set)
            for r in rrows:
                by_source[(r['frame'],r['call'])].add((r['target'],r['color'],r['depth']))
            multiple_targets=sum(1 for t in by_source.values() if len(t)>1)
            extra=raw-unique
            out.append(f'  0x{root:04X}: unique={unique}/{EXPECTED[root]} raw={raw} repeats={extra} '
                       f'GameCalls={len(source)} targets={len(targets)} material_states={len(materials)} '
                       f'source_calls_across_targets={multiple_targets} inconsistent={inconsistent}')
            for target,fbpair,color,depth in targets:
                out.append(f'    target={target} fbpair={fbpair} color=0x{color:08X} depth=0x{depth:08X}')
            for h,l,a,b,c,d,zcmp,zupd,zmode,culling in materials:
                out.append(f'    state H=0x{h:08X} L=0x{l:08X} alpha=0x{a:08X} '
                           f'blend={b} coverage_alpha={c}/{d} zcmp={zcmp} zupd={zupd} '
                           f'zmode=0x{zmode:08X} cull={culling}')
    if bad:out.append(f'WARNING invalid/mismatched records={bad}')
    out.append('CPU host draw recording only; GPU execution/visibility require RenderDoc frame capture.')
    return '\n'.join(out)


def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path)
    a=p.parse_args()
    try:
        if a.log.stat().st_size>MAX_BYTES:raise ValueError('log exceeds 32MiB limit')
        print(summarize(a.log.read_text(encoding='utf-8',errors='replace')))
    except (ValueError,OSError) as exc:p.error(str(exc))
    return 0

if __name__=='__main__':raise SystemExit(main())