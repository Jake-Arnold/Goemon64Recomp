"""All-assembly extraction must remain isolated and exclude data annotations."""
import tempfile
import unittest
from pathlib import Path

try:
    from .fullasm_config import convert, EXPECTED_SHA1, GENERATED_ROOT
    from .candidate_symbols import parse_functions
except ImportError:
    from fullasm_config import convert, EXPECTED_SHA1, GENERATED_ROOT
    from candidate_symbols import parse_functions


class FullAssemblyExtractionTests(unittest.TestCase):
    def fixture(self):
        return {
            "sha1": EXPECTED_SHA1,
            "options": {"asm_path": "asm/japan_0", "src_path": "src"},
            "segments": [
                {"name": "main", "type": "code", "start": 0x1000,
                 "vram": 0x80000400,
                 "subsegments": [[0x1000, "c", "main_1000"],
                                 [0x1040, "asm", "main_1040"]]},
                {"name": "data", "type": "bin", "start": 0x1080},
            ],
        }

    def test_c_sections_converted_without_mutating_original(self):
        original = self.fixture()
        result, count = convert(original)
        self.assertEqual(count, 1)
        self.assertEqual(original["segments"][0]["subsegments"][0][1], "c")
        self.assertEqual(result["segments"][0]["subsegments"][0][1], "asm")
        self.assertEqual(result["segments"][0]["subsegments"][1][1], "asm")
        self.assertEqual(result["options"]["asm_path"], GENERATED_ROOT + "/asm")
        self.assertEqual(original["options"]["asm_path"], "asm/japan_0")

    def test_other_rom_revision_rejected(self):
        original = self.fixture()
        original["sha1"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "Japanese"):
            convert(original)

    def test_no_c_sections_rejected(self):
        original = self.fixture()
        original["segments"][0]["subsegments"][0][1] = "asm"
        with self.assertRaisesRegex(ValueError, "No C-designated"):
            convert(original)

    def test_function_inventory_excludes_data_file(self):
        with tempfile.TemporaryDirectory() as directory:
            asm = Path(directory)
            (asm / "main_1000.s").write_text(
                "nonmatching func_80000400_1000, 0x38\n"
                "/* 1000 80000400 00000000 */ nop\n"
            )
            (asm / "main_1000.data.s").write_text(
                "nonmatching D_80000410_1010, 0x8\n"
                "/* 1010 80000410 00000000 */ nop\n"
            )
            candidates = parse_functions(asm, [{
                "name": "entry", "start": 0x1000, "end": 0x1050,
                "vram": 0x80000400,
            }])
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["name"], "recomp_entrypoint")


if __name__ == "__main__":
    unittest.main()
