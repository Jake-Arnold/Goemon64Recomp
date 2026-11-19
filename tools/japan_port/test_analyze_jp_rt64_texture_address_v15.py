"""Synthetic read-only log parser tests; no ROM data needed."""
import unittest
from analyze_jp_rt64_texture_address_v15 import summarize, byte_offset


def row(start, image, typ=1, width=32, siz=2, uls=0, ult=0, lower=42):
    return (f'[JP-RT64] TEX_REPLAY_LOAD frame=450 call=182 hash=0x8042C12B60EC2B4E '
            f'index=1 type={typ} source_tex=0x{image:08X} source_start=0x{start:08X} '
            f'source_nonzero64=0 load_fmt=0 load_siz={siz} width={width} '
            f'tile_fmt=0 tile_siz=2 uls={uls} ult={ult} '
            f'tmem_nz_before=3812 tmem_nz_after=0 candidate_minus_3c4000_nz64={lower}')


class AddressV15(unittest.TestCase):
    def test_high_base_zero_offset(self):
        output = summarize([row(0x78B6E0, 0x78B6E0)] * 16)
        self.assertIn('0x0078B6E0: 16 replay records', output)
        self.assertIn('formula=MATCH', output)
        self.assertIn('candidate image base=0x003C76E0', output)
        self.assertIn('whole TMEM=3812->0', output)

    def test_block_offset_is_accounted_for(self):
        output = summarize([row(0x7953D0, 0x795300, uls=104, lower=64)] * 8)
        self.assertIn('byte_offset=0xD0', output)
        self.assertIn('formula=MATCH', output)
        self.assertIn('candidate image base=0x003D1300', output)
        self.assertIn('0x007953D0: 8 replay records', output)

    def test_tile_offsets(self):
        f = {'type': '0', 'width': '32', 'load_siz': '2', 'uls': '4', 'ult': '8'}
        self.assertEqual(byte_offset(f), 130)

    def test_offset_as_possible_cause(self):
        output = summarize([row(0x78B6E0, 0x3C76E0, width=32, ult=0xF100)])
        self.assertIn('formula=', output)
        self.assertIn('load tile offset is at least 0x003C4000', output)

    def test_missing_metadata(self):
        output = summarize(['[JP-RT64] TEX_REPLAY_LOAD source_start=0x0078B6E0'])
        self.assertIn('source_tex=NOT_LOGGED', output)
        self.assertIn('formula=NOT_CHECKED', output)
        self.assertIn('source_tex missing', output)

    def test_unknown_not_zero(self):
        line = row(0x78B6E0, 0x78B6E0).replace('source_nonzero64=0', 'source_nonzero64=4294967295')
        output = summarize([line])
        self.assertIn('first64 high=UNREAD', output)
        self.assertNotIn('first64 high=0/64', output)

    def test_different_starts_ignored(self):
        output = summarize([row(0x7abcde, 0x7abcde)])
        self.assertIn('0x0078B6E0: 0 replay records', output)

    def test_formula_mismatch_detected(self):
        output = summarize([row(0x78B6E0, 0x78B6E4)])
        self.assertIn('MISMATCH:0x0078B6E4', output)

    def test_duplicate_group_collapse(self):
        output = summarize([row(0x78B6E0, 0x78B6E0)] * 3)
        self.assertIn('distinct load configurations: 1', output)
        self.assertIn('x3 Block', output)


if __name__ == '__main__':
    unittest.main()
