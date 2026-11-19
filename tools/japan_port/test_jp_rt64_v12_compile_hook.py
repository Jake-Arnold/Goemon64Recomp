"""Compile and execute the exact injected v12 C++ portions with a synthetic RDP."""
import subprocess, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,str(Path(__file__).parent/'fixture'))
import jp_rt64_tmem_replay_v12 as p

class CompileV12(unittest.TestCase):
    def test_code_compiles_and_runs(self):
        # Extract only new code: prefix lambda, RDP load metadata, load aftermath,
        # and trace body embedded within the existing uploadTile lambda.
        metadata=p.LOAD_NEW.replace(p.LOAD_OLD, '') if False else p.LOAD_NEW[:p.LOAD_NEW.index('            // For emulating')]
        # New metadata is after the unmodified loadOp statement.
        load_prefix=metadata
        load_after=p.AFTER_LOAD_NEW[p.AFTER_LOAD_NEW.index('            if (jpV12Trace && jpV12Seen > 0)'):p.AFTER_LOAD_NEW.index('        };\n\n        auto uploadTile')]
        target=p.UPLOAD_NEW[p.UPLOAD_NEW.index('                    constexpr uint64_t JPBad'):p.UPLOAD_NEW.index('                }\n            }\n            else if (callTile.reinterpretTile)')].rsplit('                }\n',1)[0] + '                }\n'
        cpp=r'''#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
struct LoadTile {unsigned fmt=0,siz=2,line=8,tmem=0,uls=0,ult=0,lrs=124,lrt=252;};
struct LoadTexture {unsigned address=0,fmt=0,siz=2,width=32;};
struct LoadOperation {enum class Type{Tile,Block,TLUT};Type type=Type::Tile;LoadTile tile;LoadTexture texture;};
struct DrawCall {unsigned callIndex=140;};
struct DrawCallTile {bool valid=true,tileCopyUsed=false,rawTMEM=false;uint64_t tmemHashOrID=0x8042c12b60ec2b4eull;unsigned sampleWidth=32,sampleHeight=64;LoadTile loadTile;unsigned tlut=0;};
struct DrawData {std::vector<LoadOperation> loadOperations;std::vector<DrawCallTile> callTiles;};
struct Workload {DrawData drawData;uint64_t submissionFrame=24;};
struct FramebufferPair {};
struct RDP {uint64_t TMEM[512]{};void loadTileOperation(const LoadTile&,const LoadTexture&,bool){}void loadBlockOperation(const LoadTile&,const LoadTexture&,bool){}void loadTLUTOperation(const LoadTile&,const LoadTexture&,bool){};};
struct State {RDP* rdp;uint8_t* RDRAM;void fullSyncFramebufferPairTiles(Workload&,FramebufferPair&,uint32_t&,uint32_t&);};
#define RDP_TMEM_BYTES 4096
'''
        cpp+='void State::fullSyncFramebufferPairTiles(Workload &workload, FramebufferPair &fbPair, uint32_t &loadOpCursor, uint32_t &rdpTileCursor) {\n'
        cpp+=p.FUNCTION_NEW.split('    void State::fullSyncFramebufferPairTiles(Workload &workload, FramebufferPair &fbPair, uint32_t &loadOpCursor, uint32_t &rdpTileCursor) {\n',1)[1]
        cpp+=load_prefix
        cpp+='            switch(loadOp.type){ case LoadOperation::Type::Tile: rdp->loadTileOperation(loadOp.tile,loadOp.texture,false); break; case LoadOperation::Type::Block: rdp->loadBlockOperation(loadOp.tile,loadOp.texture,false);break; case LoadOperation::Type::TLUT:rdp->loadTLUTOperation(loadOp.tile,loadOp.texture,false);break; }\n'
        cpp+=load_after+'        };\n'
        cpp+='        auto uploadTile = [&](uint32_t rdpTileIndex,const DrawCall &drawCall) {\n'
        cpp+='        const auto &callTile=workload.drawData.callTiles[rdpTileIndex];\n'
        cpp+=target
        cpp+='        };\n'
        cpp+='        for(uint32_t i=0;i<workload.drawData.loadOperations.size();i++)loadOperation(i);\n'
        cpp+='        if(!workload.drawData.callTiles.empty())uploadTile(0,DrawCall{});\n'
        cpp+='}\nint main(){ RDP rdp;std::vector<uint8_t> rdram(4*1024*1024,0); Workload w; w.drawData.loadOperations.emplace_back();w.drawData.callTiles.emplace_back();FramebufferPair fb;uint32_t a=0,b=0;State st{&rdp,rdram.data()};st.fullSyncFramebufferPairTiles(w,fb,a,b);return 0;}\n'
        with tempfile.TemporaryDirectory() as d:
            fp=Path(d)/'probe.cpp'
            ex=Path(d)/'probe'
            fp.write_text(cpp)
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-parameter',str(fp),'-o',str(ex)],check=True,capture_output=True,text=True)
            result=subprocess.run([str(ex)],env={'GOEMON_JP_RT64_TEX_TRACE':'1'},check=True,capture_output=True,text=True)
            self.assertIn('TEX_REPLAY_TARGET',result.stderr)
            self.assertIn('TEX_REPLAY_LOAD',result.stderr)
            self.assertIn('source_nonzero64=0',result.stderr)

if __name__=='__main__':unittest.main()