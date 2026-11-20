"""ROM-free synthetic tests for Japanese metadata completion.

The artificial 32 MiB fixture and dummy TOML contain NO game code. The hash
is mocked only in positive unit tests; real CLI verifies exact ROM SHA-1.
"""
import tomllib
import unittest
from unittest.mock import patch

try:
    from .complete_symbols import complete, JP_DECOMP
except ImportError:
    from complete_symbols import complete, JP_DECOMP


def fixture():
    # Input contains exactly 7351 functions and 6418 relocations in 72 sections.
    parts = [
        '# INCOMPLETE JAPAN N64RECOMP CANDIDATE MAP. NOT READY FOR PC BOOT.',
        '[[section]]',
        'name = ".entry"',
        'rom = 0x1000',
        'vram = 0x80000400',
        'size = 0x50',
        'functions = [',
        '    { name = "recomp_entrypoint", vram = 0x80000400, size = 0x38 },',
        ']',
        '[[section]]',
        'name = ".main"',
        'rom = 0x1050',
        'vram = 0x80000450',
        'size = 0x833C0',
        'functions = [',
        '    { name = "func_80049604_4A204", vram = 0x80049604, size = 0xE8 },',
        '    { name = "func_80014900_15500", vram = 0x80014900, size = 0x68 },',
    ]
    parts += [
        f'    {{ name = "dummy_{i}", vram = 0x80060000, size = 0x4 }},'
        for i in range(7348)
    ]
    parts.append(']')
    for idx in range(11, 81):
        parts.extend([
            '[[section]]', f'name = ".file_{idx}"',
            f'rom = 0x{0x700000 + idx * 0x100:08X}',
            'vram = 0x08000000' if idx >= 24 else 'vram = 0x801D0B90',
            'size = 0x100',
        ])
        if idx == 24:
            parts.append('relocs = [')
            parts.extend([
                '    { type = "R_MIPS_26", vram = 0x08000000, target_vram = 0x08000020 },'
                for _ in range(6418)
            ])
            parts.append(']')
        parts += ['functions = [', ']']
    return '\n'.join(parts) + '\n'


class MetadataCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.symbols = fixture()
        cls.rom = bytearray(0x2000000)
        cls.rom[0x4A2B8:0x4A2BC] = (0x3C013000).to_bytes(4, 'big')
        cls.rom = bytes(cls.rom)

    def completed(self, symbols=None, rom=None):
        class Digest:
            def hexdigest(self):
                return JP_DECOMP

        with patch('hashlib.sha1', return_value=Digest()):
            return complete(symbols or self.symbols,
                            rom if rom is not None else self.rom)

    def test_full_function_and_relocation_completion(self):
        output, stats = self.completed()
        result = tomllib.loads(output)['section']
        main = result[1]['functions']
        self.assertEqual(stats['functions'], 7376)
        self.assertEqual(stats['relocations'], 6418)
        self.assertEqual(stats['dynamic_overlay_tables'], 57)
        self.assertEqual(stats['new_wave_functions'], 24)
        self.assertTrue(any(x['name'] == 'func_80013D54_14954' for x in main))
        self.assertTrue(any(x['name'] == 'send_mesg' for x in main))
        self.assertTrue(any(x['name'] == 'handle_CpU' for x in main))
        self.assertFalse(any(x['name'] == 'func_80049604_4A204' for x in main))
        for name in ('.file_52', '.file_76'):
            section = next(s for s in result if s['name'] == name)
            self.assertEqual(section['relocs'], [])

    def test_refuses_to_reapply(self):
        output, _ = self.completed()
        with self.assertRaisesRegex(ValueError, 'baseline counts'):
            self.completed(output)

    def test_unknown_rom_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ROM revision mismatch'):
            complete(self.symbols, self.rom)

    def test_wrong_libultra_instruction_rejected(self):
        data = bytearray(self.rom)
        data[0x4A2B8] = 0
        with self.assertRaisesRegex(ValueError, 'boundary instruction changed'):
            self.completed(rom=bytes(data))

    def test_unexpected_function_inventory_rejected(self):
        corrupted = self.symbols.replace(
            '{ name = "func_80014900_15500", vram = 0x80014900, size = 0x68 },', '', 1
        )
        with self.assertRaisesRegex(ValueError, 'baseline counts'):
            self.completed(corrupted)

    def test_missing_merged_libultra_entry_rejected(self):
        corrupted = self.symbols.replace('func_80049604_4A204',
                                         'unknown_merged_function', 1)
        with self.assertRaisesRegex(ValueError, 'combined libultra'):
            self.completed(corrupted)

    def test_wave_overlap_rejected(self):
        corrupted = self.symbols.replace(
            '{ name = "func_80014900_15500", vram = 0x80014900, size = 0x68 },',
            '{ name = "func_80014900_15500", vram = 0x800134D0, size = 0x68 },', 1
        )
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            self.completed(corrupted)


if __name__ == '__main__':
    unittest.main()
