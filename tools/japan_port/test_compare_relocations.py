"""Synthetic regression tests for authoritative relocation comparisons."""
import unittest
try:
    from .compare_relocations import audit, USA_ROM_SHA1
except ImportError:
    from compare_relocations import audit, USA_ROM_SHA1

REF = [{'name': '.file_24', 'relocs': [
    {'type': 'R_MIPS_HI16', 'vram': 0x08000000, 'target_vram': 0x080000A0},
    {'type': 'R_MIPS_LO16', 'vram': 0x08000004, 'target_vram': 0x080000A0},
]}]
INPUT = {'source_sha1': USA_ROM_SHA1, 'relocations': {'file_24': [
    {'type': 'R_MIPS_LO16', 'vram': '0x08000004', 'target_vram': '0x080000A0'},
    {'type': 'R_MIPS_HI16', 'vram': '0x08000000', 'target_vram': '0x080000A0'},
]}}


class ComparisonTests(unittest.TestCase):
    def test_unordered_records_match(self):
        result = audit(INPUT, REF, 24, 24)
        self.assertEqual(result['matched_records'], 2)
        self.assertTrue(result['exact_type_site_target_match'])

    def test_missing_record_rejected(self):
        wrong = {**INPUT, 'relocations': {'file_24': INPUT['relocations']['file_24'][:1]}}
        with self.assertRaisesRegex(ValueError, 'Relocation mismatch'):
            audit(wrong, REF, 24, 24)

    def test_wrong_target_rejected(self):
        records = [dict(row) for row in INPUT['relocations']['file_24']]
        records[0]['target_vram'] = '0x080000C0'
        with self.assertRaisesRegex(ValueError, 'Relocation mismatch'):
            audit({**INPUT, 'relocations': {'file_24': records}}, REF, 24, 24)

    def test_wrong_revision_rejected(self):
        with self.assertRaisesRegex(ValueError, 'pinned USA'):
            audit({**INPUT, 'source_sha1': '0'*40}, REF, 24, 24)

    def test_missing_section_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing expected'):
            audit(INPUT, [], 24, 24)


if __name__ == '__main__':
    unittest.main()
