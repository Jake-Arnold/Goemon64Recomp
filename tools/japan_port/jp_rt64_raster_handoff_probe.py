#!/usr/bin/env python3
"""Read-only, opt-in v8 JP robot CPU-GameCall -> raster command handoff probe.

Requires exact v7 local files, original pinned upstream RT64 framebuffer
renderer and original Japanese decompressed ROM. No game/ROM/GPU state edits.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import jp_rt64_robot_probe as v4
import jp_rt64_triangle_gate_probe as v5
import jp_rt64_face_index_probe as v6
import jp_rt64_drawcall_account_probe as v7

MARKER = 'GOEMON_JP_RT64_RASTER_HANDOFF_V8'
RT64_RENDERER = Path('src/render/rt64_framebuffer_renderer.cpp')
RENDER_ORIGINAL_GIT_BLOB = '46289b1961b88f82f7d8437402e96881080bee96'
BACKUP_SUFFIX = '.pre-jp-raster-v8'
INTERPRETER = v4.RELATIVE
STATE = v7.STATE

RECORD_OLD = '            uint32_t flush_ambiguous = 0;\n'
RECORD_NEW = RECORD_OLD + '''            uint64_t v8_frame = 0;
            uint32_t v8_face_first = 0;
            bool v8_valid_start = false;
'''

BEGIN_OLD = '                    goemonV7ActiveState = state;\n'
BEGIN_NEW = BEGIN_OLD + '''                    // GOEMON_JP_RT64_RASTER_HANDOFF_V8: capture a face-index interval
                    // for each of the seven authenticated robot lists.
                    record.v8_valid_start = record.cursor_start >= 0 &&
                        record.cursor_start < WORKLOAD_QUEUE_SIZE;
                    if (record.v8_valid_start) {
                        const auto& w = state->ext.workloadQueue->workloads[record.cursor_start];
                        record.v8_frame = w.submissionFrame;
                        record.v8_face_first = uint32_t(w.drawData.faceIndices.size());
                    }
'''

END_OLD = '                goemonV7ActiveList = -1;\n'
END_NEW = '''                // Register only complete, unambiguous face ranges. Cross-thread
                // lookup is bounded and synchronized; the renderer is untouched.
                if (record.v8_valid_start && record.face_index_ambiguous == 0 &&
                    goemonV7CursorValid) {
                    const auto& w = state->ext.workloadQueue->workloads[record.cursor_start];
                    const size_t last = w.drawData.faceIndices.size();
                    const size_t first = record.v8_face_first;
                    if (w.submissionFrame == record.v8_frame && last >= first &&
                        last <= UINT32_MAX && (last - first) % 3u == 0 &&
                        (last - first) / 3u == record.face_index_triangles) {
                        goemon_jp_rt64_register_robot_range(record.v8_frame,
                            uint32_t(first), uint32_t(last), root,
                            goemonProbeCompleted[index] + 1u);
                    }
                }
''' + END_OLD

REGISTRY_INSERT = r'''    // GOEMON_JP_RT64_RASTER_HANDOFF_V8: capture only seven original nested
    // file-0x197 list ranges twice each; never store guest commands or ROM data.
    namespace {
        struct GoemonRobotFaceRange {
            uint64_t frame = 0;
            uint32_t begin = 0, end = 0, root = 0, sample = 0;
        };
        std::mutex goemonRobotFaceMutex;
        GoemonRobotFaceRange goemonRobotFaceRanges[14];
        unsigned goemonRobotFaceCount = 0;
    }

    void goemon_jp_rt64_register_robot_range(uint64_t frame, uint32_t begin,
                                              uint32_t end, uint32_t root,
                                              uint32_t sample) {
        if (!goemon_jp_rt64_probe_enabled() || end <= begin ||
            (end - begin) % 3u != 0u || sample < 1u || sample > 2u) return;
        std::lock_guard<std::mutex> lock(goemonRobotFaceMutex);
        if (goemonRobotFaceCount >= 14u) return;
        for (unsigned i = 0; i < goemonRobotFaceCount; i++) {
            if (goemonRobotFaceRanges[i].frame == frame &&
                goemonRobotFaceRanges[i].root == root &&
                goemonRobotFaceRanges[i].sample == sample) return;
        }
        goemonRobotFaceRanges[goemonRobotFaceCount++] = {frame, begin, end, root, sample};
        std::fprintf(stderr, "[JP-RT64] FACE_RANGE root=0x%04X sample=%u "
                             "frame=%llu first=%u end=%u triangles=%u\n",
                     root, sample, static_cast<unsigned long long>(frame), begin,
                     end, (end - begin) / 3u);
    }

    bool goemon_jp_rt64_lookup_robot_range(uint64_t frame, uint32_t first,
                                            uint32_t tris, unsigned ordinal,
                                            uint32_t *root, uint32_t *sample,
                                            uint32_t *overlap) {
        if (!goemon_jp_rt64_probe_enabled() || tris == 0u ||
            root == nullptr || sample == nullptr || overlap == nullptr) return false;
        const uint64_t end64 = uint64_t(first) + uint64_t(tris) * 3u;
        if (end64 > UINT32_MAX) return false;
        std::lock_guard<std::mutex> lock(goemonRobotFaceMutex);
        unsigned matching = 0;
        for (unsigned i = 0; i < goemonRobotFaceCount; i++) {
            const auto &entry = goemonRobotFaceRanges[i];
            if (entry.frame != frame) continue;
            const uint32_t lower = std::max(first, entry.begin);
            const uint32_t upper = std::min(uint32_t(end64), entry.end);
            if (upper <= lower) continue;
            // A single GPU GameCall may straddle two original robot lists.
            if ((upper - lower) % 3u != 0u) return false;
            if (matching++ == ordinal) {
                *root = entry.root;
                *sample = entry.sample;
                *overlap = (upper - lower) / 3u;
                return true;
            }
        }
        return false;
    }

'''

RENDER_NAMESPACE = 'namespace RT64 {\n    // Helper functions.\n'
RENDER_INCLUDE = '#include "rt64_framebuffer_renderer.h"\n'
RENDER_INCLUDE_NEW = RENDER_INCLUDE + '#include <cstdint>\n#include <cstdio>\n'
RENDER_DECLARE = 'namespace RT64 {\n' + '''    // GOEMON_JP_RT64_RASTER_HANDOFF_V8: exact face-index trace bridge.
    bool goemon_jp_rt64_lookup_robot_range(uint64_t, uint32_t, uint32_t,
                                            unsigned, uint32_t*, uint32_t*, uint32_t*);
    namespace {
        struct GoemonRobotRasterTag {
            uint32_t instance = 0, root = 0, sample = 0, overlap = 0;
        };
        thread_local GoemonRobotRasterTag goemonRobotRasterTags[256];
        thread_local unsigned goemonRobotRasterTagCount = 0;
        void goemon_jp_rt64_raster_log(uint32_t index, const char* event,
                                        uint32_t faces, bool empty_scissor) {
            for (unsigned k = 0; k < goemonRobotRasterTagCount; k++) {
                const auto &tag = goemonRobotRasterTags[k];
                if (tag.instance != index) continue;
                std::fprintf(stderr, "[JP-RT64] RASTER %s root=0x%04X sample=%u "
                                     "instance=%u call_tri=%u overlap_tri=%u empty_scissor=%u\\n",
                             event, tag.root, tag.sample, index, faces, tag.overlap,
                             unsigned(empty_scissor));
            }
        }
    }
''' + '    // Helper functions.\n'
RENDER_RESET_OLD = '        instanceDrawCallVector.clear();\n'
RENDER_RESET_NEW = RENDER_RESET_OLD + '        goemonRobotRasterTagCount = 0; // GOEMON_JP_RT64_RASTER_HANDOFF_V8\n'
RENDER_SKIP_PROJECTION_OLD = '''            if (proj.scissorRect.isNull()) {
                continue;
            }
'''
RENDER_SKIP_PROJECTION_NEW = '''            if (proj.scissorRect.isNull()) {
                // This entire projection is omitted in the CPU raster instance builder.
                for (uint32_t d = 0; d < proj.gameCallCount; d++) {
                    const auto& call = proj.gameCalls[d];
                    for (unsigned ordinal = 0; ordinal < 14u; ordinal++) {
                        uint32_t root=0, sample=0, overlap=0;
                        if (!goemon_jp_rt64_lookup_robot_range(
                                p.curWorkload->submissionFrame,
                                call.meshDesc.faceIndicesStart,
                                call.callDesc.triangleCount,
                                ordinal, &root, &sample, &overlap)) break;
                        std::fprintf(stderr, "[JP-RT64] RASTER SKIP_PROJECTION "
                                             "root=0x%04X sample=%u call=%u "
                                             "call_tri=%u overlap_tri=%u\\n",
                                     root, sample, call.callDesc.callIndex,
                                     call.callDesc.triangleCount, overlap);
                    }
                }
                continue;
            }
'''
RENDER_INSTANCE_OLD = '''                instanceDrawCallVector.push_back(instanceDrawCall);
                globalCallIndex++;
'''
RENDER_INSTANCE_NEW = '''                // Record only GameCalls overlapping the 14 authenticated list ranges.
                // An ordinary raster instance may aggregate two neighboring lists.
                for (unsigned ordinal = 0; ordinal < 14u; ordinal++) {
                    uint32_t root=0, sample=0, overlap=0;
                    if (!goemon_jp_rt64_lookup_robot_range(
                            p.curWorkload->submissionFrame,
                            call.meshDesc.faceIndicesStart,
                            call.callDesc.triangleCount,
                            ordinal, &root, &sample, &overlap)) break;
                    const bool raster_tri = instanceDrawCall.type == InstanceDrawCall::Type::IndexedTriangles ||
                        instanceDrawCall.type == InstanceDrawCall::Type::RawTriangles ||
                        instanceDrawCall.type == InstanceDrawCall::Type::RegularRect;
                    const bool scissor_empty = raster_tri && instanceDrawCall.triangles.scissor.isEmpty();
                    std::fprintf(stderr, "[JP-RT64] RASTER BUILT root=0x%04X sample=%u "
                                         "frame=%llu instance=%u call=%u call_tri=%u "
                                         "overlap_tri=%u type=%u scissor_empty=%u pipeline=%u\\n",
                                 root, sample,
                                 static_cast<unsigned long long>(p.curWorkload->submissionFrame),
                                 uint32_t(instanceDrawCallVector.size()),
                                 call.callDesc.callIndex, call.callDesc.triangleCount,
                                 overlap, unsigned(instanceDrawCall.type),
                                 unsigned(scissor_empty),
                                 unsigned(!raster_tri || instanceDrawCall.triangles.pipeline != nullptr));
                    if (goemonRobotRasterTagCount < 256u) {
                        goemonRobotRasterTags[goemonRobotRasterTagCount++] = {
                            uint32_t(instanceDrawCallVector.size()), root, sample, overlap};
                    }
                }
''' + RENDER_INSTANCE_OLD
RENDER_SKIP_SCISSOR_OLD = '''                if (triangles.scissor.isEmpty()) {
                    continue;
                }
'''
RENDER_SKIP_SCISSOR_NEW = '''                if (triangles.scissor.isEmpty()) {
                    goemon_jp_rt64_raster_log(i, "SKIP_SCISSOR", triangles.faceCount, true);
                    continue;
                }
'''
RENDER_DRAW_OLD = '''                drawCallTriangles(drawCall);

                // Simulate dither noise.
'''
RENDER_DRAW_NEW = '''                drawCallTriangles(drawCall);
                // Command recording reached the host rendering API. It does NOT
                // prove GPU execution, rasterization, or pixel visibility.
                goemon_jp_rt64_raster_log(i, "DRAW_RECORDED", triangles.faceCount, false);

                // Simulate dither noise.
'''


def replace_once(source: str, old: str, new: str, what: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f'{what}: expected unique pinned source anchor, found {source.count(old)}')
    return source.replace(old,new,1)


def transform_interpreter(source: str) -> str:
    if MARKER in source:
        raise ValueError('v8 interpreter already installed')
    if v7.MARKER not in source:
        raise ValueError('exact v7 interpreter required')
    for before,after,what in (
        (v4.INCLUDES,v4.INCLUDES+'#include <algorithm>\n#include <mutex>\n', 'includes'),
        (v4.NAMESPACE, v4.NAMESPACE + '    void goemon_jp_rt64_register_robot_range(uint64_t, uint32_t, uint32_t, uint32_t, uint32_t);\n', 'range forward declaration'),
        (RECORD_OLD,RECORD_NEW,'record fields'),
        (BEGIN_OLD,BEGIN_NEW,'actor list begin'),
        (END_OLD,END_NEW,'actor list end'),
        (v7.HELPER_END,v7.HELPER_END+REGISTRY_INSERT,'range registry')):
        source=replace_once(source,before,after,what)
    return source


def transform_renderer(source: str) -> str:
    if MARKER in source:
        raise ValueError('v8 renderer already installed')
    for before,after,what in (
        (RENDER_INCLUDE,RENDER_INCLUDE_NEW,'renderer includes'),
        (RENDER_NAMESPACE,RENDER_DECLARE,'namespace declaration'),
        (RENDER_RESET_OLD,RENDER_RESET_NEW,'frame reset'),
        (RENDER_SKIP_PROJECTION_OLD,RENDER_SKIP_PROJECTION_NEW,'projection gate'),
        (RENDER_INSTANCE_OLD,RENDER_INSTANCE_NEW,'raster instance builder'),
        (RENDER_SKIP_SCISSOR_OLD,RENDER_SKIP_SCISSOR_NEW,'raster scissor gate'),
        (RENDER_DRAW_OLD,RENDER_DRAW_NEW,'host GPU draw command')):
        source=replace_once(source,before,after,what)
    return source


def plan(rt64_dir: Path, rom: Path) -> list[tuple[Path,bytes,bytes]]:
    v4.validate_rom(rom)
    inter = rt64_dir/INTERPRETER
    state = rt64_dir/STATE
    renderer = rt64_dir/RT64_RENDERER
    original_inter=inter.with_name(inter.name+'.pre-jp-robot-probe').read_bytes()
    if v4.blob_hash(original_inter) != v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('pinned RT64 interpreter original mismatch')
    original_state=state.with_name(state.name+v7.BACKUP_SUFFIX).read_bytes()
    if v4.blob_hash(original_state) != v7.STATE_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned original RT64 state backup mismatch')
    expected_v4=v4.transform(original_inter.decode('utf-8'))
    expected_v5=v5.transform(expected_v4)
    expected_v6=v6.transform(expected_v5)
    expected_v7=v7.transform_interpreter(expected_v6)
    if inter.read_bytes()!=expected_v7.encode('utf-8'):
        raise ValueError('installed interpreter not exact v7 deterministic transformation')
    if state.read_bytes()!=v7.transform_state(original_state.decode('utf-8')).encode('utf-8'):
        raise ValueError('installed RT64 state not exact v7 deterministic transformation')
    pristine_renderer=renderer.read_bytes()
    if v4.blob_hash(pristine_renderer)!=RENDER_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned original RT64 renderer differs; refuse patch')
    results=[
        (inter,inter.read_bytes(),transform_interpreter(expected_v7).encode('utf-8')),
        (renderer,pristine_renderer,transform_renderer(pristine_renderer.decode('utf-8')).encode('utf-8')),
    ]
    for file,_,_ in results:
        if file.with_name(file.name+BACKUP_SUFFIX).exists():
            raise ValueError('existing v8 backup: refusing repeated modification')
    return results


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    p.add_argument('--rom',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run',action='store_true')
    group.add_argument('--confirm-modify-private-rt64',action='store_true')
    a=p.parse_args()
    try:
        changes=plan(a.rt64_dir,a.rom)
        if a.confirm_modify_private_rt64:
            for path,old,_ in changes:
                path.with_name(path.name+BACKUP_SUFFIX).write_bytes(old)
            try:
                for path,_,after in changes:
                    path.write_bytes(after)
            except BaseException:
                for path,old,_ in changes:
                    path.write_bytes(old)
                raise
        print('original Japanese ROM and pinned RT64 v7 chain: PASS')
        print('original renderer pinned Git blob: PASS')
        print('mode: '+('read-only v8 installed; rebuild required' if a.confirm_modify_private_rt64 else 'validated only'))
        for path,_,_ in changes:
            print('source: '+str(path))
            print('backup: '+str(path.with_name(path.name+BACKUP_SUFFIX)))
    except (OSError,ValueError,UnicodeError) as error:
        p.error(str(error))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())