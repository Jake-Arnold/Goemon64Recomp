#!/usr/bin/env python3
"""Instrument ONLY pinned RT64's F3DEX interpreter, for JP robot resource 0x197.

Strict source SHA and original Japanese ROM gates. This is source-only, read-only,
opt-in diagnostics, not an RT64 fix. No changes to the game's generated C.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

PINNED_RT64 = 'abb3d7ad0ed60a8a74aa839222d4c107e828b7f5'
ORIGINAL_BLOB_SHA1 = 'dccaa871f42671fad4dc65439155db5b4bbac27c'
JP_ROM_SHA1 = '6f8745fecc3a5e7d4918c7a73353eb0726116ded'
ORIGINAL_MARKER = 'goemon_jp_rt64_probe_before'
RELATIVE = Path('src/hle/rt64_interpreter.cpp')

INCLUDES = '#include <cassert>\n'
NAMESPACE = 'namespace RT64 {\n'
CMD_ANCHOR = '                func = hleGBI->map[opCode];\n'
CALL_ANCHOR = '''                if (func != nullptr) {
                    func(state, &dl);
                }
                else {
                    RT64_LOG_PRINTF("DL Parser ran into an unknown opCode (GBI %u): %u / 0x%X", uint32_t(hleGBI->ucode), opCode, opCode);
                }
'''

# Seven non-overlapping end-exclusive original-JP F3DEX lists, file 0x197.
# Each ends in G_ENDDL (0xB8). ROM-authenticated by JP_ROM_SHA1.
HELPER = r'''    // GOEMON_JP_RT64_TRACE: gated, read-only RT64 guest-F3DEX dispatch probe.
    // The exact original Japanese model file 0x197 has been independently
    // decoded. Do not modify any call target or pixel/draw state here.
    namespace {
        struct GoemonListRange { uint32_t first, end, expected_commands, expected_triangles; };
        constexpr GoemonListRange kGoemonRobotLists[] = {
            {0x12F0u, 0x13F0u, 32u,  8u},
            {0x1420u, 0x1520u, 32u,  8u},
            {0x1538u, 0x1628u, 30u, 10u},
            {0x1640u, 0x16F0u, 22u,  2u},
            {0x1708u, 0x17F8u, 30u, 10u},
            {0x1810u, 0x18C0u, 22u,  2u},
            {0x1938u, 0x1C38u, 96u, 64u}
        };
        constexpr uint32_t kGoemonExpectedSegment8 = 0x003EAE40u;
        constexpr uint32_t kGoemonRDRAMBytes = 0x00800000u;
        constexpr unsigned kGoemonMaxSamples = 2u;

        struct GoemonProbeList {
            bool active = false;
            uint32_t opcodes = 0;
            uint32_t mapped = 0;
            uint32_t unmapped = 0;
            uint32_t expected_tris = 0;
            uint32_t queued_tris = 0;
            uint32_t counter_resets = 0;
            uint32_t textures = 0;
            uint32_t bad_texture_resolution = 0;
            uint32_t vertices = 0;
            uint32_t matrices = 0;
        };
        thread_local GoemonProbeList goemonProbeLists[7];

        bool goemon_jp_rt64_probe_enabled() {
            static const bool enabled = []() {
                const char* value = std::getenv("GOEMON_JP_RT64_TRACE");
                return value && value[0] == '1' && value[1] == '\0';
            }();
            return enabled;
        }

        int goemon_jp_rt64_probe_before(State* state, const DisplayList* dl,
                                        uint8_t opcode, bool function_mapped, unsigned gbi) {
            if (!goemon_jp_rt64_probe_enabled() || state == nullptr ||
                state->RDRAM == nullptr || dl == nullptr) return -1;
            if ((state->rsp->segments[8] & 0x00FFFFFFu) != kGoemonExpectedSegment8) return -1;

            // Integer address arithmetic rather than pointer subtraction of potentially
            // unrelated objects, and a strict 8-MiB read boundary.
            const uintptr_t base = reinterpret_cast<uintptr_t>(state->RDRAM);
            const uintptr_t current = reinterpret_cast<uintptr_t>(dl);
            if (current < base || current - base > kGoemonRDRAMBytes - 8u ||
                ((current - base) & 7u) != 0u) return -1;
            const uint32_t physical = uint32_t(current - base);
            if (physical < kGoemonExpectedSegment8) return -1;
            const uint32_t offset = physical - kGoemonExpectedSegment8;
            for (unsigned i = 0; i < 7u; i++) {
                const auto& range = kGoemonRobotLists[i];
                auto& record = goemonProbeLists[i];
                if (offset < range.first || offset >= range.end ||
                    goemonProbeCompleted[i] >= kGoemonMaxSamples) continue;
                if (offset == range.first) {
                    record = GoemonProbeList{};
                    record.active = true;
                    std::fprintf(stderr, "[JP-RT64] BEGIN root=0x%04X sample=%u gbi=%u "
                                         "seg8=0x%08X segB=0x%08X segC=0x%08X\n",
                                 range.first, goemonProbeCompleted[i] + 1u,
                                 gbi,
                                 state->rsp->segments[8], state->rsp->segments[11],
                                 state->rsp->segments[12]);
                }
                if (!record.active) return -1;
                record.opcodes++;
                record.mapped += unsigned(function_mapped);
                record.unmapped += unsigned(!function_mapped);
                record.expected_tris += opcode == 0xB1 ? 2u : opcode == 0xBF ? 1u : 0u;
                record.vertices += unsigned(opcode == 0x04);
                record.matrices += unsigned(opcode == 0x01);
                return int(i);
            }
            return -1;
        }

        void goemon_jp_rt64_probe_after(State* state, int index, uint8_t opcode,
                                       uint32_t raw_arg, uint32_t old_triangles) {
            if (index < 0 || index >= 7) return;
            auto& record = goemonProbeLists[index];
            const uint32_t root = kGoemonRobotLists[index].first;
            const uint32_t new_triangles = state->drawCall.triangleCount;
            if (opcode == 0xB1 || opcode == 0xBF) {
                // RSP::drawIndexedTri increments this only after its early cull gate.
                // A workload flush could reset the counter; report ambiguity rather
                // than treating that as a missing triangle.
                if (new_triangles >= old_triangles) {
                    const uint32_t delta = new_triangles - old_triangles;
                    record.queued_tris += delta <= 2u ? delta : 0u;
                    record.counter_resets += unsigned(delta > 2u);
                }
                else record.counter_resets++;
            }
            if (opcode == 0xFD) {
                record.textures++;
                const unsigned segment = (raw_arg >> 24) & 15u;
                const uint32_t segment_base = state->rsp->segments[segment];
                const uint32_t translated = state->rsp->fromSegmented(raw_arg);
                const uint32_t expected_physical =
                    state->extended.extendRDRAM && (translated & 0x80000000u)
                        ? translated - 0x80000000u : translated & 0x00FFFFFFu;
                const uint32_t actual_physical = state->rdp->texture.address;
                const bool agrees = expected_physical == actual_physical;
                record.bad_texture_resolution += unsigned(!agrees);
                std::fprintf(stderr, "[JP-RT64] TEX root=0x%04X sample=%u "
                                     "seg=%u base=0x%08X raw=0x%08X "
                                     "resolved=0x%08X rdp=0x%08X match=%u\n",
                             root, goemonProbeCompleted[index] + 1u, segment,
                             segment_base, raw_arg, expected_physical,
                             actual_physical, unsigned(agrees));
            }
            if (opcode == 0xB8) {
                std::fprintf(stderr, "[JP-RT64] END root=0x%04X sample=%u "
                                     "commands=%u expected_commands=%u "
                                     "mapped=%u unmapped=%u "
                                     "tri_encoded=%u expected_tri=%u tri_queued=%u "
                                     "tri_ambiguous=%u textures=%u tex_mismatch=%u "
                                     "vertices=%u matrices=%u\n",
                             root, goemonProbeCompleted[index] + 1u,
                             record.opcodes, kGoemonRobotLists[index].expected_commands,
                             record.mapped, record.unmapped,
                             record.expected_tris, kGoemonRobotLists[index].expected_triangles,
                             record.queued_tris, record.counter_resets,
                             record.textures, record.bad_texture_resolution,
                             record.vertices, record.matrices);
                record.active = false;
                goemonProbeCompleted[index]++;
            }
        }
    } // anonymous namespace, GOEMON_JP_RT64_TRACE

'''
# Helper uses a separate count which persists across per-list snapshots.
HELPER = HELPER.replace('        thread_local GoemonProbeList goemonProbeLists[7];',
                        '        thread_local GoemonProbeList goemonProbeLists[7];\n'
                        '        thread_local unsigned goemonProbeCompleted[7] = {};')

NEW_CALL = '''                const int goemon_probe_index = goemon_jp_rt64_probe_before(state, dl, opCode, func != nullptr, unsigned(hleGBI->ucode));
                const uint32_t goemon_probe_arg = goemon_probe_index >= 0 ? dl->w1 : 0u;
                const uint32_t goemon_probe_tri_before = goemon_probe_index >= 0 ? state->drawCall.triangleCount : 0u;
                if (func != nullptr) {
                    func(state, &dl);
                }
                else {
                    RT64_LOG_PRINTF("DL Parser ran into an unknown opCode (GBI %u): %u / 0x%X", uint32_t(hleGBI->ucode), opCode, opCode);
                }
                if (goemon_probe_index >= 0) {
                    goemon_jp_rt64_probe_after(state, goemon_probe_index, opCode, goemon_probe_arg, goemon_probe_tri_before);
                }
'''


def blob_hash(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def validate_rom(path: Path) -> None:
    if path.stat().st_size != 0x2000000:
        raise ValueError('expected exact 32 MiB decompressed Japanese ROM')
    if hashlib.sha1(path.read_bytes()).hexdigest() != JP_ROM_SHA1:
        raise ValueError('Japanese ROM SHA-1 mismatch')


def transform(source: str) -> str:
    if ORIGINAL_MARKER in source:
        raise ValueError('RT64 diagnostic already installed')
    for label,anchor in [('includes',INCLUDES),('namespace',NAMESPACE),
                         ('GBI map',CMD_ANCHOR),('GBI call',CALL_ANCHOR)]:
        if source.count(anchor) != 1:
            raise ValueError(f'expected unique RT64 {label} anchor, found {source.count(anchor)}')
    source=source.replace(INCLUDES,INCLUDES+'#include <cstdint>\n#include <cstdlib>\n#include <cstdio>\n',1)
    source=source.replace(NAMESPACE,NAMESPACE+HELPER,1)
    source=source.replace(CALL_ANCHOR,NEW_CALL,1)
    return source


def plan(source: Path, rom: Path, backup: Path) -> str:
    validate_rom(rom)
    original=source.read_bytes()
    if blob_hash(original)!=ORIGINAL_BLOB_SHA1:
        raise ValueError('RT64 original interpreter file differs from pinned version; no changes made')
    if backup.exists():
        raise ValueError('RT64 backup already exists; no changes made')
    return transform(original.decode('utf-8'))


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    p.add_argument('--rom',type=Path,required=True)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run',action='store_true')
    group.add_argument('--confirm-modify-private-rt64',action='store_true')
    args=p.parse_args()
    source=args.rt64_dir / RELATIVE
    backup=source.with_name(source.name+'.pre-jp-robot-probe')
    try:
        result=plan(source,args.rom,backup)
        if args.confirm_modify_private_rt64:
            data=source.read_bytes()
            backup.write_bytes(data)
            try: source.write_text(result,encoding='utf-8')
            except BaseException:
                source.write_bytes(data)
                raise
        print('pinned RT64 interpreter blob SHA-1: PASS')
        print('Japanese decompressed ROM SHA-1: PASS')
        print('RT64 instrumentation: '+('installed (rebuild required)' if args.confirm_modify_private_rt64 else 'validated only'))
        print('source: '+str(source))
        print('original backup: '+str(backup))
    except (OSError,UnicodeError,ValueError) as error:
        p.error(str(error))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())