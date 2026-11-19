"""ROM-free v8 exact-source-gated model tests plus compiled live C++ correlation helper."""
from __future__ import annotations
import subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jp_rt64_robot_probe as v4
import jp_rt64_triangle_gate_probe as v5
import jp_rt64_face_index_probe as v6
import jp_rt64_drawcall_account_probe as v7
import jp_rt64_raster_handoff_probe as v8


def mock_interpreter_original():
    return '// dummy original\n' + v4.INCLUDES + v4.NAMESPACE + v4.CMD_ANCHOR + v4.CALL_ANCHOR

def mock_v7():
    return v7.transform_interpreter(v6.transform(v5.transform(v4.transform(mock_interpreter_original()))))

def mock_state_original():
    return '// dummy state\n' + v7.STATE_NS_OLD + 'struct State {};\n' + v7.STATE_FLUSH_OLD

def mock_renderer_original():
    return '''// dummy renderer\n''' + v8.RENDER_INCLUDE + v8.RENDER_NAMESPACE + '''void dummy() {\n''' + \
       v8.RENDER_RESET_OLD + v8.RENDER_SKIP_PROJECTION_OLD + v8.RENDER_INSTANCE_OLD + \
       v8.RENDER_SKIP_SCISSOR_OLD + v8.RENDER_DRAW_OLD + '''}\n'''

class Tests(unittest.TestCase):
    def test_transform_composes_and_has_anchors(self):
        interpreter=v8.transform_interpreter(mock_v7())
        renderer=v8.transform_renderer(mock_renderer_original())
        self.assertIn('GOEMON_JP_RT64_RASTER_HANDOFF_V8',interpreter)
        self.assertIn('goemon_jp_rt64_register_robot_range',interpreter)
        self.assertIn('goemon_jp_rt64_lookup_robot_range',interpreter)
        self.assertIn('RASTER SKIP_PROJECTION',renderer)
        self.assertIn('RASTER BUILT',renderer)
        self.assertIn('DRAW_RECORDED',renderer)
        self.assertIn('SKIP_SCISSOR',renderer)
        self.assertEqual(renderer.count('goemon_jp_rt64_raster_log(i, "DRAW_RECORDED"'),1)
    def test_repeat_and_missing_anchor_rejected(self):
        inter=v8.transform_interpreter(mock_v7())
        with self.assertRaisesRegex(ValueError, 'already installed'):
            v8.transform_interpreter(inter)
        with self.assertRaisesRegex(ValueError, 'expected unique'):
            v8.transform_interpreter(mock_v7().replace(v8.BEGIN_OLD,'oops'))
        render=v8.transform_renderer(mock_renderer_original())
        with self.assertRaisesRegex(ValueError,'already installed'):
            v8.transform_renderer(render)
        with self.assertRaisesRegex(ValueError, 'expected unique'):
            v8.transform_renderer(mock_renderer_original()+v8.RENDER_INSTANCE_OLD)
    def test_fail_closed_plan(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); rt=base/'rt'; it=rt/v8.INTERPRETER; st=rt/v8.STATE; rr=rt/v8.RT64_RENDERER
            it.parent.mkdir(parents=True, exist_ok=True); st.parent.mkdir(parents=True, exist_ok=True); rr.parent.mkdir(parents=True, exist_ok=True)
            orig=mock_interpreter_original().encode(); so=mock_state_original().encode(); ro=mock_renderer_original().encode()
            it.with_name(it.name+'.pre-jp-robot-probe').write_bytes(orig)
            it.write_bytes(mock_v7().encode())
            st.with_name(st.name+v7.BACKUP_SUFFIX).write_bytes(so)
            st.write_bytes(v7.transform_state(so.decode()).encode())
            rr.write_bytes(ro)
            hash=v4.blob_hash
            with patch.object(v4,'validate_rom',lambda path:None), \
                 patch.object(v4,'ORIGINAL_BLOB_SHA1',hash(orig)), \
                 patch.object(v7,'STATE_ORIGINAL_GIT_BLOB',hash(so)), \
                 patch.object(v8,'RENDER_ORIGINAL_GIT_BLOB',hash(ro)):
                changes=v8.plan(rt,base/'rom'); self.assertEqual(len(changes),2)
                it.write_bytes(changes[0][2]);
                with self.assertRaisesRegex(ValueError,'not exact v7'):
                    v8.plan(rt,base/'rom')
                it.write_bytes(mock_v7().encode())
                rr.write_bytes(ro+b'//changed')
                with self.assertRaisesRegex(ValueError,'renderer differs'):
                    v8.plan(rt,base/'rom')
                rr.write_bytes(ro)
                rr.with_name(rr.name+v8.BACKUP_SUFFIX).write_bytes(b'old')
                with self.assertRaisesRegex(ValueError,'existing v8 backup'):
                    v8.plan(rt,base/'rom')
    def test_compiled_cpp_face_range_and_raster_tags(self):
        cpp='''#include <algorithm>\n#include <mutex>\n#include <cstdint>\n#include <cstdio>\n#include <cassert>\n#include <thread>\nnamespace RT64 {\nbool goemon_jp_rt64_probe_enabled(){return true;}\n''' + v8.REGISTRY_INSERT + '}\n' + v8.RENDER_DECLARE + r'''
}
int main() {
  using namespace RT64;
  goemon_jp_rt64_register_robot_range(117, 30, 54, 0x12F0, 1);
  goemon_jp_rt64_register_robot_range(117, 54, 84, 0x1420, 1);
  goemon_jp_rt64_register_robot_range(117, 54, 84, 0x1420, 1); // dedupe
  assert(goemonRobotFaceCount==2);
  uint32_t root=0, sample=0, overlap=0;
  // One packed GameCall spans two independently proven original lists.
  assert(goemon_jp_rt64_lookup_robot_range(117,42,6,0,&root,&sample,&overlap));
  assert(root==0x12F0 && overlap==4);
  assert(goemon_jp_rt64_lookup_robot_range(117,42,6,1,&root,&sample,&overlap));
  assert(root==0x1420 && overlap==2);
  assert(!goemon_jp_rt64_lookup_robot_range(117,42,6,2,&root,&sample,&overlap));
  assert(!goemon_jp_rt64_lookup_robot_range(118,42,6,0,&root,&sample,&overlap));
  assert(!goemon_jp_rt64_lookup_robot_range(117,42,0,0,&root,&sample,&overlap));
  goemonRobotRasterTagCount=1;
  goemonRobotRasterTags[0]={19,0x1420,1,2};
  goemon_jp_rt64_raster_log(19,"DRAW_RECORDED",6,false);
  goemon_jp_rt64_raster_log(19,"SKIP_SCISSOR",6,true);
  goemon_jp_rt64_raster_log(2,"SHOULD_NOT_LOG",6,true);
  std::thread t([&](){for(unsigned i=0;i<100;i++){ uint32_t a=0,b=0,c=0;
      assert(goemon_jp_rt64_lookup_robot_range(117,42,6,0,&a,&b,&c)); }});
  for(unsigned i=0;i<100;i++){ uint32_t a=0,b=0,c=0;
    assert(goemon_jp_rt64_lookup_robot_range(117,42,6,1,&a,&b,&c)); }
  t.join();
}
'''
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'test.cpp'; exe=Path(temp)/'test'; src.write_text(cpp)
            p=subprocess.run(['g++','-std=c++17','-pthread','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            q=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(q.returncode,0,q.stderr)
            self.assertIn('DRAW_RECORDED',q.stderr)
            self.assertIn('SKIP_SCISSOR',q.stderr)
            self.assertNotIn('SHOULD_NOT_LOG',q.stderr)
if __name__=='__main__':unittest.main()