"""Tests for authoritative relocation set comparisons."""
import unittest

try:
    from .audit_relocations import difference
except ImportError:
    from audit_relocations import difference

REF = {'section': [
    {'name': '.entry', 'relocs': []},
    {'name': '.file_24', 'relocs': [
        {'type': 'R_MIPS_HI16', 'vram': 0x08000000, 'target_vram': 0x08000020},
        {'type': 'R_MIPS_LO16', 'vram': 0x08000004, 'target_vram': 0x08000020},
    ]},
]}
CAND = {'relocations': {'file_24': [
    {'type': 'R_MIPS_HI16', 'vram': '0x08000000', 'target_vram': '0x08000020'},
    {'type': 'R_MIPS_26', 'vram': '0x0800000C', 'target_vram': '0x08000030'},
]}}


class TestCompare(unittest.TestCase):
    def test_exact(self):
        same = {'relocations': {'file_24': [
            {'type': rec['type'], 'vram': f"0x{rec['vram']:08X}",
             'target_vram': f"0x{rec['target_vram']:08X}"}
            for rec in REF['section'][1]['relocs']
        ]}}
        stats = difference(REF, same)['summary']
        self.assertEqual((stats['exact_sections'], stats['missing'], stats['extra']),
                         (1, 0, 0))

    def test_missing_and_extra(self):
        stats = difference(REF, CAND)['summary']
        self.assertEqual((stats['exact_sections'], stats['missing'], stats['extra']),
                         (0, 1, 1))

    def test_unknown_section(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            difference(REF, {'relocations': {'file_100': []}})


if __name__ == '__main__':
    unittest.main()
