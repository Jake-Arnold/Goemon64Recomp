import unittest
from analyze_jp_rt64_high_address_v13 import summarize

class Summary(unittest.TestCase):
    def test_zero_upper_nonzero_lower(self):
        s='[JP-RT64] TEX_REPLAY_LOAD frame=450 call=182 source_start=0x0078B6E0 source_nonzero64=0 candidate_minus_3c4000_nz64=42 tmem_nz_before=3812 tmem_nz_after=0'
        out=summarize(s)
        self.assertIn('high_RDRAM_nz64=0/64',out)
        self.assertIn('lower-offset control has nonzero',out)
    def test_no_evidence_with_unread(self):
        s='[JP-RT64] TEX_REPLAY_LOAD source_start=0x007953D0 source_nonzero64=4294967295 candidate_minus_3c4000_nz64=0 tmem_nz_before=4096 tmem_nz_after=0'
        out=summarize(s)
        self.assertIn('high_RDRAM_nz64=UNREAD',out)
        self.assertNotIn('hypothesis strengthened',out)
    def test_no_data(self):
        self.assertIn('No matching loads',summarize('unrelated'))

if __name__=='__main__':unittest.main()