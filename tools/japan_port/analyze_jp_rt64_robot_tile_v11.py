#!/usr/bin/env python3
"""Join RT64 v11 robot GameCall tiles to v10 32x64 upload/cache records.

Strictly offline. Names, cache slots and resource serials apply only to the
same process execution. Never assume prior RenderDoc indices remain stable.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).parent))
from analyze_jp_rt64_texture_origin_v10 import read_rows

ROBOT_START=re.compile(r'^\[JP-RT64\] TEX_ROBOT_(CALL|TILE)\s+(.*)$')
FIELD=re.compile(r'(\w+)=([^\s]+)')


def _as_int(text:str,default=0):
    try:return int(text,0)
    except (TypeError, ValueError):return default


def robot_rows(content:str)->list[dict[str,str]]:
    result=[]
    for line in content.splitlines():
        m=ROBOT_START.match(line.strip())
        if m:
            attrs=dict(FIELD.findall(m.group(2)))
            result.append({'kind':m.group(1),**attrs})
    return result


def summarize(contents:str,only_root:str|None=None)->str:
    robots=robot_rows(contents)
    textures=read_rows(contents)
    bins=defaultdict(lambda:defaultdict(list))
    for row in textures:
        bins[row['hash'].lower()][row['event']].append(row)
    count=Counter(t['event'] for t in textures)
    all_calls={(r.get('frame'),r.get('root'),r.get('sample'),r.get('call')) for r in robots if r['kind']=='CALL'}
    output=[f'v11 robot records: calls={sum(r["kind"]=="CALL" for r in robots)} '
            f'tiles={sum(r["kind"]=="TILE" for r in robots)} '
            f'32x64 trace binds={count["BIND"]}']
    if count['BIND']>=30000:
        output.append('  WARNING: v10 30000 TEX_BIND log cap reached; absence of bind records is NOT a cache miss')
    if not robots:
        output.append('No TEX_ROBOT records: need v11 install and GOEMON_JP_RT64_TRACE=1 plus GOEMON_JP_RT64_TEX_TRACE=1. Robot range must be observed.')
        return '\n'.join(output)
    grouped=defaultdict(list)
    for r in robots:
        if only_root and r.get('root','').lower()!=only_root.lower():continue
        if r['kind']=='TILE':grouped[(r.get('root'),r.get('sample'))].append(r)
    for root,sample in sorted(grouped,key=lambda z:(_as_int(z[0]),_as_int(z[1]))):
        arr=grouped[(root,sample)]
        unique={ (r.get('call'),r.get('slot'),r.get('hash',''),r.get('copy','')):r for r in arr }
        hashes={r.get('hash','').lower() for r in unique.values() if r.get('valid')=='1' and r.get('copy')=='0' and r.get('hash')}
        dims=defaultdict(list)
        for r in unique.values():
            if r.get('hash') and r.get('valid')=='1' and r.get('copy')=='0':
                dims[(r.get('requested'),r.get('hash').lower())].append(r.get('call'))
        output.append(f'  robot root={root} sample={sample}: tile_rows={len(arr)} unique_call_tiles={len(unique)} '
                      f'normal_texture_hashes={len(hashes)}')
        for (dim,h),calls in sorted(dims.items(),key=lambda z:(z[0][0] != '32x64',z[0][0],z[0][1])):
            hist=bins.get(h,{})
            queue=hist.get('QUEUE',[])
            creation=hist.get('CREATE',[])
            add=hist.get('ADD',[])
            bind=hist.get('BIND',[])
            indices=','.join(sorted({x.get('cache_index','?') for x in add+bind},key=str)) or '?'
            serial=','.join(sorted({x.get('serial','?') for x in creation},key=str)) or '?'
            hits=sum(x.get('hit')=='1' for x in bind)
            misses=sum(x.get('hit')=='0' for x in bind)
            output.append(f'    {dim or "?"} hash={h} calls={",".join(sorted(set(calls),key=lambda x:_as_int(x)))} '
                          f'queue={len(queue)} create={len(creation)} add={len(add)} '
                          f'bind_hit={hits} bind_miss={misses} serial={serial} cache_index={indices}')
            for nn,fmt,siz,tmem,line in sorted({(x.get('nonzero','?'),x.get('fmt','?'),x.get('siz','?'),x.get('tmem','?'),x.get('line','?')) for x in queue}):
                output.append(f'      full_TMEM_nonzero={nn}/4096 fmt={fmt} siz={siz} tmem={tmem} line={line}')
        for r in unique.values():
            if r.get('copy')=='1':output.append(f'    NOTE: call {r.get("call")} slot {r.get("slot")} is a framebuffer tile copy, not a TMEM-cache hash')
            elif r.get('valid')=='0':output.append(f'    NOTE: call {r.get("call")} slot {r.get("slot")} invalid')
    if only_root and not grouped:
        output.append(f'No tile rows for root={only_root}; inspect TEX_ROBOT_CALL records for tile_count=0.')
    output.append('Source tile association confirmed only for GameCalls matched by robot face ranges; GPU decoded pixels still require a matching-frame RenderDoc or readback.')
    return '\n'.join(output)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('log',type=Path)
    p.add_argument('--root',help='Filter one display-list root, e.g. 0x1938')
    args=p.parse_args()
    print(summarize(args.log.read_text(errors='replace'),args.root))
    return 0

if __name__=='__main__':raise SystemExit(main())