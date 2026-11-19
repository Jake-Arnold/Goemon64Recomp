#!/usr/bin/env python3
"""Summarise bounded source-memory and TMEM replay observations for robot textures.

No conclusions about unknown RDRAM bytes; source_nonzero64=4294967295 means
not sampled for safety. CPU source/TMEM values do not prove GPU decode content.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re

ROW=re.compile(r'^\[JP-RT64\] TEX_REPLAY_(TARGET|LOAD)\s+(.*)$')
FIELD=re.compile(r'(\w+)=([^\s]+)')
UNREAD=0xFFFFFFFF

def records(text:str)->list[dict]:
    out=[]
    for line in text.splitlines():
        match=ROW.match(line.strip())
        if match:out.append({'event':match.group(1),**dict(FIELD.findall(match.group(2)))})
    return out

def summarise(text:str, max_loads:int=12)->str:
    recs=records(text)
    roots=[]
    current=None
    for item in recs:
        if item['event']=='TARGET':
            current={'target':item,'loads':[]}
            roots.append(current)
        elif current is not None:
            if (item.get('hash'),item.get('frame'),item.get('call')) == (current['target'].get('hash'),current['target'].get('frame'),current['target'].get('call')):
                current['loads'].append(item)
    output=[f'v12 replay snapshots={len(roots)} load_rows={sum(len(x["loads"]) for x in roots)}']
    for group in roots:
        t=group['target']
        kind='ALL_ZERO' if t.get('total_tmem_nonzero')=='0' else 'NONZERO'
        output.append(f'  {kind} frame={t.get("frame")} call={t.get("call")} hash={t.get("hash")} '
            f'tmem_nonzero={t.get("total_tmem_nonzero")}/4096 preceding_loads={t.get("recent_loads")}')
        ls=group['loads']
        output.append(f'    observed_loads={len(ls)}; newest first (max {max_loads}):')
        for op in reversed(ls[-max_loads:]):
            snz=op.get('source_nonzero64','?')
            if snz==str(UNREAD):snz='UNREAD_OUT_OF_RANGE'
            elif snz!='?':snz=f'{snz}/64'
            before=op.get('tmem_nz_before','?');after=op.get('tmem_nz_after','?')
            output.append(f'    load_index={op.get("index")} type={op.get("type")} source_start={op.get("source_start")} '
                f'RDRAM_nz64={snz} tmem={op.get("tmem")} '
                f'whole_TMEM_nz={before}->{after} load_fmt/siz={op.get("load_fmt")}/{op.get("load_siz")} '
                f'tile_fmt/siz={op.get("tile_fmt")}/{op.get("tile_siz")}, line={op.get("line")}')
    if not roots:output.append('No v12 replay events: verify v12 installed and GOEMON_JP_RT64_TEX_TRACE=1; target hashes must be encountered.')
    output.append('Source_nonzero64 reads only 64 RDRAM bytes from a conservatively bounded address. Whole-TMEM counts are not tile-specific and do not prove GPU decoded pixels.')
    return '\n'.join(output)

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('log',type=Path)
    p.add_argument('--last-loads',type=int,default=12)
    a=p.parse_args()
    if a.last_loads<0:p.error('--last-loads must be >= 0')
    print(summarise(a.log.read_text(errors='replace'),a.last_loads))
    return 0
if __name__=='__main__':raise SystemExit(main())