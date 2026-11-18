"""Bounded decompression and original-model inventory tests (ROM-free)."""
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
import audit_jp_robot_displaylists as audit


class AuditTests(unittest.TestCase):
    def test_short_rejected(self):
        for raw in (b'', b'\x00\x00\x00\x03',b'\x00\x00\x00\x05\x00'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                audit.decode_lzkn64(raw)

    def test_raw_copy_and_rle(self):
        # 3 literal bytes, 2 repetitions of 0x41, 2 zero bytes.
        raw=b'\x00\x00\x00\x0B\x83ABC\xA0A\xE0'
        self.assertEqual(audit.decode_lzkn64(raw),b'ABCAA\x00\x00')

    def test_lz_repetition(self):
        raw=b'\x00\x00\x00\x09\x82AB\x00\x02'
        self.assertEqual(audit.decode_lzkn64(raw),b'ABAB')

    def test_bad_original_rom_rejected(self):
        with self.assertRaisesRegex(ValueError,'exact original'):
            audit.audit(b'not a ROM')

    def test_verified_list_total(self):
        self.assertEqual(len(audit.LISTS),7)
        self.assertEqual(sum(x[1] for x in audit.LISTS.values()),264)
        self.assertEqual(sum(x[2] for x in audit.LISTS.values()),104)
        self.assertEqual(audit.LISTS[0x1938][3],(12,9,11))

if __name__=='__main__':unittest.main()