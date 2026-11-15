#!/usr/bin/env python3
"""Produce an explicitly INCOMPLETE Japan N64Recomp TOML candidate map.

Combines Splat-extracted function sections with conservatively audited
intra-overlay relocation candidates. This is *not* suitable for a playable
build until all relocation sites, required symbols and branches are checked.
"""
from __future__ import annotations
import argparse
import json
import re
import tomllib
from pathlib import Path

JP_DECOMP = '6f8745fecc3a5e7d4918c7a73353eb0726116ded'
TYPES = {'R_MIPS_HI16','R_MIPS_LO16','R_MIPS_26'}
BLOCK = re.compile(r'(?=^\[\[section\]\]$)', re.M)


def merge(symbols: str, inventory: dict) -> tuple[str, dict]:
    if inventory.get('source_sha1') != JP_DECOMP:
        raise ValueError('Relocation candidates must come from verified Japanese decompressed ROM')
    symbol_sections=tomllib.loads(symbols)['section']
    section_map={s['name']:s for s in symbol_sections}
    if len(section_map)!=len(symbol_sections):
        raise ValueError('Duplicate symbol section names')
    if not section_map:
        raise ValueError('No candidate sections')
    records=inventory.get('relocations',{})
    seen=set();count=0
    for name, items in records.items():
        k='.'+name
        if k not in section_map:
            raise ValueError(f'Unknown candidate relocation section {k}')
        sec=section_map[k]
        if sec['vram'] != 0x08000000:
            raise ValueError(f'Relocations cannot be applied to static section {k}')
        for item in items:
            ty=item['type']; site=int(item['vram'],16); target=int(item['target_vram'],16)
            if ty not in TYPES:
                raise ValueError(f'Unknown relocation type {ty}')
            if not sec['vram'] <= site < sec['vram'] + sec['size']:
                raise ValueError(f'{k}: relocation site out of bounds: {site:08X}')
            if not sec['vram'] <= target < sec['vram'] + sec['size']:
                raise ValueError(f'{k}: relocation target out of bounds: {target:08X}')
            key=(k,site)
            if key in seen:
                raise ValueError(f'Duplicate relocation site {k} {site:08X}')
            seen.add(key);count+=1
    if count != inventory.get('candidate_relocations'):
        raise ValueError('Candidate total does not match inventory')
    text=[
        '# INCOMPLETE JAPAN N64RECOMP CANDIDATE MAP. NOT READY FOR PC BOOT.',
        '# Missing unresolved relocations, data symbols and indirect targets.',
        '# Based on Japanese decompressed SHA-1 '+JP_DECOMP,
        '',
    ]
    parts=BLOCK.split(symbols)
    # Split at section boundaries and keep the complete originals.
    header=parts[0]
    if header.strip():
        text.append(header.rstrip()+'\n')
    for section,index in zip(parts[1:], range(len(symbol_sections))):
        name=symbol_sections[index]['name']
        if not re.search(r'^name\s*=\s*"'+re.escape(name)+r'"$',section,re.M):
            raise ValueError('Section order/name mismatch')
        matches=re.findall(r'^functions\s*=\s*\[$',section,re.M)
        if len(matches)!=1:
            raise ValueError(f'{name} missing a single functions block')
        items=records.get(name.lstrip('.'),[])
        if items:
            buf=['relocs = [']
            for item in sorted(items,key=lambda r:int(r['vram'],16)):
                buf.append('    { type = "'+item['type']+'", vram = '+item['vram']+', target_vram = '+item['target_vram']+' },')
            buf.extend([']',''])
            section=section.replace('functions = [','\n'.join(buf)+'\nfunctions = [',1)
        text.append(section.rstrip()+'\n')
    merged='\n'.join(text).rstrip()+'\n'
    verify=tomllib.loads(merged)['section']
    if len(verify)!=len(symbol_sections) or sum(len(s.get('relocs',[])) for s in verify)!=count:
        raise ValueError('Merged TOML failed structural check')
    return merged,{'sections':len(symbol_sections),'functions':sum(len(s['functions']) for s in verify),'relocations':count,'warning':'Provisional candidate metadata, not ready to execute'}


def main() -> None:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--candidate-symbols',type=Path,required=True)
    cli.add_argument('--candidate-relocations',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args=cli.parse_args()
    if args.output in (args.candidate_symbols,args.candidate_relocations):
        cli.error('Refusing to overwrite inputs')
    data,summary=merge(args.candidate_symbols.read_text(),json.loads(args.candidate_relocations.read_text()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(data)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
