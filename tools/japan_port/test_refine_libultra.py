"""Protect the ROM-verified handwritten libultra function split."""
import unittest
from unittest.mock import patch

try:
    from . import refine_libultra as module
except ImportError:
    import refine_libultra as module


SYMBOLS = '''[[section]]
name = ".main"
rom = 0x1050
vram = 0x80000450
size = 0x7DBD0
functions = [
    { name = "func_80049604_4A204", vram = 0x80049604, size = 0xE8 },
]
'''


class KnownLibultraTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = bytearray(0x2000000)
        for offset, word in module.ROM_WORDS.items():
            cls.rom[offset:offset+4] = word.to_bytes(4, "big")

    def test_split_known_symbols(self):
        with patch.object(module.hashlib, "sha1") as fake_hash:
            fake_hash.return_value.hexdigest.return_value = module.SHA1
            result, counts = module.refine(SYMBOLS, self.rom)
        self.assertEqual(counts["original_function_count"], 1)
        self.assertEqual(counts["revised_function_count"], 2)
        self.assertIn('"send_mesg"', result)
        self.assertIn('"handle_CpU"', result)

    def test_unexpected_rom_hash_fails(self):
        with self.assertRaisesRegex(ValueError, "exact Japanese"):
            module.refine(SYMBOLS, self.rom)

    def test_exception_word_mismatch_fails(self):
        damaged = self.rom[:]
        damaged[0x4A2B8] ^= 1
        with patch.object(module.hashlib, "sha1") as fake_hash:
            fake_hash.return_value.hexdigest.return_value = module.SHA1
            with self.assertRaisesRegex(ValueError, "Unexpected libultra"):
                module.refine(SYMBOLS, damaged)

    def test_unexpected_source_function_fails(self):
        wrong = SYMBOLS.replace("size = 0xE8", "size = 0xD8")
        with patch.object(module.hashlib, "sha1") as fake_hash:
            fake_hash.return_value.hexdigest.return_value = module.SHA1
            with self.assertRaisesRegex(ValueError, "generic Japanese"):
                module.refine(wrong, self.rom)


if __name__ == "__main__":
    unittest.main()
