from __future__ import annotations
import unittest
from analyze_jp_rt64_raster_v8 import summarize

class Tests(unittest.TestCase):
    def test_sum_tagged_overlap(self):
        s='\n'.join([
          '[JP-RT64] FACE_RANGE root=0x12F0 sample=1 frame=117 first=30 end=54 triangles=8',
          '[JP-RT64] FACE_RANGE root=0x1420 sample=1 frame=117 first=54 end=78 triangles=8',
          '[JP-RT64] RASTER BUILT root=0x12F0 sample=1 frame=117 instance=19 call=12 call_tri=12 overlap_tri=8 type=1 scissor_empty=0 pipeline=1',
          '[JP-RT64] RASTER BUILT root=0x1420 sample=1 frame=117 instance=19 call=12 call_tri=12 overlap_tri=4 type=1 scissor_empty=0 pipeline=1',
          '[JP-RT64] RASTER DRAW_RECORDED root=0x12F0 sample=1 instance=19 call_tri=12 overlap_tri=8 empty_scissor=0',
          '[JP-RT64] RASTER DRAW_RECORDED root=0x1420 sample=1 instance=19 call_tri=12 overlap_tri=4 empty_scissor=0',
          '[JP-RT64] RASTER BUILT root=0x1420 sample=1 frame=117 instance=20 call=13 call_tri=4 overlap_tri=4 type=1 scissor_empty=1 pipeline=1',
          '[JP-RT64] RASTER SKIP_SCISSOR root=0x1420 sample=1 instance=20 call_tri=4 overlap_tri=4 empty_scissor=1',
        ])
        out=summarize(s)
        self.assertIn('0x12F0: range=8 built=8 gpu_command_recorded=8',out)
        self.assertIn('0x1420: range=8 built=8 gpu_command_recorded=4 skip_scissor=4',out)
        self.assertIn('TOTAL recorded=12',out)
        self.assertIn('TOTAL scissor=4',out)
    def test_empty(self):
        self.assertIn('No v8',summarize('hello'))
    def test_invalid_range(self):
        out=summarize('[JP-RT64] FACE_RANGE root=0x12F0 sample=1 frame=117 first=0 end=15 triangles=8')
        self.assertIn('WARNINGS',out)
if __name__=='__main__':unittest.main()