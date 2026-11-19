#!/usr/bin/env python3
"""Strict, opt-in v7 RT64 robot draw-call conservation tracer.

Requires the user's exact v6 source-only interpreter plus untouched pinned
RT64 State::flush source. Adds bounded diagnostic accounting only. No renderer,
GPU, ROM, gameplay or draw-call behavior is changed.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import jp_rt64_robot_probe as v4
import jp_rt64_triangle_gate_probe as v5
import jp_rt64_face_index_probe as v6

MARKER = 'GOEMON_JP_RT64_DRAWCALL_ACCOUNT_V7'
INTERPRETER = v4.RELATIVE
STATE = Path('src/hle/rt64_state.cpp')
STATE_ORIGINAL_GIT_BLOB = 'f9f0ad8cdc7104f50ca0efd1a9750798e0aec094'
BACKUP_SUFFIX = '.pre-jp-drawcall-v7'

FIELD_OLD = '            uint32_t face_index_ambiguous = 0; // Cursor changed, vector shrank, or inconsistent command growth.\n'
FIELD_NEW = FIELD_OLD + '''            uint32_t flush_count = 0; // Completed State::flush -> FB game calls in this list.
            uint64_t flush_triangles = 0; // Actual GameCall::callDesc.triangleCount transferred.
            uint32_t pending_start = 0; // Pending triangles carried in from the previous list.
            int cursor_start = -1;
            uint32_t flush_ambiguous = 0;
'''

THREAD_OLD = '        thread_local unsigned goemonProbeCompleted[7] = {};\n'
THREAD_NEW = THREAD_OLD + '''        // GOEMON_JP_RT64_DRAWCALL_ACCOUNT_V7: only one list is active per thread.
        thread_local int goemonV7ActiveList = -1;
        thread_local const State* goemonV7ActiveState = nullptr;
'''

BEGIN_OLD = '                    record.active = true;\n'
BEGIN_NEW = BEGIN_OLD + '''                    record.pending_start = state->drawCall.triangleCount;
                    record.cursor_start = state->ext.workloadQueue
                        ? state->ext.workloadQueue->writeCursor : -1;
                    goemonV7ActiveList = int(i);
                    goemonV7ActiveState = state;
'''

END_OLD = '''                record.active = false;
                goemonProbeCompleted[index]++;
'''
END_NEW = '''                // GOEMON_JP_RT64_DRAWCALL_ACCOUNT_V7: reconcile the resettable
                // pending counter with *actual* game-call flushes, including
                // triangles carried into the list. Never call flush here.
                const int goemonV7CursorEnd = state->ext.workloadQueue
                    ? state->ext.workloadQueue->writeCursor : -1;
                const uint32_t goemonV7PendingEnd = state->drawCall.triangleCount;
                const bool goemonV7CursorValid = record.cursor_start >= 0 &&
                    record.cursor_start < WORKLOAD_QUEUE_SIZE &&
                    goemonV7CursorEnd == record.cursor_start &&
                    record.flush_ambiguous == 0;
                const int64_t goemonV7Conserved =
                    int64_t(record.flush_triangles) + int64_t(goemonV7PendingEnd) -
                    int64_t(record.pending_start);
                const bool goemonV7Matches = goemonV7CursorValid &&
                    goemonV7Conserved == int64_t(record.face_index_triangles) &&
                    record.face_index_ambiguous == 0;
                std::fprintf(stderr, "[JP-RT64] DRAWCALL root=0x%04X sample=%u "
                                     "flush_calls=%u flush_tri=%llu pending_in=%u pending_out=%u "
                                     "conserved_tri=%lld face_index_tri=%u cursor_ok=%u "
                                     "ambiguous=%u match=%u\\n",
                             root, goemonProbeCompleted[index] + 1u, record.flush_count,
                             static_cast<unsigned long long>(record.flush_triangles),
                             record.pending_start, goemonV7PendingEnd,
                             static_cast<long long>(goemonV7Conserved),
                             record.face_index_triangles, unsigned(goemonV7CursorValid),
                             record.flush_ambiguous + record.face_index_ambiguous,
                             unsigned(goemonV7Matches));
                goemonV7ActiveList = -1;
                goemonV7ActiveState = nullptr;
                record.active = false;
                goemonProbeCompleted[index]++;
'''

HELPER_END = '    } // anonymous namespace, GOEMON_JP_RT64_TRACE\n'
HOOK_CODE = '''    // GOEMON_JP_RT64_DRAWCALL_ACCOUNT_V7: called after a real FB game call is
    // recorded by State::flush. Does not read/alter the GPU or invoke flush.
    void goemon_jp_rt64_note_robot_flush(const State* state, uint32_t triangles,
                                         int workload_cursor) {
        if (!goemon_jp_rt64_probe_enabled() || state != goemonV7ActiveState ||
            goemonV7ActiveList < 0 || goemonV7ActiveList >= 7) return;
        auto& record = goemonProbeLists[goemonV7ActiveList];
        if (!record.active || record.cursor_start != workload_cursor) {
            record.flush_ambiguous++;
            return;
        }
        record.flush_count++;
        record.flush_triangles += triangles;
    }

'''

STATE_NS_OLD = 'namespace RT64 {\n'
STATE_NS_NEW = STATE_NS_OLD + '''    // GOEMON_JP_RT64_DRAWCALL_ACCOUNT_V7: implemented in exact v6-upgraded interpreter.
    void goemon_jp_rt64_note_robot_flush(const State*, uint32_t, int);
'''
STATE_FLUSH_OLD = '        fbPair.addGameCall(gameCall);\n'
STATE_FLUSH_NEW = STATE_FLUSH_OLD + '''        // Read-only confirmation that this call has entered the FB pair.
        goemon_jp_rt64_note_robot_flush(this, gameCall.callDesc.triangleCount,
                                       workloadCursor);
'''


def replace_exact_once(source: str, before: str, after: str, label: str) -> str:
    found = source.count(before)
    if found != 1:
        raise ValueError(f'{label}: expected unique anchor, got {found}')
    return source.replace(before, after, 1)


def transform_interpreter(source: str) -> str:
    if MARKER in source:
        raise ValueError('v7 interpreter already patched')
    if v6.MARKER not in source:
        raise ValueError('exact v6 instrumentation is required')
    for key, before, after in (
        ('record', FIELD_OLD, FIELD_NEW),
        ('per-thread state', THREAD_OLD, THREAD_NEW),
        ('list begin', BEGIN_OLD, BEGIN_NEW),
        ('list end', END_OLD, END_NEW),
        ('cross-file hook', HELPER_END, HELPER_END + HOOK_CODE),
    ):
        source = replace_exact_once(source, before, after, key)
    return source


def transform_state(source: str) -> str:
    if MARKER in source:
        raise ValueError('v7 State::flush already patched')
    source = replace_exact_once(source, STATE_NS_OLD, STATE_NS_NEW, 'RT64 namespace')
    source = replace_exact_once(source, STATE_FLUSH_OLD, STATE_FLUSH_NEW, 'FB pair submission')
    return source


def plan(rt64_dir: Path, rom: Path) -> list[tuple[Path, bytes, bytes]]:
    v4.validate_rom(rom)
    interpreter = rt64_dir / INTERPRETER
    state = rt64_dir / STATE
    pinned = interpreter.with_name(interpreter.name + '.pre-jp-robot-probe')
    backup_v4 = interpreter.with_name(interpreter.name + '.pre-jp-tri-gate-v5')
    backup_v5 = interpreter.with_name(interpreter.name + '.pre-jp-face-index-v6')
    original = pinned.read_bytes()
    if v4.blob_hash(original) != v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('original RT64 interpreter does not match pinned Git blob')
    expected_v4 = v4.transform(original.decode('utf-8')).encode('utf-8')
    expected_v5 = v5.transform(expected_v4.decode('utf-8')).encode('utf-8')
    expected_v6 = v6.transform(expected_v5.decode('utf-8')).encode('utf-8')
    if backup_v4.read_bytes() != expected_v4:
        raise ValueError('v5 predecessor backup drifted')
    if backup_v5.read_bytes() != expected_v5:
        raise ValueError('v6 predecessor backup drifted')
    now_interpreter = interpreter.read_bytes()
    if now_interpreter != expected_v6:
        raise ValueError('installed v6 interpreter differs from canonical transformation')
    now_state = state.read_bytes()
    if v4.blob_hash(now_state) != STATE_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned RT64 State::flush source differs from tested revision')
    output = [
        (interpreter, now_interpreter, transform_interpreter(now_interpreter.decode('utf-8')).encode('utf-8')),
        (state, now_state, transform_state(now_state.decode('utf-8')).encode('utf-8')),
    ]
    for target, _, _ in output:
        if target.with_name(target.name + BACKUP_SUFFIX).exists():
            raise ValueError('v7 already installed/backup exists; refusing repeat')
    return output


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', required=True, type=Path)
    p.add_argument('--rt64-dir', default=Path('lib/rt64'), type=Path)
    operation = p.add_mutually_exclusive_group(required=True)
    operation.add_argument('--dry-run', action='store_true')
    operation.add_argument('--confirm-modify-private-rt64', action='store_true')
    args = p.parse_args()
    try:
        changes = plan(args.rt64_dir, args.rom)
        if args.confirm_modify_private_rt64:
            for target, old, _ in changes:
                target.with_name(target.name + BACKUP_SUFFIX).write_bytes(old)
            try:
                for target, _, after in changes:
                    target.write_bytes(after)
            except BaseException:
                for target, old, _ in changes:
                    target.write_bytes(old)
                raise
        print('original Japanese ROM + RT64 pinned interpreter + v4/v5/v6 chain: PASS')
        print('pinned original RT64 State::flush blob: PASS')
        print('mode: ' + ('v7 read-only draw-call accounting installed (rebuild required)'
                          if args.confirm_modify_private_rt64 else 'validated only'))
        for target, _, _ in changes:
            print('source: ' + str(target))
            print('backup: ' + str(target.with_name(target.name + BACKUP_SUFFIX)))
    except (ValueError, OSError, UnicodeError) as e:
        p.error(str(e))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())