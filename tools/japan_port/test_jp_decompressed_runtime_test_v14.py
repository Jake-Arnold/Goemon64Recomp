import hashlib
from pathlib import Path
import tempfile
import unittest

import jp_decompressed_runtime_test_v14 as p


class TestJPDecompressedInputV14(unittest.TestCase):
    def setUp(self):
        self.sample = (
            "int main(int argc, char** argv) {\n"
            + p.VERSION_ANCHOR +
            "// other stuff\n"
            + p.REGISTER_ANCHOR +
            "return 0;\n}\n"
        )

    def test_git_blob_calculation(self):
        self.assertEqual(p.git_blob(b"test\n"), hashlib.sha1(b"blob 5\0test\n").hexdigest())

    def test_hash_and_originals_pinned(self):
        self.assertEqual(p.JP_DECOMP_BYTES, 0x2000000)
        self.assertEqual(p.JP_DECOMP_SHA1, '6f8745fecc3a5e7d4918c7a73353eb0726116ded')
        self.assertEqual(p.JP_DECOMP_XXH3, 0xC519E0E26FA0D20E)
        self.assertEqual(p.ORIGINAL_MAIN_BLOB, '6e6d2c5afae012b91507b85f114f3e31ebef7165')

    def test_transforms_and_preserves_original(self):
        actual = p.transform(self.sample)
        self.assertIn('const char *jpDecompressedTestInput = nullptr;', actual)
        self.assertIn('testGame.rom_hash = 0xC519E0E26FA0D20EULL;', actual)
        self.assertIn('testGame.has_compressed_code = false;', actual)
        self.assertIn('testGame.decompression_routine = nullptr;', actual)
        self.assertIn('testGame.game_id = u8"mnsg.jp.decomp-test";', actual)
        self.assertIn('mnsg.jp.decomp-test.z64', actual)
        self.assertIn('recomp::select_rom(', actual)
        self.assertEqual(actual.count(p.MARKER), 1)
        self.assertEqual(actual.count(p.REGISTER_ANCHOR), 1)

    def test_fail_closed_reapply(self):
        with self.assertRaisesRegex(ValueError, 'already installed'):
            p.transform(p.transform(self.sample))

    def test_fail_closed_anchor_drift(self):
        with self.assertRaisesRegex(ValueError, 'expected one'):
            p.transform(self.sample.replace('recomp::Version project_version{};', 'int nope = 3;'))
        with self.assertRaisesRegex(ValueError, 'expected one'):
            p.transform(self.sample + p.VERSION_ANCHOR)

    def test_wrong_rom_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / 'bad.z64'
            bad.write_bytes(bytes.fromhex('80371240') + b'wrong')
            with self.assertRaisesRegex(ValueError, 'ROM rejected'):
                p.verify_rom(bad)

    def test_plan_rejects_rom_before_modifying_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'main.cpp'
            path.write_text(self.sample)
            rom = Path(d) / 'rom.z64'
            rom.write_bytes(bytes.fromhex('80371240') + b'bad')
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'ROM rejected'):
                p.plan(path, rom)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()