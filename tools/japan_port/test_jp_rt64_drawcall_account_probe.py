"""ROM-free v7 source-gate and compiled drawcall conservation tests."""
from __future__ import annotations
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import jp_rt64_robot_probe as v4
import jp_rt64_triangle_gate_probe as v5
import jp_rt64_face_index_probe as v6
import jp_rt64_drawcall_account_probe as v7


def mock_original():
    return '// synthetic pinned RT64\n' + v4.INCLUDES + v4.NAMESPACE + v4.CMD_ANCHOR + v4.CALL_ANCHOR


def mock_v6():
    return v6.transform(v5.transform(v4.transform(mock_original())))


def mock_state():
    return '// synthetic pinned State\n' + v7.STATE_NS_OLD + 'struct State { };\n' + v7.STATE_FLUSH_OLD


class ProbeTests(unittest.TestCase):
    def test_transform_composes_v4_v5_v6_v7(self):
        initial=mock_v6()
        after=v7.transform_interpreter(initial)
        self.assertIn('goemon_jp_rt64_note_robot_flush',after)
        self.assertIn('conserved_tri=',after)
        self.assertIn('face_index_tri=',after)
        self.assertEqual(after.count('goemonV7ActiveList = int(i)'),1)
        self.assertEqual(after.count('[JP-RT64] DRAWCALL'),1)
        self.assertIn('goemon_jp_rt64_note_robot_flush(this, gameCall.callDesc.triangleCount',v7.transform_state(mock_state()))

    def test_repeat_and_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'already patched'):
            v7.transform_interpreter(v7.transform_interpreter(mock_v6()))
        with self.assertRaisesRegex(ValueError,'required'):
            v7.transform_interpreter(mock_v6().replace(v6.MARKER,'BAD'))
        with self.assertRaisesRegex(ValueError,'unique anchor'):
            v7.transform_interpreter(mock_v6().replace(v7.BEGIN_OLD,''))
        with self.assertRaisesRegex(ValueError,'unique anchor'):
            v7.transform_state(mock_state()+v7.STATE_FLUSH_OLD)

    def test_exact_pinned_files_and_backups(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); rt=base/'rt'; i=rt/v4.RELATIVE; s=rt/v7.STATE
            i.parent.mkdir(parents=True)
            source=mock_original().encode()
            prev4=v4.transform(source.decode()).encode()
            prev5=v5.transform(prev4.decode()).encode()
            prev6=v6.transform(prev5.decode()).encode()
            i.with_name(i.name+'.pre-jp-robot-probe').write_bytes(source)
            i.with_name(i.name+'.pre-jp-tri-gate-v5').write_bytes(prev4)
            i.with_name(i.name+'.pre-jp-face-index-v6').write_bytes(prev5)
            i.write_bytes(prev6)
            s.write_bytes(mock_state().encode())
            genuine_hash = v4.blob_hash
            with patch.object(v4,'validate_rom',lambda _:None), \
                 patch.object(v4,'ORIGINAL_BLOB_SHA1',genuine_hash(source)), \
                 patch.object(v7,'STATE_ORIGINAL_GIT_BLOB',genuine_hash(s.read_bytes())):
                changes=v7.plan(rt,base/'rom')
                self.assertEqual(len(changes),2)
                self.assertEqual([f.name for f,_,_ in changes],[i.name,s.name])
                i.write_bytes(changes[0][2])
                with self.assertRaisesRegex(ValueError,'installed v6'):
                    v7.plan(rt,base/'rom')
                i.write_bytes(prev6)
                s.write_bytes(s.read_bytes()+b'//drift\n')
                with self.assertRaisesRegex(ValueError,'State::flush source differs'):
                    v7.plan(rt,base/'rom')
                s.write_bytes(mock_state().encode())
                s.with_name(s.name+v7.BACKUP_SUFFIX).write_bytes(b'saved')
                with self.assertRaisesRegex(ValueError,'backup exists'):
                    v7.plan(rt,base/'rom')

    def test_compiled_cpp_flush_accounting(self):
        source=r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cassert>
#include <array>
#define WORKLOAD_QUEUE_SIZE 4
namespace RT64 {
struct DrawCall { uint32_t triangleCount=0; };
struct WorkloadQueue { int writeCursor=0; };
struct Ext { WorkloadQueue* workloadQueue=nullptr; };
struct State { DrawCall drawCall; Ext ext; };
struct Record {
 bool active=false;
 uint32_t face_index_triangles=0, face_index_ambiguous=0;
 uint32_t flush_count=0;
 uint64_t flush_triangles=0;
 uint32_t pending_start=0;
 int cursor_start=-1;
 uint32_t flush_ambiguous=0;
};
struct List { unsigned first; };
constexpr List kGoemonRobotLists[7] = {{0x12F0},{0x1420},{0x1538},{0x1640},{0x1708},{0x1810},{0x1938}};
thread_local Record goemonProbeLists[7];
thread_local unsigned goemonProbeCompleted[7] = {};
thread_local int goemonV7ActiveList=-1;
thread_local const State* goemonV7ActiveState=nullptr;
bool goemon_jp_rt64_probe_enabled() { return true; }
''' + v7.HOOK_CODE + r'''
void begin(State* state, unsigned i) {
  auto& record=goemonProbeLists[i];
''' + v7.BEGIN_NEW + r'''
}
void end(State* state, int index) {
 auto& record=goemonProbeLists[index];
 const unsigned root=kGoemonRobotLists[index].first;
''' + v7.END_NEW + r'''
}
void simulate(State* state, uint32_t triangles) {
 // An actual State::flush records a real FB game call and resets its counter.
 goemon_jp_rt64_note_robot_flush(state, triangles, state->ext.workloadQueue->writeCursor);
 state->drawCall.triangleCount=0;
}
}
int main() {
  RT64::WorkloadQueue queue;
  RT64::State s; s.ext.workloadQueue=&queue;
  s.drawCall.triangleCount=3; // carry-in from another list
  RT64::begin(&s,0);
  auto &rec=RT64::goemonProbeLists[0];
  rec.face_index_triangles=2;
  s.drawCall.triangleCount=4; // carry-in 3 + first new triangle
  RT64::simulate(&s,4);
  s.drawCall.triangleCount=1; // second new triangle queued, not yet flushed
  assert(rec.flush_count==1 && rec.flush_triangles==4);
  assert(rec.pending_start==3);
  assert(int64_t(rec.flush_triangles)+s.drawCall.triangleCount-rec.pending_start==2);
  RT64::end(&s,0);
  assert(RT64::goemonV7ActiveList==-1);
  assert(RT64::goemonProbeCompleted[0]==1);
  RT64::begin(&s,1);
  auto &r=RT64::goemonProbeLists[1];
  r.face_index_triangles=2;
  s.drawCall.triangleCount=3; // no flush, 2 new triangles pending
  RT64::end(&s,1);
  assert(r.flush_count==0);
  RT64::begin(&s,2);
  auto &q=RT64::goemonProbeLists[2];
  q.face_index_triangles=1;
  queue.writeCursor=1;
  RT64::goemon_jp_rt64_note_robot_flush(&s,3,queue.writeCursor);
  assert(q.flush_ambiguous==1);
  RT64::end(&s,2);
}
'''
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/'test.cpp'; exe=Path(temp)/'test'
            src.write_text(source)
            proc=subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],text=True,capture_output=True)
            self.assertEqual(proc.returncode,0,proc.stderr)
            result=subprocess.run([str(exe)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('match=1',result.stderr)
            self.assertIn('match=0',result.stderr)
            self.assertIn('conserved_tri=2',result.stderr)

if __name__=='__main__': unittest.main()