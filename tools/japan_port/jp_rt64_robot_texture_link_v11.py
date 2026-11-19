#!/usr/bin/env python3
"""Fail-closed v10->v11 private RT64 robot-GameCall texture-hash link.

Appends bounded, opt-in, read-only GameCall->DrawCallTile metadata logging to
an already authenticated RT64 v10 renderer. No shader/texture/ROM modifications.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import jp_rt64_texture_origin_probe as v10

MARKER = 'GOEMON_JP_RT64_ROBOT_TEXTURE_V11'
BACKUP = '.pre-jp-robot-texture-v11'
RENDERER = v10.RENDER

# The RASTER BUILT block was added by exactly pinned v8 and extended by v9;
# v10 does not edit this block. The adjacent lines form a uniquely anchored
# insertion point inside the per-robot range overlap loop.
ROBOT_ANCHOR = '''                                 unsigned(!raster_tri || instanceDrawCall.triangles.pipeline != nullptr));
                    if (goemonRobotRasterTagCount < 256u) {
'''
ROBOT_INSERT = '''                                 unsigned(!raster_tri || instanceDrawCall.triangles.pipeline != nullptr));
                    // GOEMON_JP_RT64_ROBOT_TEXTURE_V11: bounded robot-only hash provenance.
                    if (goemonJPV10TexTraceOn() &&
                        goemonJPV11RobotCalls.fetch_add(1, std::memory_order_relaxed) < 1024u) {
                        const auto firstTile = static_cast<size_t>(call.callDesc.tileIndex);
                        const auto tileCount = static_cast<size_t>(call.callDesc.tileCount);
                        const auto remaining = firstTile < drawData.callTiles.size()
                            ? drawData.callTiles.size() - firstTile : 0u;
                        const auto safeCount = std::min(std::min(tileCount, remaining), size_t(8u));
                        std::fprintf(stderr,
                            "[JP-RT64] TEX_ROBOT_CALL frame=%llu root=0x%04X sample=%u "
                            "call=%u tri=%u overlap=%u tile_start=%zu tile_count=%zu safe_count=%zu "
                            "texture_on=%u texture_tile=%u\\n",
                            static_cast<unsigned long long>(p.curWorkload->submissionFrame),
                            root, sample, unsigned(call.callDesc.callIndex),
                            unsigned(call.callDesc.triangleCount), overlap, firstTile,
                            tileCount, safeCount, unsigned(call.callDesc.textureOn),
                            unsigned(call.callDesc.textureTile));
                        for (size_t local = 0; local < safeCount; ++local) {
                            const auto& tile = drawData.callTiles[firstTile + local];
                            if (!tile.valid) {
                                std::fprintf(stderr,
                                    "[JP-RT64] TEX_ROBOT_TILE frame=%llu root=0x%04X sample=%u "
                                    "call=%u slot=%zu index=%zu valid=0\\n",
                                    static_cast<unsigned long long>(p.curWorkload->submissionFrame),
                                    root, sample, unsigned(call.callDesc.callIndex),
                                    local, firstTile + local);
                                continue;
                            }
                            std::fprintf(stderr,
                                "[JP-RT64] TEX_ROBOT_TILE frame=%llu root=0x%04X sample=%u "
                                "call=%u slot=%zu index=%zu valid=1 "
                                "hash=0x%016llX copy=%u requested=%ux%u "
                                "fmt=%u siz=%u tmem=%u line=%u tlut=%u palette=%u raw_tmem=%u\\n",
                                static_cast<unsigned long long>(p.curWorkload->submissionFrame),
                                root, sample, unsigned(call.callDesc.callIndex),
                                local, firstTile + local,
                                static_cast<unsigned long long>(tile.tmemHashOrID),
                                unsigned(tile.tileCopyUsed),
                                unsigned(tile.sampleWidth), unsigned(tile.sampleHeight),
                                unsigned(tile.loadTile.fmt), unsigned(tile.loadTile.siz),
                                unsigned(tile.loadTile.tmem), unsigned(tile.loadTile.line),
                                unsigned(tile.tlut), unsigned(tile.loadTile.palette),
                                unsigned(tile.rawTMEM));
                        }
                    }
                    if (goemonRobotRasterTagCount < 256u) {
'''

ATOM_OLD = '        std::atomic<unsigned> goemonJPV10BindRows{0};\n'
ATOM_NEW = ATOM_OLD + '        std::atomic<unsigned> goemonJPV11RobotCalls{0}; // GOEMON_JP_RT64_ROBOT_TEXTURE_V11\n'


def transform_renderer(source: str) -> str:
    if MARKER in source:
        raise ValueError('v11 already installed; no changes made')
    if v10.MARKER not in source:
        raise ValueError('exact installed v10 renderer required')
    source = v10.one(source, ATOM_OLD, ATOM_NEW, 'v10 tex trace helper')
    source = v10.one(source, ROBOT_ANCHOR, ROBOT_INSERT, 'v8/v9 robot GameCall site')
    return source


def plan(rt64_dir: Path, rom: Path) -> tuple[Path, bytes, bytes]:
    # Validate the exact installed v10 source without invoking v10.validate_base,
    # which intentionally accepts only *unpatched v9* as its own prerequisite.
    v10.v4.validate_rom(rom)
    renderer=rt64_dir/RENDERER
    cache=rt64_dir/v10.CACHE
    original_renderer=renderer.with_name(renderer.name+v10.v8.BACKUP_SUFFIX).read_bytes()
    if v10.git_blob_sha(original_renderer)!=v10.v8.RENDER_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned original renderer backup changed')
    expected_v8=v10.v8.transform_renderer(original_renderer.decode('utf-8')).encode('utf-8')
    if renderer.with_name(renderer.name+v10.v9.BACKUP).read_bytes()!=expected_v8:
        raise ValueError('renderer v9 backup differs from exact v8')
    expected_v9=v10.v9.transform(expected_v8.decode('utf-8')).encode('utf-8')
    if renderer.with_name(renderer.name+v10.RENDER_BACKUP).read_bytes()!=expected_v9:
        raise ValueError('renderer v10 backup differs from exact v9')
    expected_v10=v10.transform_renderer(expected_v9.decode('utf-8')).encode('utf-8')
    existing_renderer=renderer.read_bytes()
    if existing_renderer!=expected_v10:
        raise ValueError('installed renderer differs from deterministic v10 source; no changes')
    original_cache=cache.with_name(cache.name+v10.CACHE_BACKUP).read_bytes()
    if v10.git_blob_sha(original_cache)!=v10.CACHE_GIT_BLOB:
        raise ValueError('pinned original texture-cache backup changed')
    expected_cache=v10.transform_cache(original_cache.decode('utf-8')).encode('utf-8')
    if cache.read_bytes()!=expected_cache:
        raise ValueError('installed cache differs from deterministic v10 source; no changes')
    interpreter=rt64_dir/v10.v4.RELATIVE
    pristine_inter=interpreter.with_name(interpreter.name+'.pre-jp-robot-probe').read_bytes()
    if v10.git_blob_sha(pristine_inter)!=v10.v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('pinned interpreter original backup changed')
    expected_inter=v10.v8.transform_interpreter(v10.v7.transform_interpreter(
        v10.v6.transform(v10.v5.transform(v10.v4.transform(pristine_inter.decode('utf-8')))))).encode('utf-8')
    if interpreter.read_bytes()!=expected_inter:
        raise ValueError('interpreter differs from exact v8 source chain')
    state=rt64_dir/v10.v7.STATE
    original_state=state.with_name(state.name+v10.v7.BACKUP_SUFFIX).read_bytes()
    if v10.git_blob_sha(original_state)!=v10.v7.STATE_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned state original backup changed')
    if state.read_bytes()!=v10.v7.transform_state(original_state.decode('utf-8')).encode('utf-8'):
        raise ValueError('state differs from deterministic v7 source')
    if renderer.with_name(renderer.name+BACKUP).exists():
        raise ValueError('v11 renderer backup already exists; refusing reapply')
    modified=transform_renderer(existing_renderer.decode('utf-8')).encode('utf-8')
    return renderer,existing_renderer,modified


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run',action='store_true')
    g.add_argument('--confirm-modify-private-rt64',action='store_true')
    a=p.parse_args()
    try:
        path,old,new=plan(a.rt64_dir,a.rom)
        if a.confirm_modify_private_rt64:
            backup=path.with_name(path.name+BACKUP)
            backup.write_bytes(old)
            try:path.write_bytes(new)
            except BaseException:
                path.write_bytes(old)
                raise
        print('JP ROM, exact v10 renderer/cache, pinned originals and all backups: PASS')
        print('v11: '+('installed; native rebuild needed' if a.confirm_modify_private_rt64 else 'validated only'))
        print('renderer: '+str(path))
    except (OSError,ValueError,UnicodeError) as ex:p.error(str(ex))
    return 0

if __name__=='__main__':raise SystemExit(main())