"""Synthetic source, backup and fail-closed checks for v18.

Uses real v16 transformer fixtures rather than a running Japanese game.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import jp_rt64_texture_segment_v16 as v16
import jp_rt64_texture_alias_v18 as v18

PRISTINE = v16.INCLUDE_ANCHOR + 'namespace RT64 {\n' + v16.FUNCTION_ANCHOR + '}\n'
V16 = v16.transform(PRISTINE)


class Tests(unittest.TestCase):
    def test_transform(self):
        transformed = v18.transform(V16)
        self.assertIn(v18.MARKER, transformed)
        self.assertIn('physical != 0x007CA950u', transformed)
        self.assertIn('minus_4MiB_nz4096', transformed)
        self.assertIn('0x00406950u', transformed)
        self.assertEqual(transformed.count('std::fprintf(stderr,'), 2)

    def test_idempotence(self):
        with self.assertRaisesRegex(ValueError, 'already installed'):
            v18.transform(v18.transform(V16))

    def test_source_gate(self):
        with self.assertRaisesRegex(ValueError, 'v16 source required'):
            v18.transform(V16.replace(v16.MARKER, ''))

    def test_guard_unique(self):
        with self.assertRaisesRegex(ValueError, 'filter'):
            v18.transform(V16.replace('physical != 0x007953D0u', 'physical != 0x007953D4u'))

    def test_log_unique(self):
        with self.assertRaisesRegex(ValueError, 'ending'):
            v18.transform(V16 + v18.OLD_TAIL)

    def test_original_untouched(self):
        before = V16
        _ = v18.transform(before)
        self.assertEqual(before, V16)

    def test_pin_and_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / v18.RSP
            src.parent.mkdir(parents=True)
            original = PRISTINE.encode()
            previous = v16.transform(PRISTINE).encode()
            src.write_bytes(previous)
            src.with_name(src.name + v16.BACKUP).write_bytes(original)
            with patch.object(v16, 'verify_rom'), patch.object(v16, 'RSP_GIT_BLOB', v16.git_blob(original)):
                path, got, new = v18.plan(root, root / 'rom')
                self.assertEqual(path, src)
                self.assertEqual(got, previous)
                self.assertIn(v18.MARKER.encode(), new)
                src.with_name(src.name + v18.BACKUP).write_bytes(previous)
                with self.assertRaisesRegex(ValueError, 'backup already exists'):
                    v18.plan(root, root / 'rom')
                self.assertEqual(src.read_bytes(), previous)

    def test_source_drift_no_write(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / v18.RSP
            src.parent.mkdir(parents=True)
            original = PRISTINE.encode()
            src.write_bytes(b'changed')
            src.with_name(src.name + v16.BACKUP).write_bytes(original)
            with patch.object(v16, 'verify_rom'), patch.object(v16, 'RSP_GIT_BLOB', v16.git_blob(original)):
                with self.assertRaisesRegex(ValueError, 'differs from exact v16'):
                    v18.plan(root, root / 'rom')
                self.assertEqual(src.read_bytes(), b'changed')

    def test_boundaries(self):
        self.assertLessEqual(0x007CA950 + 4096, 8 * 1024 * 1024)
        self.assertLessEqual(0x003CA950 + 4096, 4 * 1024 * 1024)
        self.assertLessEqual(0x00406950 + 4096, 8 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
