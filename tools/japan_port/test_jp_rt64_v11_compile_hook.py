#!/usr/bin/env python3
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/"fixture"))

import jp_rt64_robot_texture_link_v11 as p

class CompileHookTest(unittest.TestCase):
    def test_exact_robot_trace_hook_compiles(self):
        payload=p.ROBOT_INSERT.split('                    // GOEMON_JP_RT64_ROBOT_TEXTURE_V11:',1)[1]
        payload='                    // GOEMON_JP_RT64_ROBOT_TEXTURE_V11:'+payload.split('                    if (goemonRobotRasterTagCount < 256u) {',1)[0]
        code='''#include <atomic>
#include <algorithm>
#include <cstdio>
#include <cstddef>
#include <cstdint>
#include <vector>
struct LoadTile { unsigned fmt=0,siz=0,tmem=0,line=0,palette=0; };
struct DrawCallTile {
 bool valid=true,tileCopyUsed=false,rawTMEM=false;
 unsigned sampleWidth=32,sampleHeight=64,tlut=0;
 unsigned long long tmemHashOrID=0x123;
 LoadTile loadTile;
};
struct CallDesc {
 uint32_t tileIndex=0,tileCount=1,callIndex=145,triangleCount=18;
 unsigned textureOn=1,textureTile=0;
};
struct Call{CallDesc callDesc;};
struct DrawData { std::vector<DrawCallTile> callTiles{{}}; };
struct Workload { uint64_t submissionFrame=893; };
struct P{Workload* curWorkload;};
struct TraceHost{
std::atomic<unsigned> goemonJPV11RobotCalls{0};
static bool goemonJPV10TexTraceOn(){return true;}
void record(){
 Workload workload; P p{&workload};
 DrawData drawData; Call call;
 unsigned root=0x1938, sample=1,overlap=18;
''' +payload + '''
}
};
int main(){TraceHost h;h.record();return 0;}
'''
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'hook.cpp';f.write_text(code)
            r=subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-pedantic',str(f),'-o',str(Path(d)/'hook')],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            out=subprocess.run([str(Path(d)/'hook')],capture_output=True,text=True,check=True)
            self.assertIn('TEX_ROBOT_TILE',out.stderr)
            self.assertIn('root=0x1938',out.stderr)
            self.assertIn('requested=32x64',out.stderr)

if __name__=='__main__':unittest.main()