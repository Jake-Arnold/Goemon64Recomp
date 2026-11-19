#!/usr/bin/env python3
"""Fail-closed opt-in v9 context logger for already instrumented v8 RT64.

Read-only metadata capture: per repeated host graphics command record the physical
framebuffer, render-target identities, and material alpha/depth/cull fields.
Does not change renderer logic, shaders, GPU commands, assets or ROM.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import jp_rt64_robot_probe as v4
import jp_rt64_triangle_gate_probe as v5
import jp_rt64_face_index_probe as v6
import jp_rt64_drawcall_account_probe as v7
import jp_rt64_raster_handoff_probe as v8

MARKER='GOEMON_JP_RT64_TARGET_STATE_V9'
BACKUP='.pre-jp-target-state-v9'
RENDER=v8.RT64_RENDERER

TAG_OLD='''        thread_local unsigned goemonRobotRasterTagCount = 0;\n'''
TAG_FIELDS_OLD='''            uint32_t instance = 0, root = 0, sample = 0, overlap = 0;\n'''
TAG_FIELDS_NEW='''            uint32_t instance = 0, root = 0, sample = 0, overlap = 0;\n            uint32_t call = 0;\n            uint64_t frame = 0;\n'''
TAG_INIT_OLD='''                            uint32_t(instanceDrawCallVector.size()), root, sample, overlap};\n'''
TAG_INIT_NEW='''                            uint32_t(instanceDrawCallVector.size()), root, sample, overlap,\n                            call.callDesc.callIndex, p.curWorkload->submissionFrame};\n'''
TAG_NEW=TAG_OLD+r'''        // GOEMON_JP_RT64_TARGET_STATE_V9: read-only render-target context.
        struct GoemonJPV9Target {
            uint64_t frame = 0;
            uint32_t fbPair = 0;
            uint32_t color = 0, depth = 0;
            uint32_t colorTarget = 0, depthTarget = 0;
            bool valid = false;
        };
        thread_local GoemonJPV9Target goemonJPV9Targets[512];
        thread_local uint32_t goemonJPV9CurrentTarget = UINT32_MAX;

        void goemon_jp_rt64_target_state_log(uint32_t instance,
                                              const InstanceDrawCall& drawCall) {
            if (goemonJPV9CurrentTarget >= 512u) return;
            const auto& target = goemonJPV9Targets[goemonJPV9CurrentTarget];
            if (!target.valid || drawCall.type != InstanceDrawCall::Type::IndexedTriangles) return;
            const auto& tris = drawCall.triangles;
            const auto& mode = tris.shaderDesc.otherMode;
            for (unsigned k = 0; k < goemonRobotRasterTagCount; ++k) {
                const auto& tag = goemonRobotRasterTags[k];
                if (tag.instance != instance) continue;
                std::fprintf(stderr,
                    "[JP-RT64] TARGET_STATE root=0x%04X sample=%u "
                    "frame=%llu source_frame=%llu call=%u target=%u fbpair=%u instance=%u "
                    "color=0x%08X depth=0x%08X "
                    "color_target=0x%08X depth_target=0x%08X "
                    "overlap_tri=%u face_count=%u "
                    "other_h=0x%08X other_l=0x%08X "
                    "alpha_compare=0x%08X force_blend=%u "
                    "cvg_x_alpha=%u alpha_cvg_sel=%u "
                    "zcmp=%u zupd=%u zmode=0x%08X culling=%u "
                    "scissor=%d,%d,%d,%d\n",
                    tag.root, tag.sample,
                    static_cast<unsigned long long>(target.frame),
                    static_cast<unsigned long long>(tag.frame), tag.call,
                    goemonJPV9CurrentTarget, target.fbPair, instance,
                    target.color, target.depth, target.colorTarget, target.depthTarget,
                    tag.overlap, tris.faceCount,
                    mode.H, mode.L, mode.alphaCompare(),
                    unsigned(mode.forceBlend()), unsigned(mode.cvgXAlpha()),
                    unsigned(mode.alphaCvgSel()), unsigned(mode.zCmp()),
                    unsigned(mode.zUpd()), mode.zMode(),
                    unsigned(tris.shaderDesc.flags.culling),
                    tris.scissor.left, tris.scissor.top,
                    tris.scissor.right, tris.scissor.bottom);
            }
        }
'''

RESET_OLD='''        goemonRobotRasterTagCount = 0; // GOEMON_JP_RT64_RASTER_HANDOFF_V8\n'''
RESET_NEW=RESET_OLD+'''        goemonJPV9CurrentTarget = UINT32_MAX; // GOEMON_JP_RT64_TARGET_STATE_V9\n        for (auto& entry : goemonJPV9Targets) entry.valid = false;\n'''
ADD_OLD='''        framebufferCount++;\n'''
ADD_NEW=ADD_OLD+'''        // v9: associate each physical renderer framebuffer with its guest images.
        if (framebufferCount <= 512u) {
            auto& entry = goemonJPV9Targets[framebufferCount - 1u];
            entry.frame = p.curWorkload->submissionFrame;
            entry.fbPair = p.fbPairIndex;
            entry.color = fbPair.colorImage.address;
            entry.depth = fbPair.depthImage.address;
            entry.colorTarget = p.fbStorage->colorTarget ? p.fbStorage->colorTarget->addressForName : 0u;
            entry.depthTarget = p.fbStorage->depthTarget ? p.fbStorage->depthTarget->addressForName : 0u;
            entry.valid = true;
        }
'''
RECORD_OLD='''        const Framebuffer &framebuffer = framebufferVector[framebufferIndex];\n'''
RECORD_NEW=RECORD_OLD+'''        goemonJPV9CurrentTarget = framebufferIndex; // GOEMON_JP_RT64_TARGET_STATE_V9\n'''
DRAW_OLD='''                goemon_jp_rt64_raster_log(i, "DRAW_RECORDED", triangles.faceCount, false);\n'''
DRAW_NEW=DRAW_OLD+'''                goemon_jp_rt64_target_state_log(i, drawCall); // GOEMON_JP_RT64_TARGET_STATE_V9\n'''


def replace_one(text:str,old:str,new:str,label:str)->str:
    cnt=text.count(old)
    if cnt!=1: raise ValueError(f'{label} expected exactly once, found {cnt}; no changes made')
    return text.replace(old,new,1)


def transform(source:str)->str:
    if MARKER in source:raise ValueError('v9 already installed')
    if v8.MARKER not in source:raise ValueError('v8 required')
    for before,after,label in [
        (TAG_FIELDS_OLD,TAG_FIELDS_NEW,'source GameCall identity'),
        (TAG_INIT_OLD,TAG_INIT_NEW,'source GameCall tag initialization'),
        (TAG_OLD,TAG_NEW,'tag context'),
        (RESET_OLD,RESET_NEW,'frame reset'),
        (ADD_OLD,ADD_NEW,'render-target assign'),
        (RECORD_OLD,RECORD_NEW,'record target'),
        (DRAW_OLD,DRAW_NEW,'host draw context')]:
        source=replace_one(source,before,after,label)
    return source


def plan(rt64:Path,rom:Path)->tuple[Path,bytes,bytes]:
    v4.validate_rom(rom)
    renderer=rt64/RENDER
    original=renderer.with_name(renderer.name+v8.BACKUP_SUFFIX).read_bytes()
    if v4.blob_hash(original)!=v8.RENDER_ORIGINAL_GIT_BLOB:
        raise ValueError('pinned untouched RT64 renderer backup mismatch')
    installed=renderer.read_bytes()
    expected=v8.transform_renderer(original.decode('utf-8')).encode('utf-8')
    if installed!=expected:
        raise ValueError('installed RT64 renderer differs from exact v8 source; no changes')
    if renderer.with_name(renderer.name+BACKUP).exists():
        raise ValueError('v9 backup already exists; refuse repeated patch')
    # Check that the corresponding source-only interpreter and state remain exact.
    interpreter=rt64/v4.RELATIVE
    pristine_inter=interpreter.with_name(interpreter.name+'.pre-jp-robot-probe').read_bytes()
    if v4.blob_hash(pristine_inter)!=v4.ORIGINAL_BLOB_SHA1:
        raise ValueError('original interpreter mismatch')
    expected_inter=v8.transform_interpreter(v7.transform_interpreter(
        v6.transform(v5.transform(v4.transform(pristine_inter.decode('utf-8')))))).encode('utf-8')
    if interpreter.read_bytes()!=expected_inter:
        raise ValueError('interpreter no longer equals exact v8 chain')
    state=rt64/v7.STATE
    original_state=state.with_name(state.name+v7.BACKUP_SUFFIX).read_bytes()
    if v4.blob_hash(original_state)!=v7.STATE_ORIGINAL_GIT_BLOB:
        raise ValueError('original RT64 state mismatch')
    if state.read_bytes()!=v7.transform_state(original_state.decode('utf-8')).encode('utf-8'):
        raise ValueError('RT64 state differs from exact v7 transform')
    return renderer,installed,transform(installed.decode('utf-8')).encode('utf-8')


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',required=True,type=Path)
    p.add_argument('--rt64-dir',type=Path,default=Path('lib/rt64'))
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--dry-run',action='store_true')
    g.add_argument('--confirm-modify-private-rt64',action='store_true')
    a=p.parse_args()
    try:
        dest,old,new=plan(a.rt64_dir,a.rom)
        if a.confirm_modify_private_rt64:
            backup=dest.with_name(dest.name+BACKUP)
            backup.write_bytes(old)
            try:dest.write_bytes(new)
            except BaseException:
                dest.write_bytes(old)
                raise
        print('exact v8 RT64 sources, original backup and JP ROM: PASS')
        print('v9 mode: '+('installed; relink needed' if a.confirm_modify_private_rt64 else 'validated only'))
        print('renderer: '+str(dest))
    except (OSError,ValueError,UnicodeError) as ex:p.error(str(ex))
    return 0

if __name__=='__main__':raise SystemExit(main())