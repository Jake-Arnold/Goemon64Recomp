#!/usr/bin/env python3
"""Bounded summary of read-only JP-RT64 v8 CPU->raster command records.

Counts cover *command recording*, not GPU execution or visible pixels.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import argparse, re

MAX_SIZE = 32 * 1024 * 1024
RANGE = re.compile(r'\[JP-RT64\] FACE_RANGE root=0x([0-9A-Fa-f]{4}) sample=([12]) frame=(\d+) first=(\d+) end=(\d+) triangles=(\d+)')
BUILT = re.compile(r'\[JP-RT64\] RASTER BUILT root=0x([0-9A-Fa-f]{4}) sample=([12]) frame=(\d+) instance=(\d+) call=(\d+) call_tri=(\d+) overlap_tri=(\d+) type=(\d+) scissor_empty=([01]) pipeline=([01])')
DRAW = re.compile(r'\[JP-RT64\] RASTER (DRAW_RECORDED|SKIP_SCISSOR) root=0x([0-9A-Fa-f]{4}) sample=([12]) instance=(\d+) call_tri=(\d+) overlap_tri=(\d+) empty_scissor=([01])')
SKIP = re.compile(r'\[JP-RT64\] RASTER SKIP_PROJECTION root=0x([0-9A-Fa-f]{4}) sample=([12]) call=(\d+) call_tri=(\d+) overlap_tri=(\d+)')
EXPECTED={0x12F0:8,0x1420:8,0x1538:10,0x1640:2,0x1708:10,0x1810:2,0x1938:64}

def summarize(text: str) -> str:
    data=defaultdict(lambda: {'range':0,'built':0,'recorded':0,'scissor':0,'projection':0,'bad_pipeline':0})
    errors=[]
    for line in text.splitlines():
        if '[JP-RT64]' not in line: continue
        if m:=RANGE.search(line):
            root,sample,frame,first,end,tri=m.groups()
            root=int(root,16); sample=int(sample); first=int(first); end=int(end); tri=int(tri)
            if root not in EXPECTED or tri!=EXPECTED[root] or end-first!=tri*3: errors.append('invalid FACE_RANGE')
            else: data[root,sample]['range'] += tri
        elif m:=BUILT.search(line):
            root,sample,frame,inst,call,calltri,overlap,kind,scissor,pipeline=m.groups()
            root=int(root,16); sample=int(sample); overlap=int(overlap)
            data[root,sample]['built']+=overlap
            if pipeline=='0':data[root,sample]['bad_pipeline']+=overlap
        elif m:=DRAW.search(line):
            kind,root,sample,inst,calltri,overlap,scissor=m.groups()
            row=data[int(root,16),int(sample)]
            row['recorded' if kind=='DRAW_RECORDED' else 'scissor']+=int(overlap)
        elif m:=SKIP.search(line):
            root,sample,call,calltri,overlap=m.groups()
            data[int(root,16),int(sample)]['projection']+=int(overlap)
    if not data:
        if errors:return 'WARNINGS: '+str(len(errors))+' malformed face ranges; no valid captures.'
        return 'No v8 [JP-RT64] raster trace records found.'
    out=[]
    for sample in (1,2):
        grouped=[data.get((root,sample)) for root in EXPECTED]
        valid=[x for x in grouped if x is not None]
        if not valid: continue
        out.append(f'Sample {sample}:')
        for root in EXPECTED:
            d=data.get((root,sample))
            if d is None:
                out.append(f'  0x{root:04X}: NO RANGE OR RASTER MATCH')
                continue
            out.append(f'  0x{root:04X}: range={d["range"]} built={d["built"]} '
                       f'gpu_command_recorded={d["recorded"]} skip_scissor={d["scissor"]} '
                       f'skip_projection={d["projection"]} missing_pipeline={d["bad_pipeline"]}')
        for field in ('range','built','recorded','scissor','projection','bad_pipeline'):
            out.append('  TOTAL '+field+'='+str(sum(d[field] for d in valid)))
    if errors:out.append('WARNINGS: '+str(len(errors))+' malformed face ranges')
    out.append('GPU command recording is NOT evidence of GPU execution or pixel visibility.')
    return '\n'.join(out)

def main()->int:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('log',type=Path);a=p.parse_args()
    try:
        if a.log.stat().st_size>MAX_SIZE:raise ValueError('log exceeds 32MiB')
        print(summarize(a.log.read_text(encoding='utf-8',errors='replace')))
    except (OSError,ValueError) as e:p.error(str(e))
    return 0

if __name__=='__main__':raise SystemExit(main())