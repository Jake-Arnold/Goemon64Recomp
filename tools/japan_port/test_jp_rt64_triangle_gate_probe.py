"""ROM-free fixture tests of RT64 v4→v5 cull-gate instrumentation."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import jp_rt64_robot_probe as v4
import jp_rt64_triangle_gate_probe as v5


class GateTest(unittest.TestCase):
    def test_v4_transform_roundtrip(self):
        source='#include "rt64_interpreter.h"\n'+v4.INCLUDES+v4.NAMESPACE+'void Interpreter::processDisplayLists() {\n'+v4.CMD_ANCHOR+v4.CALL_ANCHOR+'}\n}\n'
        changed=v5.transform(v4.transform(source))
        self.assertIn('GOEMON_JP_RT64_TRI_GATE_V5',changed)
        self.assertIn('gate_pass=%u gate_skip=%u',changed)
        with self.assertRaisesRegex(ValueError,'already installed'):
            v5.transform(changed)

    def test_reject_unknown_source_and_drift(self):
        with self.assertRaisesRegex(ValueError,'v4 RT64 robot probe not installed'):
            v5.transform('other source')
        a=v4.HELPER
        with self.assertRaisesRegex(ValueError,'pre-dispatch tri gate'):
            v5.transform(a.replace(v5.BEFORE_OLD,''))
        with self.assertRaisesRegex(ValueError,'END log'):
            v5.transform(a.replace(v5.END_OLD,''))

    def test_compiled_cpp_cull_and_pass(self):
        fixture=r'''
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <vector>
struct DisplayList { std::uint32_t w0, w1; };
namespace RT64 {
struct FakeRSP {
 std::array<uint32_t,16> segments{};
 std::array<uint32_t,4> geometryModeStack{};
 uint32_t geometryModeStackSize=1;
 uint32_t cullBothMask=0x3000;
 uint32_t fromSegmented(uint32_t a) {return segments[(a>>24)&15]+(a&0xFFFFFF);}
};
struct FakeRDP { struct Texture {uint32_t address=0;} texture; };
struct State {
 uint8_t* RDRAM;
 std::unique_ptr<FakeRSP> rsp=std::make_unique<FakeRSP>();
 std::unique_ptr<FakeRDP> rdp=std::make_unique<FakeRDP>();
 struct {bool extendRDRAM=false;} extended;
 struct {uint32_t triangleCount=0;} drawCall;
};
'''
        app=r'''
void go(bool cull, bool reset) {
 std::vector<uint8_t> buf(0x800000u,0);
 State s{};s.RDRAM=buf.data();s.rsp->segments[8]=0x003EAE40;
 s.rsp->geometryModeStack[0]= cull ? 0x3000u : 0u;
 for(unsigned j=0;j<22;++j) {
   DisplayList* dl=reinterpret_cast<DisplayList*>(buf.data()+0x003EAE40+0x1640+j*8);
   const uint8_t op=j==21?0xB8:j==10?0xB1:0xE7;
   dl->w0=uint32_t(op)<<24;dl->w1=0;
   const int x=goemon_jp_rt64_probe_before(&s,dl,op,true,6);
   if(x<0) continue;
   const uint32_t before=s.drawCall.triangleCount;
   if(op==0xB1 && !cull) s.drawCall.triangleCount+=2;
   if(op==0xB1 && reset) s.drawCall.triangleCount=0;
   goemon_jp_rt64_probe_after(&s,x,op,dl->w1,before);
 }
}
}
int main(int argc,char** argv) {
 RT64::go(argc>1 && argv[1][0]=='c', argc>1 && argv[1][0]=='r');
}
'''
        replaced=v5.transform(v4.HELPER)
        with tempfile.TemporaryDirectory() as temp:
            cpp=Path(temp)/'probe.cpp';cpp.write_text(fixture+replaced+app)
            exe=Path(temp)/'probe'
            subprocess.run(['g++','-std=c++20','-O1','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)],check=True,capture_output=True)
            for arg,pass_count,skip_count in [('c',0,2),('p',2,0),('r',2,0)]:
                r=subprocess.run([str(exe),arg],env={**os.environ,'GOEMON_JP_RT64_TRACE':'1'},capture_output=True,text=True,check=True)
                self.assertIn(f'gate_pass={pass_count} gate_skip={skip_count}',r.stderr)
                self.assertIn('tri_encoded=2 expected_tri=2',r.stderr)
                self.assertEqual('CULL_GATE' in r.stderr,skip_count>0)
                if arg == 'r':
                    self.assertIn('tri_queued=0 tri_ambiguous=0',r.stderr)
            off=subprocess.run([str(exe),'c'],env={**os.environ,'GOEMON_JP_RT64_TRACE':'0'},capture_output=True,text=True,check=True)
            self.assertNotIn('[JP-RT64]',off.stderr)

if __name__=='__main__':unittest.main()