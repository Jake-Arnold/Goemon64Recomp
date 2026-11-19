#!/usr/bin/env python3
"""Fail-closed, source-only v11 -> v12 JP robot CPU TMEM load replay trace.

Logs source-address, bounded RDRAM sample, and CPU TMEM change metrics for
recent RDP texture loads preceding 32x64 robot texture hashes. No pixels, game
assets or whole memory blobs are emitted. Only State source is modified.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import jp_rt64_robot_texture_link_v11 as v11

MARKER = 'GOEMON_JP_RT64_TMEM_REPLAY_V12'
STATE_BACKUP = '.pre-jp-tmem-replay-v12'
STATE = v11.v10.v7.STATE

INCLUDE_OLD = '#include "rt64_state.h"\n'
INCLUDE_NEW = INCLUDE_OLD + '#include <algorithm>\n#include <array>\n#include <cstdio>\n#include <cstdlib>\n'

FUNCTION_OLD = '''    void State::fullSyncFramebufferPairTiles(Workload &workload, FramebufferPair &fbPair, uint32_t &loadOpCursor, uint32_t &rdpTileCursor) {
        auto loadOperation = [&](uint32_t loadOpIndex) {
'''
FUNCTION_NEW = '''    void State::fullSyncFramebufferPairTiles(Workload &workload, FramebufferPair &fbPair, uint32_t &loadOpCursor, uint32_t &rdpTileCursor) {
        // GOEMON_JP_RT64_TMEM_REPLAY_V12: bounded, read-only replay provenance.
        // The two exact hashes were obtained from the user's v11 pink robot trace.
        const bool jpV12Trace = []() {
            const char *e = std::getenv("GOEMON_JP_RT64_TEX_TRACE");
            return e && e[0] == '1' && e[1] == '\\0';
        }();
        struct JPV12Load {
            uint32_t index = 0, type = 0, src = 0, srcNz64 = 0xFFFFFFFFu;
            uint32_t srcTex = 0, width = 0, loadFmt = 0, loadSiz = 0;
            uint32_t tileFmt = 0, tileSiz = 0, tmem = 0, line = 0;
            uint32_t uls = 0, ult = 0, lrs = 0, lrt = 0;
            uint32_t tmemBefore = 0, tmemAfter = 0;
        };
        std::array<JPV12Load, 32> jpV12Loads{};
        uint32_t jpV12Seen = 0;
        auto jpV12TMEMNZ = [&]() -> uint32_t {
            const auto *bytes = reinterpret_cast<const uint8_t *>(rdp->TMEM);
            uint32_t nz = 0;
            for (uint32_t i = 0; i < RDP_TMEM_BYTES; i++) nz += bytes[i] != 0;
            return nz;
        };
        auto loadOperation = [&](uint32_t loadOpIndex) {
'''

LOAD_OLD = '''            const auto &loadOp = workload.drawData.loadOperations[loadOpIndex];

            // For emulating how Rice hashes textures, we need information about the load operation that was performed in the particular TMEM address.
'''
LOAD_NEW = '''            const auto &loadOp = workload.drawData.loadOperations[loadOpIndex];
            if (jpV12Trace) {
                JPV12Load &rec = jpV12Loads[jpV12Seen++ % jpV12Loads.size()];
                rec = {};
                rec.index = loadOpIndex;
                rec.type = uint32_t(loadOp.type);
                rec.srcTex = loadOp.texture.address;
                rec.width = loadOp.texture.width;
                rec.loadFmt = loadOp.texture.fmt;
                rec.loadSiz = loadOp.texture.siz;
                rec.tileFmt = loadOp.tile.fmt;
                rec.tileSiz = loadOp.tile.siz;
                rec.tmem = loadOp.tile.tmem;
                rec.line = loadOp.tile.line;
                rec.uls = loadOp.tile.uls;
                rec.ult = loadOp.tile.ult;
                rec.lrs = loadOp.tile.lrs;
                rec.lrt = loadOp.tile.lrt;
                rec.tmemBefore = jpV12TMEMNZ();
                const uint64_t bytesPerRow =
                    (uint64_t(loadOp.texture.width) << loadOp.texture.siz) >> 1;
                const uint64_t offset = (loadOp.type == LoadOperation::Type::Block)
                    ? ((uint64_t(loadOp.tile.uls) << loadOp.texture.siz) >> 1)
                        + bytesPerRow * loadOp.tile.ult
                    : ((uint64_t(loadOp.tile.uls >> 2) << loadOp.texture.siz) >> 1)
                        + bytesPerRow * (loadOp.tile.ult >> 2);
                const uint64_t source = uint64_t(loadOp.texture.address) + offset;
                rec.src = source <= UINT32_MAX ? uint32_t(source) : 0xFFFFFFFFu;
                rec.srcNz64 = 0xFFFFFFFFu; // not sampled (outside conservative 4 MiB bound)
                constexpr uint64_t Conservative4MiB = 4ull * 1024ull * 1024ull;
                if (RDRAM && source <= Conservative4MiB - 64u) {
                    rec.srcNz64 = 0;
                    for (uint32_t i = 0; i < 64u; i++)
                        rec.srcNz64 += RDRAM[size_t(source) + i] != 0;
                }
            }

            // For emulating how Rice hashes textures, we need information about the load operation that was performed in the particular TMEM address.
'''

AFTER_LOAD_OLD = '''            case LoadOperation::Type::TLUT:
                rdp->loadTLUTOperation(loadOp.tile, loadOp.texture, false);
                break;
            };
        };

        auto uploadTile ='''
AFTER_LOAD_NEW = '''            case LoadOperation::Type::TLUT:
                rdp->loadTLUTOperation(loadOp.tile, loadOp.texture, false);
                break;
            };
            if (jpV12Trace && jpV12Seen > 0)
                jpV12Loads[(jpV12Seen - 1u) % jpV12Loads.size()].tmemAfter = jpV12TMEMNZ();
        };

        auto uploadTile ='''

UPLOAD_OLD = '''                else {
                    callTile.tmemHashOrID = textureManager.uploadTexture(this, callTile.loadTile, ext.textureCache, workload.submissionFrame, callTile.sampleWidth, callTile.sampleHeight, callTile.tlut);
                }
            }
            else if (callTile.reinterpretTile) {
'''
UPLOAD_NEW = '''                else {
                    callTile.tmemHashOrID = textureManager.uploadTexture(this, callTile.loadTile, ext.textureCache, workload.submissionFrame, callTile.sampleWidth, callTile.sampleHeight, callTile.tlut);
                    // Only log when this call actually hashes/queues the current CPU TMEM.
                    constexpr uint64_t JPBad = 0x8042c12b60ec2b4eull;
                constexpr uint64_t JPCompare = 0x4263ca7ef085e861ull;
                const uint64_t hash = callTile.tmemHashOrID;
                static thread_local uint32_t jpV12Printed = 0;
                if (jpV12Trace && (hash == JPBad || hash == JPCompare) &&
                    callTile.sampleWidth == 32u && callTile.sampleHeight == 64u &&
                    jpV12Printed < 16u) {
                    ++jpV12Printed;
                    std::fprintf(stderr,
                        "[JP-RT64] TEX_REPLAY_TARGET frame=%llu call=%u hash=0x%016llX "
                        "tile_index=%u tile_fmt=%u tile_siz=%u tmem=%u line=%u "
                        "total_tmem_nonzero=%u recent_loads=%u\\n",
                        static_cast<unsigned long long>(workload.submissionFrame),
                        unsigned(drawCall.callIndex), static_cast<unsigned long long>(hash),
                        unsigned(rdpTileIndex), unsigned(callTile.loadTile.fmt),
                        unsigned(callTile.loadTile.siz), unsigned(callTile.loadTile.tmem),
                        unsigned(callTile.loadTile.line), jpV12TMEMNZ(),
                        unsigned(std::min<size_t>(jpV12Seen, jpV12Loads.size())));
                    const uint32_t records = uint32_t(std::min<size_t>(jpV12Seen, jpV12Loads.size()));
                    for (uint32_t off = records; off > 0u; --off) {
                        const auto &rec = jpV12Loads[(jpV12Seen - off) % jpV12Loads.size()];
                        std::fprintf(stderr,
                            "[JP-RT64] TEX_REPLAY_LOAD frame=%llu call=%u hash=0x%016llX "
                            "index=%u type=%u source_tex=0x%08X source_start=0x%08X "
                            "source_nonzero64=%u load_fmt=%u load_siz=%u width=%u "
                            "tile_fmt=%u tile_siz=%u tmem=%u line=%u "
                            "uls=%u ult=%u lrs=%u lrt=%u tmem_nz_before=%u tmem_nz_after=%u\\n",
                            static_cast<unsigned long long>(workload.submissionFrame),
                            unsigned(drawCall.callIndex), static_cast<unsigned long long>(hash),
                            rec.index, rec.type, rec.srcTex, rec.src, rec.srcNz64,
                            rec.loadFmt, rec.loadSiz, rec.width, rec.tileFmt, rec.tileSiz,
                            rec.tmem, rec.line, rec.uls, rec.ult, rec.lrs, rec.lrt,
                            rec.tmemBefore, rec.tmemAfter);
                    }
                }
                }
            }
            else if (callTile.reinterpretTile) {
'''

def transform_state(source:str)->str:
    if MARKER in source:raise ValueError('v12 already installed')
    if v11.v10.v7.MARKER not in source:raise ValueError('v7 State instrumentation required')
    for before,after,label in (
        (INCLUDE_OLD,INCLUDE_NEW,'State include'),
        (FUNCTION_OLD,FUNCTION_NEW,'fullSync function'),
        (LOAD_OLD,LOAD_NEW,'RDP load metadata'),
        (AFTER_LOAD_OLD,AFTER_LOAD_NEW,'RDP load aftermath'),
        (UPLOAD_OLD,UPLOAD_NEW,'target tile upload'),
    ):
        source=v11.v10.one(source,before,after,label)
    return source

def plan(rt64:Path,rom:Path)->tuple[Path,bytes,bytes]:
    v11.v10.v4.validate_rom(rom)
    r=rt64/v11.RENDERER
    c=rt64/v11.v10.CACHE
    s=rt64/STATE
    pristine_r=r.with_name(r.name+v11.v10.v8.BACKUP_SUFFIX).read_bytes()
    if v11.v10.git_blob_sha(pristine_r)!=v11.v10.v8.RENDER_ORIGINAL_GIT_BLOB:
        raise ValueError('original renderer blob mismatch')
    expected_v8=v11.v10.v8.transform_renderer(pristine_r.decode()).encode()
    if r.with_name(r.name+v11.v10.v9.BACKUP).read_bytes()!=expected_v8:
        raise ValueError('v9 renderer original backup mismatch')
    expected_v9=v11.v10.v9.transform(expected_v8.decode()).encode()
    if r.with_name(r.name+v11.v10.RENDER_BACKUP).read_bytes()!=expected_v9:
        raise ValueError('v10 renderer backup mismatch')
    expected_v10=v11.v10.transform_renderer(expected_v9.decode()).encode()
    if r.with_name(r.name+v11.BACKUP).read_bytes()!=expected_v10:
        raise ValueError('v11 renderer backup mismatch')
    expected_v11=v11.transform_renderer(expected_v10.decode()).encode()
    if r.read_bytes()!=expected_v11:
        raise ValueError('installed renderer not exact v11; no modifications')
    pristine_c=c.with_name(c.name+v11.v10.CACHE_BACKUP).read_bytes()
    if v11.v10.git_blob_sha(pristine_c)!=v11.v10.CACHE_GIT_BLOB:
        raise ValueError('original texture-cache blob mismatch')
    if c.read_bytes()!=v11.v10.transform_cache(pristine_c.decode()).encode():
        raise ValueError('installed texture-cache differs from v10; no modifications')
    interpreter=rt64/v11.v10.v4.RELATIVE
    original_i=interpreter.with_name(interpreter.name+'.pre-jp-robot-probe').read_bytes()
    if v11.v10.git_blob_sha(original_i)!=v11.v10.v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('original interpreter blob mismatch')
    expected_i=v11.v10.v8.transform_interpreter(v11.v10.v7.transform_interpreter(
        v11.v10.v6.transform(v11.v10.v5.transform(v11.v10.v4.transform(original_i.decode()))))).encode()
    if interpreter.read_bytes()!=expected_i:
        raise ValueError('installed interpreter differs from exact v8 chain')
    original_s=s.with_name(s.name+v11.v10.v7.BACKUP_SUFFIX).read_bytes()
    if v11.v10.git_blob_sha(original_s)!=v11.v10.v7.STATE_ORIGINAL_GIT_BLOB:
        raise ValueError('original state blob mismatch')
    expected_s=v11.v10.v7.transform_state(original_s.decode()).encode()
    if s.read_bytes()!=expected_s:
        raise ValueError('installed State differs from exact v7; no modifications')
    if s.with_name(s.name+STATE_BACKUP).exists():
        raise ValueError('v12 State backup exists; refuse reapply')
    return s,expected_s,transform_state(expected_s.decode()).encode()

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',required=True,type=Path)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run',action='store_true')
    group.add_argument('--confirm-modify-private-rt64',action='store_true')
    a=p.parse_args()
    try:
        src,old,new=plan(a.rt64_dir,a.rom)
        if a.confirm_modify_private_rt64:
            backup=src.with_name(src.name+STATE_BACKUP)
            backup.write_bytes(old)
            try:src.write_bytes(new)
            except BaseException:
                src.write_bytes(old)
                raise
        print('JP ROM, exact v11 renderer, v10 cache, v8 interpreter, v7 State and originals: PASS')
        print('v12: '+('installed; native rebuild needed' if a.confirm_modify_private_rt64 else 'validated only'))
        print('State: '+str(src))
    except (OSError, ValueError, UnicodeError) as exc:p.error(str(exc))
    return 0

if __name__=='__main__':raise SystemExit(main())