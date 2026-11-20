"""Pure-metadata checks for Japan's isolated N64Recomp probe generator."""
import unittest

try:
    from .probe_config import OVERLAYS, inspect_symbol_map
except ImportError:
    from probe_config import OVERLAYS, inspect_symbol_map


def fixture():
    sections = [
        {"name": ".entry", "rom": 0x1000, "vram": 0x80000400,
         "size": 0x50, "functions": [
             {"name": "recomp_entrypoint", "vram": 0x80000400, "size": 0x38}
         ]},
        {"name": ".main", "rom": 0x1050, "vram": 0x80000450,
         "size": 0x833C0,
         "functions": [{"name": "synthetic"}] * 7350},
    ]
    for i in range(11, 81):
        sections.append({
            "name": f".file_{i}",
            "vram": 0x08000000 if i >= 24 else 0x801CB460,
            "rom": 0x580000 + (i - 11) * 0x100,
            "size": 0x100, "functions": [],
            "relocs": [{"type": "R_MIPS_26"}] * 6426 if i == 24 else [],
        })
    return {"section": sections}


class ProbeMetadataTests(unittest.TestCase):
    def test_accepted_pinned_layout(self):
        report = inspect_symbol_map(fixture())
        self.assertEqual(report["sections"], 72)
        self.assertEqual(report["relocatable_overlays"], 57)
        self.assertEqual(report["functions"], 7351)
        self.assertEqual(report["relocations"], 6426)

    def test_bad_entrypoint_name(self):
        data = fixture()
        data["section"][0]["functions"][0]["name"] = "func_80000400_1000"
        with self.assertRaisesRegex(ValueError, "entrypoint"):
            inspect_symbol_map(data)

    def test_missing_overlay(self):
        data = fixture()
        data["section"][-1]["name"] = ".unknown"
        with self.assertRaisesRegex(ValueError, "file_24 through file_80"):
            inspect_symbol_map(data)

    def test_missing_empty_relocation_table_rejected(self):
        data = fixture()
        # file_52 has zero relocations but MUST have the relocs key.
        file_52 = next(s for s in data['section'] if s['name'] == '.file_52')
        del file_52['relocs']
        with self.assertRaisesRegex(ValueError, 'relocs array'):
            inspect_symbol_map(data)

    def test_old_metadata_rejected(self):
        data = fixture()
        data["section"][-1]["functions"] = []
        data["section"][15]["relocs"] = [{"type": "R_MIPS_26"}] * 6194
        data["section"][15 + 0]["name"] = data["section"][15]["name"]
        data["section"][15 + 0]["vram"] = 0x08000000
        # still 6426 in file_24; explicitly strip it too
        data["section"][15]["relocs"] = []
        with self.assertRaisesRegex(ValueError, "older candidate inventory"):
            inspect_symbol_map(data)


if __name__ == "__main__":
    unittest.main()
