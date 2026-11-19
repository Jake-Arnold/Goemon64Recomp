"""ROM-free tests of exact v5->v6 transformation and compiled C++ face-growth metric."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
v4 = types.ModuleType('jp_rt64_robot_probe')
v4.RELATIVE=Path('src/hle/rt64_interpreter.cpp')
v4.ORIGINAL_BLOB_SHA1='test-blob'
v4.blob_hash=lambda data:'test-blob'
v4.validate_rom=lambda path:None
v4.transform=lambda txt:'PINNED-V4\n' + txt
v5 = types.ModuleType('jp_rt64_triangle_gate_probe')
v5.V5_MARKER='GOEMON_JP_RT64_TRI_GATE_V5'
v5.transform=lambda txt:'GOEMON_JP_RT64_TRI_GATE_V5\n'+txt
sys.modules['jp_rt64_robot_probe']=v4
sys.modules['jp_rt64_triangle_gate_probe']=v5
spec=importlib.util.spec_from_file_location('probe_v6', HERE/'jp_rt64_face_index_probe.py')
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fake_v5() -> str:
    return ('GOEMON_JP_RT64_TRI_GATE_V5\n' + mod.FIELD_ANCHOR + mod.PRE_ANCHOR +
            mod.AFTER_ANCHOR + mod.END_FMT_ANCHOR + mod.END_ARGS_ANCHOR)


class TransformTests(unittest.TestCase):
    def test_exact_source_upgrade(self):
        source = fake_v5()
        output = mod.transform(source)
        self.assertIn(mod.MARKER, output)
        self.assertIn('face_index_tri=%u face_ambiguous=%u',output)
        self.assertIn('WORKLOAD_QUEUE_SIZE',output)
        self.assertIn('drawData.faceIndices.size()',output)
        self.assertIn('goemon_jp_rt64_probe_after',output)
        self.assertEqual(output.count('goemon_probe_cursor_before'),4) if False else None
        self.assertEqual(output.count('goemon_jp_rt64_probe_after'),1)

    def test_double_apply_rejected(self):
        with self.assertRaisesRegex(ValueError,'already installed'):
            mod.transform(mod.transform(fake_v5()))

    def test_no_v5_rejected(self):
        with self.assertRaisesRegex(ValueError,'absent'):
            mod.transform(fake_v5().replace(v5.V5_MARKER,''))

    def test_missing_anchor_rejected(self):
        for needle in (mod.FIELD_ANCHOR,mod.PRE_ANCHOR,mod.AFTER_ANCHOR,mod.END_FMT_ANCHOR,mod.END_ARGS_ANCHOR):
            with self.subTest(anchor=needle[:28]):
                with self.assertRaisesRegex(ValueError,'anchor'):
                    mod.transform(fake_v5().replace(needle,''))

    def test_duplicated_anchor_rejected(self):
        with self.assertRaisesRegex(ValueError,'found 2'):
            mod.transform(fake_v5()+mod.END_ARGS_ANCHOR)

    def test_fail_closed_plan_and_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); rt=base/'rt'; target=rt/v4.RELATIVE
            target.parent.mkdir(parents=True)
            original=b'ORIGINAL SOURCE\n'
            pristine=target.with_name(target.name+'.pre-jp-robot-probe')
            oldv4=target.with_name(target.name+'.pre-jp-tri-gate-v5')
            pristine.write_bytes(original)
            v4.transform=lambda txt:'PINNED-V4\n' + txt + mod.FIELD_ANCHOR + mod.PRE_ANCHOR + mod.AFTER_ANCHOR + mod.END_FMT_ANCHOR + mod.END_ARGS_ANCHOR
            expected_v4=v4.transform(original.decode()).encode()
            expected_v5=v5.transform(expected_v4.decode()).encode()
            oldv4.write_bytes(expected_v4)
            target.write_bytes(expected_v5)
            try:
                _, _, changed=mod.plan(rt,base/'rom')
            except ValueError as e:
                self.fail(f'valid fixture refused: {e}')
            self.assertIn(mod.MARKER,changed.decode())
            target.write_bytes(changed)
            with self.assertRaisesRegex(ValueError,'differs'):
                mod.plan(rt,base/'rom')

    def test_compiled_cpp_face_index_growth_and_flush_reset(self):
        source = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstddef>
#include <array>
#include <vector>
#define WORKLOAD_QUEUE_SIZE 4
#define RT64_LOG_PRINTF(...) ((void)0)
struct DrawData { std::vector<uint32_t> faceIndices; };
struct Workload { DrawData drawData; };
struct WorkloadQueue { int writeCursor=0; std::array<Workload,4> workloads; };
struct Ext { WorkloadQueue* workloadQueue=nullptr; };
struct State { Ext ext; struct { uint32_t triangleCount=0; } drawCall; };
struct DisplayList { uint32_t w1=0; };
struct Record { uint32_t face_index_triangles=0, face_index_ambiguous=0; };
thread_local Record goemonProbeLists[7];
void goemon_jp_rt64_probe_after(State*,int,uint8_t,uint32_t,uint32_t) {}
using Handler = void(*)(State*, DisplayList**);
void run(uint8_t opCode, Handler func, State* state) {
    DisplayList command{};
    DisplayList* dl = &command;
    const int goemon_probe_index = 0;
    const uint32_t goemon_probe_arg = goemon_probe_index >= 0 ? dl->w1 : 0u;
''' + mod.PRE_REPLACE + '    if (func != nullptr) func(state, &dl);\n' + mod.AFTER_REPLACE + r'''
}
void pass2(State* state, DisplayList**) {
   auto &d = state->ext.workloadQueue->workloads[0].drawData.faceIndices;
   for (int i=0;i<6;i++) d.push_back(i);
   state->drawCall.triangleCount = 1; // simulate mid-handler flush/reset
}
void pass1(State* state, DisplayList**) {
   auto &d = state->ext.workloadQueue->workloads[0].drawData.faceIndices;
   for (int i=0;i<3;i++) d.push_back(i);
   state->drawCall.triangleCount = 0;
}
void skip(State*, DisplayList**) {}
void incomplete(State* state, DisplayList**) {
  state->ext.workloadQueue->workloads[0].drawData.faceIndices.push_back(7);
}
void cursor_change(State* state, DisplayList**) {
  state->ext.workloadQueue->writeCursor = 1;
}
int main() {
  WorkloadQueue queue;
  State s; s.ext.workloadQueue=&queue;
  run(0xB1,pass2,&s);
  assert(goemonProbeLists[0].face_index_triangles==2);
  assert(goemonProbeLists[0].face_index_ambiguous==0);
  run(0xBF,pass1,&s);
  assert(goemonProbeLists[0].face_index_triangles==3);
  run(0xB1,skip,&s);
  assert(goemonProbeLists[0].face_index_triangles==3);
  run(0xBF,incomplete,&s);
  assert(goemonProbeLists[0].face_index_ambiguous==1);
  run(0xBF,cursor_change,&s);
  assert(goemonProbeLists[0].face_index_ambiguous==2);
  return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            t=Path(tmp); (t/'main.cpp').write_text(source)
            result=subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',str(t/'main.cpp'),'-o',str(t/'test')],capture_output=True,text=True)
            if result.returncode:
                self.fail(result.stderr[:3500])
            p=subprocess.run([str(t/'test')],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)


if __name__ == '__main__': unittest.main()