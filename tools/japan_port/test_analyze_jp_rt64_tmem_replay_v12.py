import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import analyze_jp_rt64_tmem_replay_v12 as p

class AnalyzerTests(unittest.TestCase):
    def test_zero_source(self):
        text='''[JP-RT64] TEX_REPLAY_TARGET frame=5 call=140 hash=0x8042c12b60ec2b4e tile_index=8 total_tmem_nonzero=0 recent_loads=1
[JP-RT64] TEX_REPLAY_LOAD frame=5 call=140 hash=0x8042c12b60ec2b4e index=3 type=0 source_tex=0x00000200 source_start=0x00000200 source_nonzero64=0 load_fmt=0 load_siz=2 width=32 tile_fmt=0 tile_siz=2 tmem=0 line=8 uls=0 ult=0 lrs=124 lrt=252 tmem_nz_before=0 tmem_nz_after=0'''
        s=p.summarise(text)
        self.assertIn('ALL_ZERO frame=5 call=140',s)
        self.assertIn('RDRAM_nz64=0/64',s)
        self.assertIn('whole_TMEM_nz=0->0',s)
    def test_unread_and_isolation(self):
        text='''[JP-RT64] TEX_REPLAY_TARGET frame=5 call=143 hash=0x4263ca7ef085e861 total_tmem_nonzero=3550 recent_loads=1
[JP-RT64] TEX_REPLAY_LOAD frame=5 call=143 hash=0x4263ca7ef085e861 index=7 type=1 source_start=0x00D00000 source_nonzero64=4294967295 tmem_nz_before=3 tmem_nz_after=3550'''
        s=p.summarise(text)
        self.assertIn('NONZERO',s)
        self.assertIn('UNREAD_OUT_OF_RANGE',s)
        self.assertNotIn('ALL_ZERO',s)
    def test_no_records(self):
        self.assertIn('No v12 replay events',p.summarise(''))
    def test_parser(self):
        self.assertEqual(p.records('[JP-RT64] TEX_REPLAY_TARGET frame=1 hash=0x1')[0]['hash'],'0x1')

if __name__=='__main__':unittest.main()