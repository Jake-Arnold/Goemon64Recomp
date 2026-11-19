#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path
import tempfile
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,str(Path(__file__).parent/'fixture'))
import jp_rt64_robot_texture_link_v11 as p


class SourceTests(unittest.TestCase):
    @staticmethod
    def fake_v10_renderer():
        return p.v10.RENDER_HELPER + p.v10.MARKER+'\n'+p.ROBOT_ANCHOR
    def test_exact_v8_site_is_in_v8_renderer_template(self):
        self.assertEqual(p.v10.v8.RENDER_INSTANCE_NEW.count(p.ROBOT_ANCHOR),1)
    def test_renderer_v10_helper_anchor_unique(self):
        self.assertEqual(p.v10.RENDER_HELPER.count(p.ATOM_OLD),1)
    def test_transform_writes_bounded_root_hashes(self):
        s=p.transform_renderer(self.fake_v10_renderer())
        self.assertIn(p.MARKER,s)
        self.assertIn('TEX_ROBOT_TILE',s)
        self.assertIn('TEX_ROBOT_CALL',s)
        self.assertIn('1024u',s)
        self.assertIn('tileCount',s)
        self.assertIn('drawData.callTiles.size()',s)
        self.assertIn('goemonJPV10TexTraceOn()',s)
    def test_fail_closed_on_reapply(self):
        s=p.transform_renderer(self.fake_v10_renderer())
        with self.assertRaisesRegex(ValueError,'already installed'):p.transform_renderer(s)
    def test_fail_closed_on_drift(self):
        s=self.fake_v10_renderer()
        with self.assertRaisesRegex(ValueError,'pinned anchor'):p.transform_renderer(s.replace(p.ROBOT_ANCHOR,'bad site'))
        with self.assertRaisesRegex(ValueError,'pinned anchor'):p.transform_renderer(s.replace(p.ATOM_OLD,'bad helper'))
    def test_rom_guard_no_files_written(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);rom=path/'rom';rom.write_bytes(b'bad')
            with self.assertRaises(Exception):p.plan(path,rom)
            self.assertEqual(sorted(x.name for x in path.iterdir()),['rom'])

if __name__=='__main__':unittest.main()