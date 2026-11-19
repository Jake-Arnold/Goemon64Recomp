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
    def test_same_gamecalls_rebuilt_twice_are_not_extra_geometry(self):
        # One eight-triangle source interval, two unique GameCalls of four
        # triangles each. A second framebuffer pass reuses the same calls
        # with different renderer instance IDs, just like the live v8 log.
        rows = ['[JP-RT64] FACE_RANGE root=0x12F0 sample=1 frame=893 first=100 end=124 triangles=8']
        for instance_delta in (0, 1):
            for call, instance in ((140, 139 + instance_delta), (141, 140 + instance_delta)):
                rows.append(f'[JP-RT64] RASTER BUILT root=0x12F0 sample=1 frame=893 instance={instance} call={call} call_tri=4 overlap_tri=4 type=2 scissor_empty=0 pipeline=1')
            for call, instance in ((140, 139 + instance_delta), (141, 140 + instance_delta)):
                rows.append(f'[JP-RT64] RASTER DRAW_RECORDED root=0x12F0 sample=1 instance={instance} call_tri=4 overlap_tri=4 empty_scissor=0')
        result = summarize('\n'.join(rows))
        self.assertIn('0x12F0: range=8 built=8 gpu_command_recorded=8', result)
        self.assertIn('TOTAL range=8', result)
        self.assertIn('TOTAL built=8', result)
        self.assertIn('TOTAL recorded=8', result)
        self.assertIn('TOTAL raw_recorded=16', result)
        self.assertIn('TOTAL repeat_recorded=8', result)
        self.assertNotIn('WARNINGS', result)

    def test_identical_instance_id_with_two_unique_calls(self):
        # Instance IDs can be reused between resetFramebuffers invocations;
        # only frame+GameCall identifies a source range portion reliably.
        rows = ['[JP-RT64] FACE_RANGE root=0x12F0 sample=1 frame=1 first=0 end=24 triangles=8']
        for call in (9, 10):
            rows.append(f'[JP-RT64] RASTER BUILT root=0x12F0 sample=1 frame=1 instance=7 call={call} call_tri=4 overlap_tri=4 type=2 scissor_empty=0 pipeline=1')
            rows.append('[JP-RT64] RASTER DRAW_RECORDED root=0x12F0 sample=1 instance=7 call_tri=4 overlap_tri=4 empty_scissor=0')
        result = summarize('\n'.join(rows))
        self.assertIn('TOTAL recorded=8', result)
        self.assertIn('TOTAL repeat_recorded=0', result)

    def test_identical_call_number_across_frames_is_distinct(self):
        # Two independent v8 samples from different frames are NOT merged.
        rows = []
        for sample, frame in ((1, 893), (2, 894)):
            rows.extend([
                f'[JP-RT64] FACE_RANGE root=0x12F0 sample={sample} frame={frame} first=12 end=36 triangles=8',
                f'[JP-RT64] RASTER BUILT root=0x12F0 sample={sample} frame={frame} instance=5 call=10 call_tri=8 overlap_tri=8 type=2 scissor_empty=0 pipeline=1',
                f'[JP-RT64] RASTER DRAW_RECORDED root=0x12F0 sample={sample} instance=5 call_tri=8 overlap_tri=8 empty_scissor=0',
            ])
        result = summarize('\n'.join(rows))
        self.assertEqual(result.count('TOTAL recorded=8'), 2)
        self.assertEqual(result.count('TOTAL repeat_recorded=0'), 2)

    def test_empty(self):
        self.assertIn('No v8',summarize('hello'))
    def test_invalid_range(self):
        out=summarize('[JP-RT64] FACE_RANGE root=0x12F0 sample=1 frame=117 first=0 end=15 triangles=8')
        self.assertIn('WARNINGS',out)
if __name__=='__main__':unittest.main()