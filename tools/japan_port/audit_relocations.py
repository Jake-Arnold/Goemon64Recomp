#!/usr/bin/env python3
"""Compare relocation candidates to a trusted N64Recomp symbols TOML reference.

Compare the USA candidate inventory against pinned USA syms to expose exact
missing and extra records. Never transplant USA relocation sites to Japan.
"""
from __future__ import annotations
import argparse
import json
import tomllib
from collections import Counter
from pathlib import Path


def difference(reference: dict, candidate: dict) -> dict:
    expected={}
    for section in reference['section']:
        if not section['name'].startswith('.file_'):
            continue
        name=section['name'][1:]
        expected[name]=Counter((r['type'],r['vram'],r['target_vram'])
                               for r in section.get('relocs',[]))
    found={}
    for name, records in candidate.get('relocations',{}).items():
        if name not in expected:
            raise ValueError(f'Unknown candidate section: {name}')
        found[name]=Counter((r['type'],int(r['vram'],16),int(r['target_vram'],16))
                            for r in records)
    result={}; totals={'reference':0,'candidate':0,'exact_sections':0,'missing':0,'extra':0}
    for name, refs in expected.items():
        cand=found.get(name,Counter())
        missing=refs-cand; extra=cand-refs
        result[name]={
            'reference':sum(refs.values()), 'candidate':sum(cand.values()),
            'missing': [{'type':key[0],'vram':f'0x{key[1]:08X}',
                         'target_vram':f'0x{key[2]:08X}', 'count':count}
                        for key,count in sorted(missing.items(),key=lambda x:x[0][1])],
            'extra': [{'type':key[0],'vram':f'0x{key[1]:08X}',
                       'target_vram':f'0x{key[2]:08X}', 'count':count}
                      for key,count in sorted(extra.items(),key=lambda x:x[0][1])],
        }
        totals['reference']+=sum(refs.values())
        totals['candidate']+=sum(cand.values())
        totals['missing']+=sum(missing.values())
        totals['extra']+=sum(extra.values())
        totals['exact_sections']+=not missing and not extra
    return {'summary':{**totals,'sections':len(expected)},'per_section':result,
            'caveat':'Diagnostic USA reference differences; never transplant USA relocation records into Japan'}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--candidates',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    results=difference(tomllib.loads(args.reference.read_text()),
                       json.loads(args.candidates.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results['summary'],indent=2))

if __name__=='__main__': main()
