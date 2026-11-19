#!/usr/bin/env python3
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).parent))
import analyze_jp_rt64_texture_origin_v10 as a

DATA='''[JP-RT64] TEX_QUEUE frame=10 hash=0xAAA size=32x64 decode=1 tmem_bytes=4096 nonzero=100 fingerprint=0x123 fmt=0 siz=2 tmem=0 line=8 tlut=0 palette=0
[JP-RT64] TEX_CREATE serial=112003 frame=10 hash=0xAAA size=32x64 fmt=0 siz=2 tmem=0 line=8 tlut=0 palette=0
[JP-RT64] TEX_ADD frame=10 hash=0xAAA cache_index=89 size=32x64 decoded=1
[JP-RT64] TEX_BIND frame=20 hash=0xAAA cache_index=89 hit=1 requested=32x64 cached=32x64 fmt=0 siz=2 tmem=0 line=8 tlut=0 palette=0 raw_tmem=0 replaced=0
[JP-RT64] TEX_QUEUE frame=11 hash=0xBBB size=32x64 decode=1 tmem_bytes=4096 nonzero=0 fingerprint=0x111 fmt=0 siz=2 tmem=0 line=8 tlut=0 palette=0
[JP-RT64] TEX_ADD frame=11 hash=0xBBB cache_index=7 size=32x64 decoded=1
'''
class AnalyzeTests(unittest.TestCase):
    def test_read(self):self.assertEqual(len(a.read_rows(DATA)),6)
    def test_join(self):
        s=a.summarize(a.read_rows(DATA),'112003',89)
        self.assertIn('matched_hashes=1',s)
        self.assertIn('serial=112003 cache_index=89',s)
        self.assertIn('nonzero=100',s)
        self.assertNotIn('hash=0xbbb',s)
    def test_missing_source(self):
        s=a.summarize(a.read_rows('[JP-RT64] TEX_BIND frame=20 hash=0xEEE cache_index=89 hit=1'),'999')
        self.assertIn('matched_hashes=0',s)
    def test_zero_tmem(self):
        s=a.summarize(a.read_rows(DATA),cache_index=7)
        self.assertIn('entirely zero',s)
    def test_stable_across_other_events(self):
        self.assertEqual(a.read_rows('not a trace\n'),[])

if __name__=='__main__':unittest.main()