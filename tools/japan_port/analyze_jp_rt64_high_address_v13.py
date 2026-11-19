#!/usr/bin/env python3
"""Summarize v13 8 MiB RDRAM and offset-control samples for two exact loads."""
from __future__ import annotations
import argparse
from pathlib import Path
import re
from collections import defaultdict

ROW=re.compile(r'^\[JP-RT64\] TEX_REPLAY_LOAD\s+(.*)$')
FIELD=re.compile(r'(\w+)=([^\s]+)')
UNKNOWN=str(0xffffffff)
ADDRS={'0x0078B6E0','0x007953D0'}

def summarize(txt:str)->str:
    grouped=defaultdict(list)
    for line in txt.splitlines():
        m=ROW.match(line)
        if not m:continue
        d=dict(FIELD.findall(m.group(1)))
        if d.get('source_start') not in ADDRS:continue
        grouped[d['source_start']].append(d)
    seen=any(grouped.values())
    out=[]
    for addr in sorted(ADDRS):
        rows=grouped[addr]
        if not rows:
            out.append(f'{addr}: no samples');continue
        observations=set()
        for d in rows:
            high=d.get('source_nonzero64','?')
            low=d.get('candidate_minus_3c4000_nz64','?')
            before=d.get('tmem_nz_before','?')
            after=d.get('tmem_nz_after','?')
            observations.add((high,low,before,after))
        out.append(f'{addr}: samples={len(rows)}, distinct_observations={len(observations)}')
        for hi,lo,before,after in sorted(observations):
            h='UNREAD' if hi==UNKNOWN else ('NOT_LOGGED' if hi=='?' else hi+'/64')
            l='UNREAD' if lo==UNKNOWN else ('NOT_LOGGED' if lo=='?' else lo+'/64')
            out.append(f'  high_RDRAM_nz64={h} minus_0x003C4000_nz64={l} whole_TMEM_nz={before}->{after}')
            if hi=='0' and lo not in ('0','?',UNKNOWN):
                out.append('  FINDING: high source first64 all zero; lower-offset control has nonzero data (base-offset hypothesis strengthened, not proven)')
    if not seen:out.append('No matching loads; verify GOEMON_JP_RT64_TEX_TRACE=1, actor encountered, v13 installed.')
    out.append('A 64-byte source sample cannot prove an entire texture valid. No RDRAM remapping or texture changes were performed.')
    return '\n'.join(out)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log',type=Path)
    a=ap.parse_args()
    print(summarize(a.log.read_text(errors='replace')))
    return 0

if __name__=='__main__':raise SystemExit(main())