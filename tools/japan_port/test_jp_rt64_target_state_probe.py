#!/usr/bin/env python3
"""Fail-closed source anchors and compiled native C++ fixture for v9 only."""
from __future__ import annotations
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
import jp_rt64_target_state_probe as v9
import jp_rt64_raster_handoff_probe as v8

class V9SourceTests(unittest.TestCase):
    def fixture(self):
        return (f'// {v8.MARKER}\n' + v9.TAG_FIELDS_OLD + v9.TAG_INIT_OLD + v9.TAG_OLD +
                v9.RESET_OLD + v9.ADD_OLD + v9.RECORD_OLD + v9.DRAW_OLD)

    def test_exact_anchors(self):
        output=v9.transform(self.fixture())
        self.assertIn(v9.MARKER,output)
        for fragment in (v9.TAG_FIELDS_NEW,v9.TAG_INIT_NEW,v9.TAG_NEW,v9.RESET_NEW,
                         v9.ADD_NEW,v9.RECORD_NEW,v9.DRAW_NEW):
            self.assertIn(fragment,output)

    def test_refuse_reapply(self):
        with self.assertRaisesRegex(ValueError,'already installed'):
            v9.transform(v9.transform(self.fixture()))

    def test_refuse_missing_v8(self):
        with self.assertRaisesRegex(ValueError,'v8 required'):
            v9.transform(self.fixture().replace(v8.MARKER,''))

    def test_refuse_duplicate_anchor(self):
        with self.assertRaisesRegex(ValueError,'exactly once'):
            v9.transform(self.fixture()+v9.ADD_OLD)

    def test_verify_installed_exact_v9_is_readonly(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            rt64=Path(d)
            src=rt64/v9.RENDER
            src.parent.mkdir(parents=True)
            src.with_name(src.name+v8.BACKUP_SUFFIX).write_text('original-pinned-renderer')
            expected_v8=self.fixture()
            expected_v9=v9.transform(expected_v8)
            src.write_text(expected_v9)
            src.with_name(src.name+v9.BACKUP).write_text(expected_v8)
            with mock.patch.object(v9.v4,'validate_rom'), \
                 mock.patch.object(v9.v4,'blob_hash',return_value=v8.RENDER_ORIGINAL_GIT_BLOB), \
                 mock.patch.object(v8,'transform_renderer',return_value=expected_v8), \
                 mock.patch.object(v9,'_validate_dependent_rt64_sources') as validate_dep:
                self.assertEqual(v9.verify_installed(rt64,Path('any')),src)
                validate_dep.assert_called_once_with(rt64)
                self.assertEqual(src.read_text(),expected_v9)
                self.assertEqual(src.with_name(src.name+v9.BACKUP).read_text(),expected_v8)
                with self.assertRaisesRegex(ValueError,'v9 appears already installed'):
                    v9.plan(rt64,Path('any'))

    def test_verify_refuses_invalid_v9_backup_or_changed_renderer(self):
        from unittest import mock
        with tempfile.TemporaryDirectory() as d:
            rt64=Path(d)
            src=rt64/v9.RENDER
            src.parent.mkdir(parents=True)
            src.with_name(src.name+v8.BACKUP_SUFFIX).write_text('original-pinned-renderer')
            expected_v8=self.fixture()
            expected_v9=v9.transform(expected_v8)
            src.write_text(expected_v9)
            saved=src.with_name(src.name+v9.BACKUP)
            saved.write_text('changed-backup')
            with mock.patch.object(v9.v4,'validate_rom'), \
                 mock.patch.object(v9.v4,'blob_hash',return_value=v8.RENDER_ORIGINAL_GIT_BLOB), \
                 mock.patch.object(v8,'transform_renderer',return_value=expected_v8), \
                 mock.patch.object(v9,'_validate_dependent_rt64_sources'):
                with self.assertRaisesRegex(ValueError,'v9 backup does not match'):
                    v9.verify_installed(rt64,Path('any'))
                saved.write_text(expected_v8)
                src.write_text(expected_v9+'// unsafe drift')
                with self.assertRaisesRegex(ValueError,'not exact pinned v9'):
                    v9.verify_installed(rt64,Path('any'))

    @unittest.skipUnless(shutil.which('g++'),'g++ not installed')
    def test_real_compiled_cxx_context_helper(self):
        program='''#include <cstdint>\n#include <cstdio>\n#include <cinttypes>\n#include <climits>\n\n'''+'''
struct Rect {int left=1,top=2,right=3,bottom=4;};
struct Mode {
    uint32_t L=0x0ABCDEF1,H=0x0BE01234;
    uint32_t alphaCompare()const{return L&3u;}
    uint32_t zMode()const{return L&0xC00u;}
    bool forceBlend()const{return (L&0x4000u)!=0;}
    bool cvgXAlpha()const{return (L&0x1000u)!=0;}
    bool alphaCvgSel()const{return (L&0x2000u)!=0;}
    bool zCmp()const{return (L&0x10u)!=0;}
    bool zUpd()const{return (L&0x20u)!=0;}
};
struct ShaderDesc{Mode otherMode;struct{bool culling=true;}flags;};
struct InstanceDrawCall {
    enum class Type { Unknown,Raytracing,IndexedTriangles,RawTriangles};
    Type type=Type::IndexedTriangles;
    struct {ShaderDesc shaderDesc;unsigned faceCount=8;Rect scissor;} triangles;
};
struct GoemonRobotRasterTag{unsigned instance,root,sample,overlap,call;uint64_t frame;};
thread_local GoemonRobotRasterTag goemonRobotRasterTags[256];
thread_local unsigned goemonRobotRasterTagCount=0;
'''+v9.TAG_NEW[len(v9.TAG_OLD):]+'''
int main(){
  goemonRobotRasterTagCount=1;
  goemonRobotRasterTags[0]={5,0x1938,1,8,145,893};
  goemonJPV9CurrentTarget=0;
  goemonJPV9Targets[0]={893,3,0x12C000,0x16D000,0x12C000,0x16D000,true};
  InstanceDrawCall call;
  goemon_jp_rt64_target_state_log(5,call);
  goemon_jp_rt64_target_state_log(6,call); // no duplicate tag
  call.type=InstanceDrawCall::Type::RawTriangles;
  goemon_jp_rt64_target_state_log(5,call); // non-indexed omitted
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'fixture.cpp';src.write_text(program)
            exe=Path(d)/'probe'
            comp=subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(comp.returncode,0,comp.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(run.stderr.count('[JP-RT64] TARGET_STATE'),1,run.stderr)
            self.assertIn('call=145 target=0 fbpair=3',run.stderr)
            self.assertIn('other_h=0x0BE01234',run.stderr)

if __name__=='__main__':unittest.main()