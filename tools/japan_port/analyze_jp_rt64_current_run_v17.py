#!/usr/bin/env python3
"""Read-only classification of current-run robot TMEM replay source histories.

Analyzes only [JP-RT64] TEX_REPLAY_TARGET and matching TEX_REPLAY_LOAD
metadata from one existing log. It does not assume old run addresses recur.
No ROM, graphics data, or host GPU bytes are read.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re

TARGET_HASH = 0x8042C12B60EC2B4E
LINE = re.compile(r'^\[JP-RT64\] TEX_REPLAY_(TARGET|LOAD)\s+(.*)$')
FIELD = re.compile(r'([A-Za-z_][A-Za-z_0-9]*)=([^\s]+)')
UNKNOWN = 0xFFFFFFFF


def number(row: dict[str, str], key: str) -> int | None:
    value = row.get(key)
    try:
        n = int(value, 0) if value is not None else None
    except ValueError:
        return None
    return n if n is None or n >= 0 else None


def count64(row: dict[str, str]) -> str:
    n = number(row, 'source_nonzero64')
    if n is None:
        return 'NOT_LOGGED'
    if n == UNKNOWN:
        return 'UNREAD'
    return f'{n}/64'


def parse(lines) -> tuple[list[dict], Counter]:
    snapshots = []
    current = None
    counts = Counter()
    for line in lines:
        match = LINE.match(line)
        if match is None:
            continue
        event, rest = match.groups()
        f = dict(FIELD.findall(rest))
        if event == 'TARGET':
            counts['all_targets'] += 1
            current = None
            if number(f, 'hash') == TARGET_HASH:
                current = {'target': f, 'loads': []}
                snapshots.append(current)
                counts['selected_targets'] += 1
        elif current is not None:
            t = current['target']
            if all(f.get(k) == t.get(k) for k in ('frame', 'call', 'hash')):
                limit = number(t, 'recent_loads')
                if limit is None or len(current['loads']) < limit:
                    current['loads'].append(f)
                else:
                    counts['over_limit_rows'] += 1
            else:
                counts['unmatched_rows'] += 1
    return snapshots, counts


def summarize(lines) -> str:
    snapshots, counters = parse(lines)
    out = ['JP v17 same-run robot texture provenance (read-only)',
           f"robot_hash=0x{TARGET_HASH:016X} targets={len(snapshots)} "
           f"other_hash_targets={counters['all_targets'] - len(snapshots)}"]
    if not snapshots:
        out.append('NO TARGETS: verify this log contains TEX_REPLAY_TARGET events for the robot hash.')
        return '\n'.join(out)
    empties = sum(number(s['target'], 'total_tmem_nonzero') == 0 for s in snapshots)
    nonzero = sum(number(s['target'], 'total_tmem_nonzero') not in (None, 0) for s in snapshots)
    absent = len(snapshots) - empties - nonzero
    out.append(f'target whole-TMEM: zero={empties} nonzero={nonzero} unreported={absent}; '
               'these counts cover ALL 4096 bytes, not just one tile')
    out.append(f"load rows={sum(len(s['loads']) for s in snapshots)} "
               f"unmatched={counters['unmatched_rows']} "
               f"over_target_limit={counters['over_limit_rows']}")
    source_stats = defaultdict(lambda: {'rows': 0, 'nz': Counter(), 'drops': 0, 'examples': Counter()})
    no_clear = 0
    dropped_snapshots = 0
    incomplete = 0
    for i, s in enumerate(snapshots, 1):
        t = s['target']
        loads = s['loads']
        expected = number(t, 'recent_loads')
        if expected is not None and len(loads) != expected:
            incomplete += 1
        drops = []
        for row in loads:
            src = row.get('source_start', 'NOT_LOGGED')
            stats = source_stats[src]
            stats['rows'] += 1
            stats['nz'][count64(row)] += 1
            a, b = number(row, 'tmem_nz_before'), number(row, 'tmem_nz_after')
            if a is not None and b is not None and a > 0 and b == 0:
                stats['drops'] += 1
                drops.append(row)
            stats['examples'][(row.get('source_tex', '?'), row.get('type', '?'),
                               row.get('width', '?'), row.get('load_siz', '?'))] += 1
        if drops:
            dropped_snapshots += 1
        else:
            no_clear += 1
        label = ', '.join(f"{r.get('source_start', '?')} (load={r.get('index', '?')}, "
                          f"src64={count64(r)}, {r.get('tmem_nz_before', '?')}->0)"
                          for r in drops)
        if not label:
            label = 'NONE in recorded replay window'
        out.append(f"target#{i} frame={t.get('frame','?')} call={t.get('call','?')} "
                   f"tmem={t.get('total_tmem_nonzero','?')}/4096 "
                   f"loads={len(loads)}/{expected if expected is not None else '?'} "
                   f"nonzero_to_zero=[{label}]")
    out.append(f'windows with nonzero-to-zero TMEM load={dropped_snapshots}, '
               f'without={no_clear}, incomplete_load_lists={incomplete}')
    out.append(f'distinct source_start addresses in recorded load windows={len(source_stats)}')
    for src, stats in sorted(source_stats.items(), key=lambda pair: (-pair[1]['drops'], -pair[1]['rows'], pair[0]))[:24]:
        nz_text = ','.join(f'{k}:{v}' for k, v in sorted(stats['nz'].items()))
        ex = stats['examples'].most_common(1)[0][0]
        out.append(f"  {src} rows={stats['rows']} drops_to_zero={stats['drops']} "
                   f"src64=[{nz_text}] source_tex={ex[0]} type={ex[1]} width={ex[2]} siz={ex[3]}")
    if len(source_stats) > 24:
        out.append(f'  ... {len(source_stats) - 24} additional source addresses omitted')
    out.append('Repeated load rows can refer to the same underlying operation in different target snapshots; counts are appearances, not independent loads.')
    out.append('No observed clear in a bounded history is not proof that TMEM was never cleared earlier.')
    out.append('CPU TMEM and first-64 RDRAM counts do not prove the full original texture data or GPU output.')
    return '\n'.join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    args = p.parse_args()
    with args.log.open('r', encoding='utf-8', errors='replace') as stream:
        print(summarize(stream))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
