"""ROM-free source transformation and host-C++ probe tests. No game files are written."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import jp_rt64_robot_probe as jp


class ProbeTests(unittest.TestCase):
    @staticmethod
    def sample_source():
        return ('#include "rt64_interpreter.h"\n'+jp.INCLUDES+'\n'
                +jp.NAMESPACE+
                'void Interpreter::processDisplayLists(uint32_t addr, DisplayList *dlStart) {\n'
                '    DisplayList* dl = dlStart; uint8_t opCode=0; GBIFunction func;\n'
                '    while (dl != nullptr) {\n'
                '        if (false) {} else {\n'
                +jp.CMD_ANCHOR
                +jp.CALL_ANCHOR+
                '        }\n'
                '    }\n'
                '}\n}\n')

    def test_transform_unique_and_idempotence(self):
        changed=jp.transform(self.sample_source())
        self.assertIn('GOEMON_JP_RT64_TRACE',changed)
        self.assertIn('goemon_jp_rt64_probe_after',changed)
        self.assertEqual(changed.count('goemon_jp_rt64_probe_before(state'),1)
        with self.assertRaisesRegex(ValueError,'already installed'):
            jp.transform(changed)
        for anchor in (jp.INCLUDES,jp.NAMESPACE,jp.CMD_ANCHOR,jp.CALL_ANCHOR):
            with self.subTest(anchor=anchor[:40]):
                with self.assertRaisesRegex(ValueError,'anchor'):
                    jp.transform(self.sample_source().replace(anchor,'',1))

    def test_git_blob_sha_hash(self):
        sample=b'hello\n'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'file'
            p.write_bytes(sample)
            res=subprocess.run(['git','hash-object',str(p)],capture_output=True,text=True,check=True)
            self.assertEqual(jp.blob_hash(sample),res.stdout.strip())

    def test_fail_closed_on_different_rt64_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'rt64.cpp';source.write_text(self.sample_source())
            rom=root/'japan.z64';rom.write_bytes(b'wrong')
            with self.assertRaisesRegex(ValueError,'32 MiB'):
                jp.plan(source,rom,root/'back')
            rom.write_bytes(b'\0'*0x2000000)
            with self.assertRaisesRegex(ValueError,'SHA-1 mismatch'):
                jp.plan(source,rom,root/'back')
            # Authenticating exact 32-MiB Japanese ROM is mandatory.

    def test_original_list_inventory(self):
        for i,(start,end,count,tris) in enumerate(((0x12F0,0x13F0,32,8),
                (0x1420,0x1520,32,8),(0x1538,0x1628,30,10),
                (0x1640,0x16F0,22,2),(0x1708,0x17F8,30,10),
                (0x1810,0x18C0,22,2),(0x1938,0x1C38,96,64))):
            self.assertGreater(end,start)
            self.assertEqual(count,(end-start)//8)
            self.assertEqual(jp.HELPER.count(f'0x{start:X}u'),1)
        self.assertIn('kGoemonMaxSamples = 2u',jp.HELPER)
        self.assertIn('goemonProbeCompleted[i] >= kGoemonMaxSamples',jp.HELPER)

    def test_synthetic_host_cpp_runtime(self):
        preamble=r'''
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
    uint32_t fromSegmented(uint32_t a) {
       return segments[(a >> 24) & 15] + (a & 0xFFFFFF);
    }
};
struct FakeRDP { struct Texture { uint32_t address = 0; } texture; };
struct State {
  uint8_t* RDRAM;
  std::unique_ptr<FakeRSP> rsp = std::make_unique<FakeRSP>();
  std::unique_ptr<FakeRDP> rdp = std::make_unique<FakeRDP>();
  struct { bool extendRDRAM = false; } extended;
  struct { uint32_t triangleCount = 0; } drawCall;
};
'''
        app=r'''
void run_probe(int loops) {
    std::vector<uint8_t> rdram(0x800000u, 0u);
    State s{};
    s.RDRAM = rdram.data();
    s.rsp->segments[8] = 0x003EAE40u;
    s.rsp->segments[12] = 0x787CA950u;
    for (int sample=0;sample<loops;++sample) {
        for (unsigned j=0;j<96u;++j) {
            DisplayList* dl=reinterpret_cast<DisplayList*>(
                   rdram.data()+0x003EAE40u+0x1938u+j*8u);
            uint8_t op=j==95 ? 0xB8u : j==1 ? 0xFDu : j>=3&&j<35 ? 0xB1u : 0xE7u;
            dl->w0=uint32_t(op)<<24;
            dl->w1=op==0xFD ? 0x0C000000u:0;
            const int index=goemon_jp_rt64_probe_before(&s,dl,op,true,2);
            if (index>=0) {
                const uint32_t before=s.drawCall.triangleCount;
                if(op==0xFD) s.rdp->texture.address=0x007CA950u;
                if(op==0xB1) s.drawCall.triangleCount+=2;
                goemon_jp_rt64_probe_after(&s,index,op,dl->w1,before);
            }
        }
    }
}
}
int main() { RT64::run_probe(4); }
'''
        with tempfile.TemporaryDirectory() as td:
            cpp=Path(td)/'probe.cpp'
            cpp.write_text(preamble+jp.HELPER+app)
            exe=Path(td)/'probe'
            subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-O1',
                            str(cpp),'-o',str(exe)],check=True,capture_output=True)
            p=subprocess.run([str(exe)],env={**os.environ,'GOEMON_JP_RT64_TRACE':'1'},
                            capture_output=True,text=True,check=True)
            output=p.stderr
            self.assertEqual(output.count('[JP-RT64] BEGIN root=0x1938'),2)
            self.assertEqual(output.count('[JP-RT64] TEX root=0x1938'),2)
            self.assertEqual(output.count('[JP-RT64] END root=0x1938'),2)
            self.assertIn('resolved=0x007CA950 rdp=0x007CA950 match=1',output)
            self.assertIn('commands=96 expected_commands=96',output)
            self.assertIn('tri_encoded=64 expected_tri=64 tri_queued=64 tri_ambiguous=0',output)
            self.assertNotIn('tex_mismatch=1',output)
            p=subprocess.run([str(exe)],env={**os.environ,'GOEMON_JP_RT64_TRACE':'0'},
                            capture_output=True,text=True,check=True)
            self.assertNotIn('[JP-RT64]',p.stderr)


if __name__=='__main__':
    unittest.main()