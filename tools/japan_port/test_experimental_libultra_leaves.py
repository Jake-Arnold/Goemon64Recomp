"""Synthetic metadata tests; no ROM or generated game instructions required."""
import tomllib
import unittest

try:
    from .experimental_libultra_leaves import LEAVES, NATIVE_LINK_ALIASES, apply
except ImportError:
    from experimental_libultra_leaves import LEAVES, NATIVE_LINK_ALIASES, apply


def fixture() -> str:
    lines = [
        "[[section]]",
        'name = ".entry"',
        "functions = []",
        "",
        "[[section]]",
        'name = ".main"',
        "functions = [",
    ]
    for name, (vram, size) in LEAVES.items():
        lines.append(
            f'    {{ name = "{name}", vram = 0x{vram:08X}, size = 0x{size:X} }},'
        )
    lines.append("]")
    return "\n".join(lines) + "\n"


class LibultraLeafTests(unittest.TestCase):
    def test_three_original_rom_routines_are_aliased(self):
        result, stats = apply(fixture())
        self.assertEqual(stats["input_functions"], 3)
        self.assertEqual(stats["output_functions"], 3)
        names = {
            f["name"]
            for section in tomllib.loads(result)["section"]
            for f in section["functions"]
        }
        self.assertEqual(names, {"jp_impl_" + key for key in LEAVES})

    def test_native_link_uses_only_the_two_missing_host_symbols(self):
        result, stats = apply(fixture(), aliases=NATIVE_LINK_ALIASES)
        names = {
            f["name"]
            for section in tomllib.loads(result)["section"]
            for f in section["functions"]
        }
        self.assertEqual(names, {
            "jp_osCheckId_mips", "jp_osPfsRWInode_mips", "__osPfsSelectBank",
        })
        self.assertEqual(stats["output_functions"], stats["input_functions"])

    def test_wrong_rom_address_is_rejected(self):
        first = next(iter(LEAVES))
        original = f'vram = 0x{LEAVES[first][0]:08X}'
        with self.assertRaisesRegex(ValueError, "function layout"):
            apply(fixture().replace(original, "vram = 0x80000000", 1))

    def test_wrong_function_length_is_rejected(self):
        name = next(iter(LEAVES))
        old = f'name = "{name}", vram = 0x{LEAVES[name][0]:08X}, size = 0x{LEAVES[name][1]:X}'
        with self.assertRaisesRegex(ValueError, "function layout"):
            apply(fixture().replace(old, old.replace(f"size = 0x{LEAVES[name][1]:X}", "size = 0x4"), 1))

    def test_reapply_fails_closed(self):
        result, _ = apply(fixture())
        with self.assertRaisesRegex(ValueError, "function layout"):
            apply(result)

    def test_missing_main_rejected(self):
        with self.assertRaisesRegex(ValueError, "main section"):
            apply(fixture().replace('name = ".main"', 'name = ".data"'))

    def test_duplicate_symbols_rejected(self):
        source = fixture()
        line = f'    {{ name = "{next(iter(LEAVES))}", vram = 0x{next(iter(LEAVES.values()))[0]:08X}, size = 0x{next(iter(LEAVES.values()))[1]:X} }},'
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            apply(source.replace(line, line + "\n" + line))


if __name__ == "__main__":
    unittest.main()
