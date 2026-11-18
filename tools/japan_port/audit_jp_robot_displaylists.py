#!/usr/bin/env python3
"""Read-only ROM-authenticated audit for Japanese robot's seven nested F3DEX lists.

Requires the user's original normalized Japanese retail ROM, but prints only
counts and address classifications. Never copies proprietary resource bytes.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import struct

ORIGINAL_SHA1 = '9843ee979b5f6c80f5eda85df0baed9ae7c4e73b'
FILE_ID=0x197
ROM_TABLE=0x58258
FILE_SHA256='470489e151c6375cdd4844084a4299e4a1f0809e8de5d7f7420832eda893041e'
LISTS={
    0x12F0:(0x13F0,32,8,(9,)),
    0x1420:(0x1520,32,8,(9,)),
    0x1538:(0x1628,30,10,(9,)),
    0x1640:(0x16F0,22,2,(10,)),
    0x1708:(0x17F8,30,10,(9,)),
    0x1810:(0x18C0,22,2,(10,)),
    0x1938:(0x1C38,96,64,(12,9,11)),
}


def decode_lzkn64(src:bytes,maxout:int=0x100000)->bytes:
    if len(src)<4:
        raise ValueError('short compressed resource')
    compressed_size=int.from_bytes(src[:4],'big')
    if not (4<=compressed_size<=len(src)):
        raise ValueError('bad resource size header')
    out=bytearray();i=4
    while i<compressed_size:
        cmd=src[i];i+=1
        if cmd<=0x7F:
            if i>=compressed_size: raise ValueError('short LZ backref')
            length=((cmd&0x7C)>>2)+2
            offset=((cmd&3)<<8)|src[i];i+=1
            if offset==0 or offset>len(out):raise ValueError('invalid LZ backref')
            for _ in range(length): out.append(out[-offset])
        elif cmd<=0x9F:
            length=cmd&0x1F
            if i+length>compressed_size:raise ValueError('short literal')
            out.extend(src[i:i+length]);i+=length
        elif cmd<=0xDF:
            if i>=compressed_size:raise ValueError('short RLE')
            out.extend(bytes([src[i]])*((cmd&0x1F)+2));i+=1
        elif cmd<=0xFE:out.extend(bytes((0,))*((cmd&0x1F)+2))
        else:
            if i>=compressed_size:raise ValueError('short long-zero RLE')
            out.extend(bytes((0,))*(src[i]+2));i+=1
        if len(out)>maxout:raise ValueError('decompression cap exceeded')
    return bytes(out)


def audit(rom:bytes)->list[dict]:
    if len(rom)!=0x1000000 or hashlib.sha1(rom).hexdigest()!=ORIGINAL_SHA1:
        raise ValueError('requires exact original normalized Japan rev-0 16-MiB ROM')
    start=struct.unpack_from('>I',rom,ROM_TABLE+4*(FILE_ID-1))[0]
    end=struct.unpack_from('>I',rom,ROM_TABLE+4*FILE_ID)[0]
    if not (start&0x80000000):raise ValueError('expected compressed file 0x197')
    lo=start&0x7FFFFFFF;hi=end&0x7FFFFFFF
    if not (0x1000<=lo<hi<=len(rom)):
        raise ValueError('bad file table for model file 0x197')
    data=decode_lzkn64(rom[lo:hi])
    if len(data)!=15120 or hashlib.sha256(data).hexdigest()!=FILE_SHA256:
        raise ValueError('original model resource content mismatch')
    output=[]
    for start,(stop,expected_count,expected_tri,expected_texture_segments) in LISTS.items():
        if stop>len(data):raise ValueError('list exceeds resource')
        commands=[]
        for off in range(start,stop,8):
            w0,w1=struct.unpack_from('>II',data,off)
            commands.append((w0>>24,w1))
        count=len(commands)
        encoded_tris=sum(2 if op==0xB1 else 1 if op==0xBF else 0 for op,_ in commands)
        textures=tuple((word>>24)&15 for op,word in commands if op==0xFD)
        if (count,encoded_tris,textures)!=(expected_count,expected_tri,expected_texture_segments):
            raise ValueError(f'original display list changed at 0x{start:04X}')
        if commands[-1][0]!=0xB8 or any(op==0xB8 for op,_ in commands[:-1]):
            raise ValueError(f'list does not end at expected offset 0x{stop:X}')
        output.append({'root':start,'commands':count,'triangles':encoded_tris,'texture_segments':textures})
    return output


def main()->int:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--original-rom',required=True,type=Path)
    a=cli.parse_args()
    try: rows=audit(a.original_rom.read_bytes())
    except (OSError,ValueError) as e:cli.error(str(e))
    print('Original Japanese ROM: authenticated; resource 0x197: authenticated')
    for row in rows:
        print('list=0x%04X commands=%d encoded_triangles=%d texture_segments=%s' %
              (row['root'],row['commands'],row['triangles'],','.join('%X'%x for x in row['texture_segments'])))
    print('TOTAL lists=%d commands=%d encoded_triangles=%d'%
          (len(rows),sum(x['commands'] for x in rows),sum(x['triangles'] for x in rows)))
    return 0

if __name__=='__main__':raise SystemExit(main())