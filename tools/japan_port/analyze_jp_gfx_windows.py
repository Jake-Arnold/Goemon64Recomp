#!/usr/bin/env python3
"""Compare bounded guest Gfx windows from read-only JP native trace v3.

No emulator access or modifications. Prints metadata only; never emits raw
Gfx words, user paths, actor pointers or copyrighted game memory contents.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re

MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_COMMANDS = 64
BEGIN = re.compile(r'\[JP-MODEL3\] BEGIN actor=0x([0-9A-Fa-f]{8}) gen=(\d+) model=0x([0-9A-Fa-f]{4}) mode=([14]) sample=([12]) source=0x([0-9A-Fa-f]{8}) start=0x([0-9A-Fa-f]{8}) end=0x([0-9A-Fa-f]{8}) commands=(\d+)\Z')
CMD = re.compile(r'\[JP-MODEL3\] CMD mode=([14]) sample=([12]) index=(\d+) w0=([0-9A-Fa-f]{8}) w1=([0-9A-Fa-f]{8})\Z')
END = re.compile(r'\[JP-MODEL3\] END mode=([14]) sample=([12]) commands=(\d+)\Z')


def parse(source: str) -> dict[tuple[int,int],dict]:
    windows = {}
    current = None
    for line in source.splitlines():
        pos = line.find('[JP-MODEL3]')
        if pos < 0:
            continue
        message = line[pos:]
        if match := BEGIN.fullmatch(message):
            if current is not None:
                raise ValueError('nested capture BEGIN')
            actor, gen, model, mode, sample, src, start, end, length = match.groups()
            mode, sample, length = int(mode), int(sample), int(length)
            start, end = int(start,16), int(end,16)
            if (mode,sample) in windows:
                raise ValueError('duplicate mode/sample capture')
            if length <= 0 or length > MAX_COMMANDS or end-start != length * 8:
                raise ValueError('invalid bounded capture length')
            current = {'key':(mode,sample),'length':length, 'model':int(model,16),
                       'commands':[], 'gen':int(gen), 'actor':actor,
                       'source':int(src,16)}
        elif match := CMD.fullmatch(message):
            if current is None:
                raise ValueError('CMD without BEGIN')
            mode,sample,index,w0,w1=match.groups()
            if (int(mode),int(sample)) != current['key'] or int(index) != len(current['commands']):
                raise ValueError('wrong command index or capture key')
            if len(current['commands']) >= current['length']:
                raise ValueError('too many Gfx commands')
            current['commands'].append((int(w0,16),int(w1,16)))
        elif match := END.fullmatch(message):
            if current is None:
                raise ValueError('END without BEGIN')
            mode,sample,length=map(int,match.groups())
            if ((mode,sample) != current['key'] or length != current['length'] or
                    len(current['commands']) != length):
                raise ValueError('incomplete or mismatched capture')
            windows[current['key']] = current
            current = None
        else:
            raise ValueError(f'unrecognized v3 trace record: {message[:80]}')
    if current is not None:
        raise ValueError('incomplete trailing capture')
    return windows


def compare(a: dict,b: dict) -> dict:
    left, right = a['commands'], b['commands']
    common = min(len(left),len(right))
    return {
        'same_length':len(left)==len(right),
        'same_opcode_sequence':[w0>>24 for w0,_ in left]==[w0>>24 for w0,_ in right],
        'first_word_changed':[i for i in range(common) if left[i][0] != right[i][0]],
        'second_word_changed':[i for i in range(common) if left[i][1] != right[i][1]],
        'opcode_changed':[i for i in range(common) if (left[i][0]>>24)!=(right[i][0]>>24)],
    }


def summarize(windows: dict) -> str:
    if not windows:
        return 'No complete [JP-MODEL3] captures found.'
    lines=[]
    for mode in (1,4):
        samples=[(k[1],v) for k,v in windows.items() if k[0]==mode]
        samples.sort()
        if not samples:
            lines.append(f'Mode {mode}: no complete capture')
            continue
        for sample,window in samples:
            ops=Counter(w0>>24 for w0,_ in window['commands'])
            opstr=' '.join(f'0x{k:02X}:{v}' for k,v in sorted(ops.items()))
            lines.append(f'Mode {mode} sample {sample}: {window["length"]} commands, model=0x{window["model"]:04X}, generation={window["gen"]}, opcode counts [{opstr}]')
        if len(samples)==2:
            d=compare(samples[0][1],samples[1][1])
            lines.append('Mode %u comparison: same_count=%s same_opcode_sequence=%s w0_changed=%u w1_changed=%u opcode_changed=%u' % (
                mode, d['same_length'], d['same_opcode_sequence'],len(d['first_word_changed']),
                len(d['second_word_changed']),len(d['opcode_changed'])))
            for key in ['first_word_changed','second_word_changed','opcode_changed']:
                indices=d[key]
                lines.append(f'  {key} indexes (first 16): {indices[:16]}')
    lines.append('These are guest display-list buffer writes, not confirmed RT64/RSP/GPU processing.')
    return '\n'.join(lines)


def main() -> int:
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('log',type=Path)
    args=cli.parse_args()
    try:
        if args.log.stat().st_size > MAX_LOG_BYTES:
            raise ValueError('trace log exceeds 32 MiB cap')
        raw=args.log.read_text(encoding='utf-8',errors='replace')
        print(summarize(parse(raw)))
    except (ValueError,OSError) as exc:
        cli.error(str(exc))
    return 0


if __name__=='__main__':
    raise SystemExit(main())