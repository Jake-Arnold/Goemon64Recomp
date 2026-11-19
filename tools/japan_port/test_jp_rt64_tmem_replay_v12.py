import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,str(Path(__file__).parent/'fixture'))
import jp_rt64_tmem_replay_v12 as p

class TransformTests(unittest.TestCase):
    @staticmethod
    def fixture()->str:
        return (p.INCLUDE_OLD+'\n// '+p.v11.v10.v7.MARKER+'\n'
                +p.FUNCTION_OLD+p.LOAD_OLD+p.AFTER_LOAD_OLD+p.UPLOAD_OLD+'\n}')
    def test_source_hook(self):
        s=p.transform_state(self.fixture())
        self.assertIn(p.MARKER,s)
        self.assertIn('TEX_REPLAY_TARGET',s)
        self.assertIn('TEX_REPLAY_LOAD',s)
        self.assertIn('Conservative4MiB',s)
        self.assertNotIn('RDRAM[size_t(source)', self.fixture())
    def test_idempotence_refused(self):
        with self.assertRaisesRegex(ValueError,'already installed'):p.transform_state(p.transform_state(self.fixture()))
    def test_broken_load_anchor_refused(self):
        with self.assertRaisesRegex(ValueError,'expected exactly one'):p.transform_state(self.fixture().replace(p.LOAD_OLD,'garbled'))
    def test_broken_function_anchor_refused(self):
        with self.assertRaisesRegex(ValueError,'expected exactly one'):p.transform_state(self.fixture().replace(p.FUNCTION_OLD,'garbled'))
    def test_duplicate_anchor_refused(self):
        with self.assertRaisesRegex(ValueError,'expected exactly one'):p.transform_state(self.fixture()+p.UPLOAD_OLD)
    def test_missing_v7_refused(self):
        with self.assertRaisesRegex(ValueError,'v7 State instrumentation'):p.transform_state(self.fixture().replace(p.v11.v10.v7.MARKER,''))
    def test_exact_bad_and_comparison_hashes(self):
        s=p.transform_state(self.fixture())
        self.assertIn('0x8042c12b60ec2b4eull',s)
        self.assertIn('0x4263ca7ef085e861ull',s)
        self.assertIn('jpV12Printed < 16u',s)

if __name__=='__main__':unittest.main()