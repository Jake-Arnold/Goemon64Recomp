#!/usr/bin/env python3
import unittest
import jp_rt64_tmem_replay_v12 as v12
import jp_rt64_tmem_high_address_v13 as v13
v10 = v12.v11.v10

class Guards(unittest.TestCase):
    @staticmethod
    def fixture():
        pristine=(v12.INCLUDE_OLD+v12.FUNCTION_OLD+v12.LOAD_OLD+v12.AFTER_LOAD_OLD+v12.UPLOAD_OLD+'\n'+v10.v7.MARKER+'\n')
        return v12.transform_state(pristine)
    def test_installed_v12_upgrade(self):
        old=self.fixture()
        new=v13.transform_state(old)
        self.assertIn(v13.MARKER,new)
        self.assertIn('Runtime8MiB',new)
        self.assertIn('candidate_minus_3c4000_nz64',new)
        self.assertNotIn('Conservative4MiB',new)
        self.assertEqual(new.count('0x0078B6E0ull'),1)
        self.assertEqual(new.count('0x007953D0ull'),1)
    def test_idempotent_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'already installed'):
            v13.transform_state(v13.transform_state(self.fixture()))
    def test_old_v7_rejected(self):
        with self.assertRaisesRegex(ValueError,'v12 State instrumentation required'):
            v13.transform_state(v12.INCLUDE_OLD+v10.v7.MARKER)
    def test_source_drift(self):
        bad=self.fixture().replace('rec.srcNz64 = 0xFFFFFFFFu; // not sampled (outside conservative 4 MiB bound)', 'rec.srcNz64 = 0; // drift')
        with self.assertRaisesRegex(ValueError,'bounded RDRAM sample: expected 1 exact v12 anchor; found 0'):
            v13.transform_state(bad)
    def test_orig_remains_unchanged(self):
        src=self.fixture()
        v13.transform_state(src)
        self.assertIn('Conservative4MiB',src)
    def test_paired_address_differences(self):
        self.assertEqual(0x78b6e0-0x3c76e0,0x3c4000)
        self.assertEqual(0x7953d0-0x3d13d0,0x3c4000)

if __name__=='__main__':unittest.main()