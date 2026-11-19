#!/usr/bin/env python3
"""Correlate bounded RT64 v10 32x64 texture-origin records from a game log.

Resource #112003 and cache index 89 were from one RenderDoc capture and are
NOT stable across process launches. Prefer resolving by hash or content evidence.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from pathlib import Path
import re

START=re.compile(r'^\[JP-RT64\] TEX_(QUEUE|CREATE|ADD|BIND)\s+(.*)$')
FIELD=re.compile(r'(\w+)=([^\s]+)')
TYPES=['QUEUE','CREATE','ADD','BIND']


def read_rows(contents:str)->list[dict]:
    rows=[]
    for n,line in enumerate(contents.splitlines(),1):
        m=START.match(line.strip())
        if m is None:continue
        values=dict(FIELD.findall(m.group(2)))
        if 'hash' not in values:continue
        rows.append({'event':m.group(1),'line':n,**values})
    return rows


def summarize(rows:list[dict],serial:str|None=None,cache_index:int|None=None,limit:int=25)->str:
    groups=defaultdict(list)
    for row in rows:groups[row['hash'].lower()].append(row)
    selected_hashes=set(groups)
    if serial is not None:
        selected_hashes={h for h,g in groups.items() if any(x['event']=='CREATE' and x.get('serial')==serial for x in g)}
    if cache_index is not None:
        by_idx={h for h,g in groups.items() if any(x.get('cache_index')==str(cache_index) and x['event'] in {'ADD','BIND'} for x in g)}
        selected_hashes &= by_idx
    output=[f'32x64 texture events={len(rows)} hashes={len(groups)} matched_hashes={len(selected_hashes)}']
    ranked=sorted(selected_hashes,key=lambda h:(-sum(1 for r in groups[h] if r['event']=='BIND'),h))
    shown=ranked[:limit] if limit>0 else ranked
    if len(shown)<len(ranked):output.append(f'  showing {len(shown)} hashes with most binds; use --limit 0 for all')
    for h in shown:
        g=groups[h]
        events={e:[r for r in g if r['event']==e] for e in TYPES}
        serials=sorted({r['serial'] for r in events['CREATE'] if 'serial' in r})
        indices=sorted({r['cache_index'] for r in events['ADD']+events['BIND'] if 'cache_index' in r},key=int)
        unique_queue={(r.get('decode'),r.get('tmem_bytes'),r.get('nonzero'),r.get('fingerprint')) for r in events['QUEUE']}
        hits=sum(r.get('hit')=='1' for r in events['BIND'])
        misses=sum(r.get('hit')=='0' for r in events['BIND'])
        output.append(f'  hash={h} serial={",".join(serials) or "?"} cache_index={",".join(indices) or "?"} '
                      f'queue={len(events["QUEUE"])} create={len(events["CREATE"])} '
                      f'add={len(events["ADD"])} bind_hit={hits} bind_miss={misses}')
        for decode,nbytes,nonzero,fingerprint in sorted(unique_queue,key=str):
            output.append(f'    TMEM decode={decode or "?"} bytes={nbytes or "?"} '
                          f'nonzero={nonzero or "?"} fingerprint={fingerprint or "?"}')
        if len(serials)>1:output.append('    WARNING: hash associated with multiple created resources')
        if events['BIND'] and not events['QUEUE']:
            output.append('    NOTE: upload not observed in this logging session / logging cap reached')
        if events['QUEUE'] and any(x.get('decode')=='1' and x.get('nonzero')=='0' for x in events['QUEUE']):
            output.append('    FINDING: input TMEM buffer was entirely zero at queue time')
        if events['QUEUE'] and any(x.get('decode')=='1' and x.get('nonzero') not in ('0',None) for x in events['QUEUE']):
            output.append('    FINDING: full 4096-byte TMEM snapshot had nonzero bytes; relevant tile region not yet proven nonzero')
    if not selected_hashes:output.append('No matching hash. Cache index and resource serial can change between runs.')
    output.append('No GPU readback: these events do not prove decoded pixel contents. v10 is research-only.')
    return '\n'.join(output)


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('log',type=Path)
    p.add_argument('--serial',help='Texture Cache RGBA32 resource serial in THIS execution')
    p.add_argument('--cache-index',type=int,help='Cache slot observed in THIS execution')
    p.add_argument('--limit',type=int,default=25,help='Maximum hash groups shown (0 for all)')
    a=p.parse_args()
    print(summarize(read_rows(a.log.read_text(errors='replace')),a.serial,a.cache_index,a.limit))
    return 0

if __name__=='__main__':raise SystemExit(main())