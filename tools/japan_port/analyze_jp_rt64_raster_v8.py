#!/usr/bin/env python3
"""Summarize JP RT64 v8 robot raster trace, separating distinct GameCalls from repeats.

The same workload GameCall may be reprocessed by the renderer more than once.
Only distinct (root, sample, frame, GameCall) intersections count toward the
unique source triangle total. Raw host command *invocations* are counted
separately. Neither implies GPU execution or visible pixels.
"""
from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import argparse
import re

MAX_SIZE = 32 * 1024 * 1024
RANGE = re.compile(r'\[JP-RT64\] FACE_RANGE root=0x([0-9A-Fa-f]{4}) sample=([12]) frame=(\d+) first=(\d+) end=(\d+) triangles=(\d+)')
BUILT = re.compile(r'\[JP-RT64\] RASTER BUILT root=0x([0-9A-Fa-f]{4}) sample=([12]) frame=(\d+) instance=(\d+) call=(\d+) call_tri=(\d+) overlap_tri=(\d+) type=(\d+) scissor_empty=([01]) pipeline=([01])')
DRAW = re.compile(r'\[JP-RT64\] RASTER (DRAW_RECORDED|SKIP_SCISSOR) root=0x([0-9A-Fa-f]{4}) sample=([12]) instance=(\d+) call_tri=(\d+) overlap_tri=(\d+) empty_scissor=([01])')
SKIP = re.compile(r'\[JP-RT64\] RASTER SKIP_PROJECTION root=0x([0-9A-Fa-f]{4}) sample=([12]) call=(\d+) call_tri=(\d+) overlap_tri=(\d+)')
EXPECTED = {0x12F0: 8, 0x1420: 8, 0x1538: 10, 0x1640: 2, 0x1708: 10, 0x1810: 2, 0x1938: 64}


def summarize(log: str) -> str:
    """Deduplicate repeated *recordings* of the same GameCall, not real NPCs."""
    warnings: list[str] = []
    ranges: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    lines = [line for line in log.splitlines() if '[JP-RT64]' in line]

    # Establish the immutable provenance of every sampled face-index interval.
    for line in lines:
        m = RANGE.search(line)
        if m is None:
            continue
        root = int(m[1], 16)
        sample, frame, first, end, tri = map(int, m.groups()[1:])
        key = (root, sample)
        value = (frame, first, end, tri)
        if root not in EXPECTED or tri != EXPECTED.get(root) or end - first != tri * 3:
            warnings.append('invalid FACE_RANGE')
        elif key in ranges and ranges[key] != value:
            warnings.append('conflicting FACE_RANGE')
        else:
            ranges[key] = value

    # A key identifies source triangle provenance. It is *not* a renderer
    # instance ID, because those IDs are reused between rendering passes.
    calls: dict[tuple[int, int, int, int], dict] = {}
    pending = defaultdict(deque)  # (root,sample,instance,call_tri,overlap) -> FIFO keys
    for line in lines:
        if m := BUILT.search(line):
            root = int(m[1], 16)
            sample, frame, instance, call, call_tri, overlap, kind, scissor, pipeline = map(int, m.groups()[1:])
            if (root, sample) not in ranges or ranges[root, sample][0] != frame:
                warnings.append('RASTER BUILT without matching FACE_RANGE/frame')
                continue
            if overlap < 1 or overlap > call_tri:
                warnings.append('invalid built overlap')
                continue
            identity = (root, sample, frame, call)
            if identity not in calls:
                calls[identity] = {'overlap': overlap, 'built': 0, 'draw': 0, 'scissor': 0,
                                   'projection': 0, 'bad_pipeline': 0}
            rec = calls[identity]
            if rec['overlap'] != overlap:
                warnings.append('conflicting overlap for same GameCall')
                continue
            rec['built'] += 1
            rec['bad_pipeline'] += int(not pipeline)
            pending[(root, sample, instance, call_tri, overlap)].append(identity)
        elif m := DRAW.search(line):
            event = m[1]
            root = int(m[2], 16)
            sample, instance, call_tri, overlap, scissor = map(int, m.groups()[2:])
            tag = (root, sample, instance, call_tri, overlap)
            if not pending[tag]:
                warnings.append('DRAW/SKIP_SCISSOR without matching BUILT event')
                continue
            rec = calls[pending[tag].popleft()]
            rec['draw' if event == 'DRAW_RECORDED' else 'scissor'] += 1
        elif m := SKIP.search(line):
            root = int(m[1], 16)
            sample, call, call_tri, overlap = map(int, m.groups()[1:])
            if (root, sample) not in ranges:
                warnings.append('SKIP_PROJECTION without matching FACE_RANGE')
                continue
            frame = ranges[root, sample][0]
            identity = (root, sample, frame, call)
            if identity not in calls:
                calls[identity] = {'overlap': overlap, 'built': 0, 'draw': 0, 'scissor': 0,
                                   'projection': 0, 'bad_pipeline': 0}
            rec = calls[identity]
            if rec['overlap'] != overlap:
                warnings.append('conflicting projection overlap')
                continue
            rec['projection'] += 1

    out = []
    for sample in (1, 2):
        if not any(s == sample for _, s in ranges) and not any(s == sample for _, s, _, _ in calls):
            continue
        out.append(f'Sample {sample}:')
        totals = defaultdict(int)
        for root in EXPECTED:
            rg = ranges.get((root, sample))
            matches = [v for (r, s, _, _), v in calls.items() if r == root and s == sample]
            if rg is None:
                out.append(f'  0x{root:04X}: NO FACE_RANGE')
                continue
            source = rg[3]
            built = sum(v['overlap'] for v in matches if v['built'])
            recorded = sum(v['overlap'] for v in matches if v['draw'])
            skipped_scissor = sum(v['overlap'] for v in matches if v['scissor'] and not v['draw'])
            skipped_projection = sum(v['overlap'] for v in matches if v['projection'] and not v['built'])
            missing_pipeline = sum(v['overlap'] for v in matches if v['bad_pipeline'])
            raw_built = sum(v['overlap'] * v['built'] for v in matches)
            raw_recorded = sum(v['overlap'] * v['draw'] for v in matches)
            repeat_built = raw_built - built
            repeat_recorded = raw_recorded - recorded
            row = {'range': source, 'built': built, 'recorded': recorded,
                   'scissor': skipped_scissor, 'projection': skipped_projection,
                   'bad_pipeline': missing_pipeline, 'raw_recorded': raw_recorded,
                   'repeat_built': repeat_built, 'repeat_recorded': repeat_recorded}
            for field, value in row.items():
                totals[field] += value
            out.append(f'  0x{root:04X}: range={source} built={built} '
                       f'gpu_command_recorded={recorded} skip_scissor={skipped_scissor} '
                       f'skip_projection={skipped_projection} missing_pipeline={missing_pipeline} '
                       f'repeat_recorded={repeat_recorded}')
            if built > source or recorded > source:
                warnings.append(f'root=0x{root:04X} unique triangles exceed source range')
        for field in ('range', 'built', 'recorded', 'scissor', 'projection', 'bad_pipeline',
                      'raw_recorded', 'repeat_built', 'repeat_recorded'):
            out.append(f'  TOTAL {field}={totals[field]}')
    if warnings:
        out.append(f'WARNINGS: {len(warnings)} ({"; ".join(sorted(set(warnings))[:4])})')
    if not ranges and not calls:
        if warnings:
            return '\n'.join(out) + '\nNo valid v8 robot ranges.'
        return 'No v8 [JP-RT64] raster trace records found.'
    out.append('Raw recordings may repeat the same GameCalls; unique source geometry is counted once per frame/root/sample/call.')
    out.append('GPU command recording is NOT evidence of GPU execution or pixel visibility.')
    return '\n'.join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    a = p.parse_args()
    try:
        if a.log.stat().st_size > MAX_SIZE:
            raise ValueError('log exceeds 32MiB')
        print(summarize(a.log.read_text(encoding='utf-8', errors='replace')))
    except (OSError, ValueError) as e:
        p.error(str(e))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())