#!/usr/bin/env python3
import sys
from pathlib import Path
import unittest
import tempfile
import subprocess
sys.path.insert(0,str(Path(__file__).parent/'fixture'))
sys.path.insert(0,str(Path(__file__).parent))
import jp_rt64_texture_origin_probe as p

class SourceTests(unittest.TestCase):
    def renderer_fixture(self):
        return p.RENDER_INCLUDE+p.NAMESPACE+p.v9.MARKER+'\n'+p.BIND_OLD
    def cache_fixture(self):
        return p.CACHE_INCLUDE+p.NAMESPACE+p.QUEUE_OLD+p.CREATE_OLD+p.ADD_OLD
    def test_renderer_transform(self):
        s=p.transform_renderer(self.renderer_fixture())
        self.assertIn(p.MARKER,s)
        self.assertIn('TEX_BIND',s)
        self.assertIn('GOEMON_JP_RT64_TEX_TRACE',s)
        self.assertIn('cache_index=%u hit=%u',s)
    def test_cache_transform(self):
        s=p.transform_cache(self.cache_fixture())
        for x in ('TEX_QUEUE','TEX_CREATE','TEX_ADD','fingerprint=','nonzero=','serial=%u'):
            self.assertIn(x,s)
        self.assertIn('decodeTMEM',s)
    def test_reapplication_fails(self):
        with self.assertRaisesRegex(ValueError,'already installed'):
            p.transform_renderer(p.transform_renderer(self.renderer_fixture()))
        with self.assertRaisesRegex(ValueError,'already installed'):
            p.transform_cache(p.transform_cache(self.cache_fixture()))
    def test_drift_fails(self):
        for inp,fun in [(self.renderer_fixture().replace(p.BIND_OLD,'no matching call\n'),p.transform_renderer),
                        (self.cache_fixture().replace(p.CREATE_OLD,'changed create\n'),p.transform_cache)]:
            with self.assertRaisesRegex(ValueError,'pinned anchor'):
                fun(inp)
    def test_git_blob(self):
        self.assertEqual(p.git_blob_sha(b'hello\n'),'ce013625030ba8dba906f756967f9e9ca394464a')
    def test_zero_bytes_no_unsolicited_writes(self):
        with tempfile.TemporaryDirectory() as root:
            rt64=Path(root); rom=rt64/'rom';rom.write_bytes(b'bad')
            with self.assertRaises(Exception):p.plan(rt64,rom)
            self.assertEqual(sorted(x.name for x in rt64.iterdir()),['rom'])
    def test_compiled_hook_helpers(self):
        # Verify the exact helper functions and their mutex-free atomic gate compile.
        src='''#include <atomic>\n#include <cstdio>\n#include <cstdlib>\n#include <cstring>\nnamespace RT64 {\n'''+p.RENDER_HELPER+'''\n}
int main(){return RT64::goemonJPV10TexTraceOn()?0:0;}
'''
        with tempfile.TemporaryDirectory() as root:
            f=Path(root)/'test.cpp';f.write_text(src)
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-pedantic','-fsyntax-only',str(f)],check=True,capture_output=True)

if __name__=='__main__':unittest.main()