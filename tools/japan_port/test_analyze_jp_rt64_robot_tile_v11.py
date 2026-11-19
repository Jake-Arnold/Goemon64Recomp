import unittest
from analyze_jp_rt64_robot_tile_v11 import summarize


class AnalyzerTests(unittest.TestCase):
    def test_robot_only_and_identify_hash(self):
        sample='''[JP-RT64] TEX_QUEUE frame=1 hash=0x000000000000000A size=32x64 decode=1 tmem_bytes=4096 nonzero=3000 fingerprint=0x1 fmt=2 siz=1 tmem=0 line=8 tlut=0 palette=0
[JP-RT64] TEX_CREATE serial=9 frame=1 hash=0x000000000000000A size=32x64 fmt=2 siz=1 tmem=0 line=8 tlut=0 palette=0
[JP-RT64] TEX_ADD frame=1 hash=0x000000000000000A cache_index=89 size=32x64 decoded=1
[JP-RT64] TEX_BIND frame=1 hash=0x000000000000000A cache_index=89 hit=1 requested=32x64 cached=32x64 fmt=2 siz=1 tmem=0 line=8 tlut=0 palette=0 raw_tmem=0 replaced=0
[JP-RT64] TEX_ROBOT_CALL frame=1 root=0x1938 sample=1 call=145 tri=18 overlap=18 tile_start=10 tile_count=1 safe_count=1 texture_on=1 texture_tile=0
[JP-RT64] TEX_ROBOT_TILE frame=1 root=0x1938 sample=1 call=145 slot=0 index=10 valid=1 hash=0x000000000000000A copy=0 requested=32x64 fmt=2 siz=1 tmem=0 line=8 tlut=0 palette=0 raw_tmem=0
[JP-RT64] TEX_ROBOT_TILE frame=1 root=0x1938 sample=1 call=145 slot=0 index=10 valid=1 hash=0x000000000000000A copy=0 requested=32x64 fmt=2 siz=1 tmem=0 line=8 tlut=0 palette=0 raw_tmem=0
'''
        out=summarize(sample,'0x1938')
        self.assertIn('unique_call_tiles=1',out)
        self.assertIn('hash=0x000000000000000a',out)
        self.assertIn('bind_hit=1',out)
        self.assertIn('full_TMEM_nonzero=3000/4096',out)
        self.assertNotIn('No tile rows',out)
    def test_no_v11_rows(self):
        out=summarize('[JP-RT64] TEX_QUEUE frame=1 hash=0x1')
        self.assertIn('No TEX_ROBOT records',out)
    def test_copy_not_misread_as_cache_hash(self):
        s='[JP-RT64] TEX_ROBOT_TILE frame=1 root=0x1938 sample=1 call=145 slot=0 index=10 valid=1 hash=0xAB copy=1 requested=32x64'
        o=summarize(s)
        self.assertIn('framebuffer tile copy',o)
        self.assertIn('normal_texture_hashes=0',o)

if __name__=='__main__':unittest.main()