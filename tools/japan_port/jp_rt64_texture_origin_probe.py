#!/usr/bin/env python3
"""Fail-closed opt-in v9->v10 read-only RT64 texture-origin recorder.

Tracks 32x64 TMEM queue -> GPU decode creation serial -> cache-index insertion
-> render binding, including hashes and nonzero-byte counts. No GPU readback,
texture mutation, graphics-pipeline changes, game code, or ROM changes.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import jp_rt64_robot_probe as v4
import jp_rt64_triangle_gate_probe as v5
import jp_rt64_face_index_probe as v6
import jp_rt64_drawcall_account_probe as v7
import jp_rt64_raster_handoff_probe as v8
import jp_rt64_target_state_probe as v9

MARKER = 'GOEMON_JP_RT64_TEXTURE_ORIGIN_V10'
CACHE = Path('src/render/rt64_texture_cache.cpp')
RENDER = Path('src/render/rt64_framebuffer_renderer.cpp')
RENDER_BACKUP = '.pre-jp-texture-origin-v10'
CACHE_BACKUP = '.pre-jp-texture-origin-v10'
CACHE_GIT_BLOB = '0848f3eda2b9577b54b4549ee8b168957a07545e'

# The exact default RT64 v9 renderer is authenticated by reconstructing the
# published v4-v9 transformations from its verified pristine v8 backup.
RENDER_INCLUDE = '#include "rt64_framebuffer_renderer.h"\n'
CACHE_INCLUDE = '#include "rt64_texture_cache.h"\n'
NAMESPACE = 'namespace RT64 {\n    // Helper functions.\n'
INCLUDES = '#include <atomic>\n#include <cstdio>\n#include <cstdlib>\n#include <cstring>\n'

RENDER_HELPER = '''    // GOEMON_JP_RT64_TEXTURE_ORIGIN_V10: read-only, opt-in 32x64 tile trace.
    namespace {
        bool goemonJPV10TexTraceOn() {
            const char* e = std::getenv("GOEMON_JP_RT64_TEX_TRACE");
            return e && e[0] == '1' && e[1] == '\\0';
        }
        std::atomic<unsigned> goemonJPV10BindRows{0};
    }
'''
CACHE_HELPER = '''    // GOEMON_JP_RT64_TEXTURE_ORIGIN_V10: read-only, opt-in upload correlation.
    namespace {
        bool goemonJPV10TexTraceOn() {
            const char* e = std::getenv("GOEMON_JP_RT64_TEX_TRACE");
            return e && e[0] == '1' && e[1] == '\\0';
        }
        std::atomic<unsigned> goemonJPV10UploadRows{0};
        std::atomic<unsigned> goemonJPV10CreateRows{0};
        std::atomic<unsigned> goemonJPV10AddRows{0};
    }
'''

BIND_OLD = '''                textureCache->useTexture(callTile.tmemHashOrID, submissionFrame, textureIndex, gpuTile.tcScale, gpuTile.textureDimensions, textureReplaced, hasMipmaps, shiftedByHalf);\n'''
BIND_NEW = '''                const bool goemonJPV10CacheHit = textureCache->useTexture(callTile.tmemHashOrID, submissionFrame, textureIndex, gpuTile.tcScale, gpuTile.textureDimensions, textureReplaced, hasMipmaps, shiftedByHalf);
                // A binding can be absent even with a nonzero TMEM hash; do not
                // read GPU tile dimensions unless the cache lookup succeeded.
                if (goemonJPV10TexTraceOn() &&
                    ((callTile.sampleWidth == 32 && callTile.sampleHeight == 64) ||
                     (goemonJPV10CacheHit && gpuTile.textureDimensions.x == 32.0f && gpuTile.textureDimensions.y == 64.0f)) &&
                    goemonJPV10BindRows.fetch_add(1, std::memory_order_relaxed) < 30000u) {
                    std::fprintf(stderr,
                        "[JP-RT64] TEX_BIND frame=%llu hash=0x%016llX cache_index=%u hit=%u "
                        "requested=%ux%u cached=%.0fx%.0f fmt=%u siz=%u tmem=%u line=%u "
                        "tlut=%u palette=%u raw_tmem=%u replaced=%u\\n",
                        static_cast<unsigned long long>(submissionFrame),
                        static_cast<unsigned long long>(callTile.tmemHashOrID),
                        textureIndex, unsigned(goemonJPV10CacheHit),
                        unsigned(callTile.sampleWidth), unsigned(callTile.sampleHeight),
                        goemonJPV10CacheHit ? double(gpuTile.textureDimensions.x) : 0.0,
                        goemonJPV10CacheHit ? double(gpuTile.textureDimensions.y) : 0.0,
                        unsigned(callTile.loadTile.fmt), unsigned(callTile.loadTile.siz),
                        unsigned(callTile.loadTile.tmem), unsigned(callTile.loadTile.line),
                        unsigned(callTile.tlut), unsigned(callTile.loadTile.palette),
                        unsigned(callTile.rawTMEM), unsigned(textureReplaced));
                }
'''

QUEUE_OLD = '        newUpload.decodeTMEM = decodeTMEM;\n'
QUEUE_NEW = QUEUE_OLD + '''
        if (goemonJPV10TexTraceOn() && width == 32 && height == 64 &&
            goemonJPV10UploadRows.fetch_add(1, std::memory_order_relaxed) < 30000u) {
            unsigned nonzero = 0;
            unsigned long long checksum = 14695981039346656037ull;
            for (uint8_t b : newUpload.bytesTMEM) {
                nonzero += (b != 0);
                checksum ^= b;
                checksum *= 1099511628211ull;
            }
            std::fprintf(stderr,
                "[JP-RT64] TEX_QUEUE frame=%llu hash=0x%016llX "
                "size=%dx%d decode=%u tmem_bytes=%zu nonzero=%u "
                "fingerprint=0x%016llX fmt=%u siz=%u tmem=%u line=%u "
                "tlut=%u palette=%u\\n",
                static_cast<unsigned long long>(creationFrame),
                static_cast<unsigned long long>(hash), width, height,
                unsigned(decodeTMEM), newUpload.bytesTMEM.size(), nonzero,
                checksum, unsigned(loadTile.fmt), unsigned(loadTile.siz),
                unsigned(loadTile.tmem), unsigned(loadTile.line),
                unsigned(tlut), unsigned(loadTile.palette));
        }
'''
CREATE_OLD = '                        dstTexture->texture->setName("Texture Cache RGBA32 #" + std::to_string(TextureGlobalCounter++));\n'
CREATE_NEW = CREATE_OLD + '''                        // Counter in resource name increments at creation, not cache insertion.
                        if (goemonJPV10TexTraceOn() && upload.width == 32 && upload.height == 64 &&
                            goemonJPV10CreateRows.fetch_add(1, std::memory_order_relaxed) < 30000u) {
                            std::fprintf(stderr,
                                "[JP-RT64] TEX_CREATE serial=%u frame=%llu hash=0x%016llX "
                                "size=%ux%u fmt=%u siz=%u tmem=%u line=%u tlut=%u palette=%u\\n",
                                TextureGlobalCounter - 1,
                                static_cast<unsigned long long>(upload.creationFrame),
                                static_cast<unsigned long long>(upload.hash),
                                upload.width, upload.height,
                                unsigned(upload.loadTile.fmt), unsigned(upload.loadTile.siz),
                                unsigned(upload.loadTile.tmem), unsigned(upload.loadTile.line),
                                unsigned(upload.tlut), unsigned(upload.loadTile.palette));
                        }
'''
ADD_OLD = '                        textureMap.add(addition.hash, addition.texture->creationFrame, addition.texture);\n'
ADD_NEW = ADD_OLD + '''                        if (goemonJPV10TexTraceOn() && addition.texture->width == 32 && addition.texture->height == 64 &&
                            goemonJPV10AddRows.fetch_add(1, std::memory_order_relaxed) < 30000u) {
                            const auto goemonJPV10It = textureMap.hashMap.find(addition.hash);
                            if (goemonJPV10It != textureMap.hashMap.end()) {
                                std::fprintf(stderr,
                                    "[JP-RT64] TEX_ADD frame=%llu hash=0x%016llX cache_index=%u "
                                    "size=%ux%u decoded=%u\\n",
                                    static_cast<unsigned long long>(addition.texture->creationFrame),
                                    static_cast<unsigned long long>(addition.hash),
                                    unsigned(goemonJPV10It->second),
                                    unsigned(addition.texture->width), unsigned(addition.texture->height),
                                    unsigned(addition.texture->decodeTMEM));
                            }
                        }
'''


def git_blob_sha(b:bytes)->str:
    return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()


def one(s:str,old:str,new:str,label:str)->str:
    c=s.count(old)
    if c != 1:
        raise ValueError(f'{label}: expected exactly one pinned anchor; found {c}')
    return s.replace(old,new,1)


def transform_renderer(source:str)->str:
    if MARKER in source:raise ValueError('v10 renderer already installed')
    if v9.MARKER not in source:raise ValueError('exact installed v9 renderer required')
    source=one(source,RENDER_INCLUDE,RENDER_INCLUDE+INCLUDES,'renderer include')
    source=one(source,NAMESPACE,NAMESPACE+RENDER_HELPER,'renderer namespace')
    source=one(source,BIND_OLD,BIND_NEW,'cache lookup')
    return source


def transform_cache(source:str)->str:
    if MARKER in source:raise ValueError('v10 cache already installed')
    source=one(source,CACHE_INCLUDE,CACHE_INCLUDE+INCLUDES,'cache include')
    source=one(source,NAMESPACE,NAMESPACE+CACHE_HELPER,'cache namespace')
    for old,new,label in [
        (QUEUE_OLD,QUEUE_NEW,'queue input'),
        (CREATE_OLD,CREATE_NEW,'decode creation'),
        (ADD_OLD,ADD_NEW,'index assignment')]:
        source=one(source,old,new,label)
    return source


def validate_base(rt64:Path,rom:Path)->tuple[Path,bytes,Path,bytes]:
    v4.validate_rom(rom)
    renderer=rt64/RENDER
    cache=rt64/CACHE
    original_renderer=renderer.with_name(renderer.name+v8.BACKUP_SUFFIX).read_bytes()
    if git_blob_sha(original_renderer)!=v8.RENDER_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned original renderer backup changed')
    expected_v8=v8.transform_renderer(original_renderer.decode('utf-8')).encode('utf-8')
    v9_backup=renderer.with_name(renderer.name+v9.BACKUP)
    if v9_backup.read_bytes()!=expected_v8:
        raise ValueError('v9 renderer backup is not exact v8')
    expected_v9=v9.transform(expected_v8.decode('utf-8')).encode('utf-8')
    if renderer.read_bytes()!=expected_v9:
        raise ValueError('renderer differs from exact published v9; no changes')
    original_cache=cache.read_bytes()
    if git_blob_sha(original_cache)!=CACHE_GIT_BLOB:
        raise ValueError('texture cache differs from untouched pinned RT64; no changes')
    # V9's interpreter and state were validated before v9; check them again.
    interpreter=rt64/v4.RELATIVE
    original_inter=interpreter.with_name(interpreter.name+'.pre-jp-robot-probe').read_bytes()
    if git_blob_sha(original_inter)!=v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('pinned interpreter backup changed')
    expected_inter=v8.transform_interpreter(v7.transform_interpreter(
        v6.transform(v5.transform(v4.transform(original_inter.decode('utf-8')))))).encode('utf-8')
    if interpreter.read_bytes()!=expected_inter:
        raise ValueError('interpreter differs from exact v8 chain')
    state=rt64/v7.STATE
    original_state=state.with_name(state.name+v7.BACKUP_SUFFIX).read_bytes()
    if git_blob_sha(original_state)!=v7.STATE_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned state backup changed')
    if state.read_bytes()!=v7.transform_state(original_state.decode('utf-8')).encode('utf-8'):
        raise ValueError('state differs from exact v7 chain')
    return renderer,expected_v9,cache,original_cache


def plan(rt64:Path,rom:Path)->list[tuple[Path,bytes,bytes]]:
    renderer,original_renderer,cache,original_cache=validate_base(rt64,rom)
    results=[(renderer,original_renderer,transform_renderer(original_renderer.decode('utf-8')).encode('utf-8')),
             (cache,original_cache,transform_cache(original_cache.decode('utf-8')).encode('utf-8'))]
    for path,_,_ in results:
        if path.with_name(path.name+RENDER_BACKUP).exists():
            raise ValueError(f'existing v10 backup for {path}; refusing reapply')
    return results


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',required=True,type=Path)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run',action='store_true')
    g.add_argument('--confirm-modify-private-rt64',action='store_true')
    a=p.parse_args()
    try:
        edits=plan(a.rt64_dir,a.rom)
        if a.confirm_modify_private_rt64:
            for path,old,_ in edits:
                path.with_name(path.name+RENDER_BACKUP).write_bytes(old)
            try:
                for path,_,new in edits:path.write_bytes(new)
            except BaseException:
                for path,old,_ in edits:path.write_bytes(old)
                raise
        print('JP ROM, pinned RT64 originals, v9 renderer, v8 interpreter, v7 state: PASS')
        print('v10: '+('installed; rebuild needed' if a.confirm_modify_private_rt64 else 'validated only'))
        for path,_,_ in edits:print('source:',path)
    except (OSError,ValueError,UnicodeError) as err:p.error(str(err))
    return 0

if __name__=='__main__':raise SystemExit(main())