#!/usr/bin/env python3
"""Compile the injected v10 source snippets against synthetic field shapes."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).parent/'fixture'))
sys.path.insert(0,str(Path(__file__).parent))
import jp_rt64_texture_origin_probe as p

PREFIX = r'''#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <vector>
#include <string>
#include <unordered_map>
namespace RT64 {
struct V2 {float x=32,y=64;};
struct V3 {float x=32,y=64,z=1;};
struct LoadTile {unsigned fmt=0,siz=2,tmem=0,line=8,palette=0;};
struct CallTile {uint16_t sampleWidth=32,sampleHeight=64;uint64_t tmemHashOrID=33;LoadTile loadTile;unsigned tlut=0;bool rawTMEM=false;};
struct GpuTile {V2 tcScale;V3 textureDimensions;};
struct TextureCache {bool useTexture(uint64_t,unsigned long long,unsigned &idx,V2&,V3&,bool&,bool&,bool&){idx=89;return true;}};
struct TextureUpload {uint64_t hash=33,creationFrame=20;int width=32,height=64;uint32_t tlut=0;LoadTile loadTile;std::vector<uint8_t> bytesTMEM={0,1};bool decodeTMEM=true;};
struct Texture {unsigned width=32,height=64;bool decodeTMEM=true;uint64_t creationFrame=20;};
struct TextureMap {std::unordered_map<uint64_t,uint32_t> hashMap;void add(uint64_t h,uint64_t,Texture *){hashMap[h]=89;}};
struct Addition {uint64_t hash=33;Texture *texture;};
struct NativeTex {void setName(const std::string&){};};
'''

class CppHooks(unittest.TestCase):
    def test_cpp_hooks_syntax(self):
        # The two production sources have independent anonymous namespaces.
        # Prefix the cache fixture helper name to avoid sharing a TU here.
        cache_helper=p.CACHE_HELPER.replace('goemonJPV10TexTraceOn','goemonJPV10CacheTraceOn')
        q=p.QUEUE_NEW.replace('goemonJPV10TexTraceOn','goemonJPV10CacheTraceOn')
        c=p.CREATE_NEW.replace('goemonJPV10TexTraceOn','goemonJPV10CacheTraceOn')
        add=p.ADD_NEW.replace('goemonJPV10TexTraceOn','goemonJPV10CacheTraceOn')
        src=PREFIX+p.RENDER_HELPER+cache_helper+r'''
void bind(){
 TextureCache tc; TextureCache* textureCache=&tc; CallTile callTile; GpuTile gpuTile;
 uint64_t submissionFrame=20;unsigned textureIndex=0;
 bool textureReplaced=false,hasMipmaps=false,shiftedByHalf=false;
'''+p.BIND_NEW+r'''
}
void upload(){
 TextureUpload newUpload;bool decodeTMEM=true;int width=32,height=64;
 uint64_t creationFrame=20,hash=33;LoadTile loadTile;unsigned tlut=0;
'''+q+r'''
}
void create(){
 NativeTex tex;struct Dest {NativeTex* texture;};Dest obj{&tex};Dest* dstTexture=&obj;
 TextureUpload upload;static uint32_t TextureGlobalCounter=112003;
'''+c+r'''
}
void add(){TextureMap textureMap;Texture t;Addition addition{33,&t};
'''+add+r'''
}
}
int main(){RT64::bind();RT64::upload();RT64::create();RT64::add();}
'''
        with tempfile.TemporaryDirectory() as root:
            f=Path(root)/'v10.cpp';f.write_text(src)
            r=subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-fsyntax-only',str(f)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()