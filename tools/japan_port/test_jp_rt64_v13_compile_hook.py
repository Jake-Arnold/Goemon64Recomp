import subprocess, tempfile, unittest
from pathlib import Path
from test_jp_rt64_tmem_high_address_v13 import v13

class CppCompile(unittest.TestCase):
    def test_exact_injected_sample_compiles_and_runs(self):
        fragment=v13.NEW_SAMPLE
        # Test the actual inserted hook as a compiling C++ statement on an
        # emulated 8 MiB readable RDRAM array with the two candidate offsets.
        cpp='''#include <cstddef>\n#include <cstdint>\n#include <vector>\n#include <cassert>\nstruct Record { uint32_t srcNz64=0, candidateNz64=0; };\nint main() {\n  std::vector<uint8_t> ram(8u*1024u*1024u,0);\n  const uint8_t* RDRAM=ram.data();\n  for(unsigned i=0;i<64;i++){ram[0x003C76E0+i]=(i%3==0)?0:0xA5;}\n  Record rec{};\n  uint64_t source=0x0078B6E0ull;\n'''+ '{\n' + fragment + '\n}' + '''\n  assert(rec.srcNz64==0);\n  assert(rec.candidateNz64==42);\n  source=0x007953D0ull;\n  for(unsigned i=0;i<64;i++)ram[0x003D13D0+i]=0x42;\n'''+ '{\n' + fragment + '\n}' + '''\n  assert(rec.srcNz64==0 && rec.candidateNz64==64);\n  source=8ull*1024ull*1024ull + 10;\n'''+ '{\n' + fragment + '\n}' + '''\n  assert(rec.srcNz64==0xFFFFFFFFu && rec.candidateNz64==0xFFFFFFFFu);\n}\n'''
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'t.cpp').write_text(cpp)
            subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','t.cpp','-o','test'],cwd=p,check=True,capture_output=True,text=True)
            subprocess.run([str(p/'test')],cwd=p,check=True,capture_output=True,text=True)

if __name__=='__main__':unittest.main()