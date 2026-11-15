"""Check RSP microcode equivalence without shipping ROM contents."""
import hashlib
import unittest

try:
    from .verify_rsp import compare_microcode
    from .rom import RomError
except ImportError:
    from verify_rsp import compare_microcode
    from rom import RomError


class TestAudioMicrocode(unittest.TestCase):
    def setUp(self):
        self.segment = bytes(range(32))
        self.us = b'@' * 13 + self.segment + b'!'
        self.jp = b'?' * 9 + self.segment + b'#'
        self.sha1 = hashlib.sha1(self.segment).hexdigest()

    def test_exact_single_match(self):
        result = compare_microcode(self.us, self.jp, 13, 9, 32, self.sha1)
        self.assertTrue(result['byte_identical'])
        self.assertEqual(result['japan_occurrences'], 1)

    def test_wrong_digest(self):
        with self.assertRaisesRegex(RomError, 'digest'):
            compare_microcode(self.us, self.jp, 13, 9, 32, '0' * 40)

    def test_different_microcode(self):
        with self.assertRaisesRegex(RomError, 'differs'):
            compare_microcode(self.us, self.jp[:-2]+b'XX', 13, 9, 32, self.sha1)

    def test_duplicate_microcode_rejected(self):
        with self.assertRaisesRegex(RomError, 'uniquely'):
            compare_microcode(self.us, self.jp+self.segment, 13, 9, 32, self.sha1)

    def test_invalid_bounds(self):
        with self.assertRaisesRegex(RomError, 'outside'):
            compare_microcode(self.us, self.jp, 13, len(self.jp), 32, self.sha1)


if __name__ == '__main__':
    unittest.main()
