from __future__ import annotations
import unittest
from analyze_jp_rt64_target_state_v9 import parse,summarize


def record(target:int=0,color:int=0x12c000,frame:int=893,call:int=140,root:int=0x1938,tri:int=4,
           alpha:int=0,blend:int=0)->str:
    return (f'[JP-RT64] TARGET_STATE root=0x{root:04X} sample=1 frame={frame} source_frame={frame} '
        f'call={call} target={target} fbpair=3 instance=139 color=0x{color:08X} depth=0x0016D000 '
        f'color_target=0x{color:08X} depth_target=0x0016D000 overlap_tri={tri} face_count={tri} '
        f'other_h=0x0BE01234 other_l=0x0ABCDEF1 alpha_compare=0x{alpha:08X} force_blend={blend} '
        'cvg_x_alpha=1 alpha_cvg_sel=0 zcmp=1 zupd=1 zmode=0x00000400 culling=1 scissor=0,0,320,240')

class V9SummaryTests(unittest.TestCase):
    def test_repeats_are_not_unique_geometry(self):
        s=summarize('\n'.join([record(0),record(1),record(1)]))
        self.assertIn('unique=4/64 raw=12 repeats=8',s)
        self.assertIn('targets=2',s)
        self.assertIn('source_calls_across_targets=1',s)
    def test_distinct_npcs_and_frames(self):
        s=summarize('\n'.join([record(call=140),record(call=141),record(frame=894,call=140)]))
        self.assertIn('unique=12/64 raw=12',s)
    def test_alpha_variance(self):
        s=summarize('\n'.join([record(call=140,alpha=0),record(call=141,alpha=1,blend=1)]))
        self.assertIn('material_states=2',s)
    def test_invalid_frame(self):
        raw=record().replace('source_frame=893','source_frame=892')
        rows,bad=parse(raw)
        self.assertEqual(rows,[])
        self.assertEqual(bad,1)
    def test_missing_trace(self):
        self.assertIn('No valid v9',summarize('hello world'))

if __name__=='__main__':unittest.main()