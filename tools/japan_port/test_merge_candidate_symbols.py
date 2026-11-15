"""Ensure the provisional Japanese TOML merger rejects invalid metadata."""
import unittest

try:
    from .merge_candidate_symbols import merge, JP_DECOMP
except ImportError:
    from merge_candidate_symbols import merge, JP_DECOMP

SYMS = '''[[section]]
name = ".entry"
rom = 0x1000
vram = 0x80000400
size = 0x50
functions = [
]

[[section]]
name = ".file_24"
rom = 0x12340
vram = 0x08000000
size = 0x100
functions = [
    { name = "func_08000000_12340", vram = 0x08000000, size = 0x20 },
]
'''

DATA = {
    'source_sha1': JP_DECOMP,
    'candidate_relocations': 2,
    'relocations': {
        'file_24': [
            {'type': 'R_MIPS_HI16', 'vram': '0x08000000', 'target_vram': '0x08000020'},
            {'type': 'R_MIPS_LO16', 'vram': '0x08000004', 'target_vram': '0x08000020'},
        ],
    },
}


class TestMerge(unittest.TestCase):
    def test_success(self):
        output, stats = merge(SYMS, DATA)
        self.assertEqual((stats['sections'], stats['functions'], stats['relocations']),
                         (2, 1, 2))
        self.assertIn('INCOMPLETE JAPAN', output)

    def test_wrong_region(self):
        with self.assertRaisesRegex(ValueError, 'Japanese'):
            merge(SYMS, {**DATA, 'source_sha1': '0' * 40})

    def test_unknown_section(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            merge(SYMS, {**DATA, 'relocations': {'file_25': DATA['relocations']['file_24']}})

    def test_duplicate_site(self):
        records = [DATA['relocations']['file_24'][0]] * 2
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            merge(SYMS, {**DATA, 'relocations': {'file_24': records}})

    def test_bad_target(self):
        records = [{**DATA['relocations']['file_24'][0],
                    'target_vram': '0x08000104'}, DATA['relocations']['file_24'][1]]
        with self.assertRaisesRegex(ValueError, 'out of bounds'):
            merge(SYMS, {**DATA, 'relocations': {'file_24': records}})

    def test_bss_target_requires_verified_bounds(self):
        records = [
            {**item, 'target_vram': '0x08000110'}
            for item in DATA['relocations']['file_24']
        ]
        example = {**DATA, 'relocations': {'file_24': records}}
        with self.assertRaisesRegex(ValueError, 'out of bounds'):
            merge(SYMS, example)
        output, statistics = merge(SYMS, example, {'.file_24': 0x20})
        self.assertIn('0x08000110', output)
        self.assertEqual(statistics['relocations'], 2)

    def test_zero_reloc_overlay_still_marked_relocatable(self):
        # N64Recomp only registers a section as relocatable if its
        # TOML includes a 'relocs' array (including relocs = []).
        output, statistics = merge(SYMS, {
            'source_sha1': JP_DECOMP,
            'candidate_relocations': 0,
            'relocations': {},
        })
        import tomllib
        sections = tomllib.loads(output)['section']
        self.assertNotIn('relocs', sections[0])
        self.assertIn('relocs', sections[1])
        self.assertEqual(sections[1]['relocs'], [])
        self.assertEqual(statistics['relocations'], 0)

    def test_bss_limit_cannot_be_negative(self):
        with self.assertRaisesRegex(ValueError, 'Invalid BSS'):
            merge(SYMS, DATA, {'.file_24': -4})

    def test_bss_limit_must_belong_to_section(self):
        with self.assertRaisesRegex(ValueError, 'Invalid BSS'):
            merge(SYMS, DATA, {'.file_25': 64})


if __name__ == '__main__':
    unittest.main()
