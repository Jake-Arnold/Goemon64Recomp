"""Synthetic ROM and assembly checks for the region-safe relocation scanner."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

try:
    from . import reloc_candidates as scanner
    from .reloc_candidates import parse, symbol_address
except ImportError:
    import reloc_candidates as scanner
    from reloc_candidates import parse, symbol_address


class CandidateRelocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.asm = self.base / "asm"
        self.asm.mkdir()
        words = [0x3C040800, 0x24840020, 0x0E00000C] + [0] * 13
        self.rom = self.base / "rom.z64"
        self.rom.write_bytes(b"".join(word.to_bytes(4, "big") for word in words))
        self.splat = self.base / "splat.yaml"
        self.splat.write_text(yaml.safe_dump({
            "sha1": hashlib.sha1(self.rom.read_bytes()).hexdigest(),
            "segments": [
                {"type": "code", "name": "file_24", "start": 0,
                 "vram": 0x08000000, "overlay": True,
                 "subsegments": [[0, "asm", "file_24"]]},
                {"type": "bin", "name": "end", "start": 64},
            ],
        }))
        self.asm_file = self.asm / "file_24.s"
        self.asm_file.write_text(
            "/* 000 08000000 3C040800 */ lui $a0, %hi(func_08000020_20)\n"
            "/* 004 08000004 24840020 */ addiu $a0, $a0, %lo(func_08000020_20)\n"
            "/* 008 08000008 0E00000C */ jal func_08000030_30\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_records(self):
        result = parse(self.asm, self.splat, self.rom)
        self.assertEqual(result["candidate_relocations"], 3)
        self.assertEqual(result["types"]["R_MIPS_HI16"], 1)
        self.assertEqual(result["types"]["R_MIPS_LO16"], 1)
        self.assertEqual(result["types"]["R_MIPS_26"], 1)
        self.assertEqual(result["sections_with_candidates"], 1)

    def test_graphics_pair_excludes_only_named_sites_for_the_rom(self):
        data = bytearray(self.rom.read_bytes())
        data[12:20] = data[:8]
        self.rom.write_bytes(data)
        digest = hashlib.sha1(data).hexdigest()
        cfg = yaml.safe_load(self.splat.read_text())
        cfg["sha1"] = digest
        self.splat.write_text(yaml.safe_dump(cfg))
        self.asm_file.write_text(self.asm_file.read_text() +
            "/* 00C 0800000C 3C040800 */ lui $a0, %hi(func_08000020_20)\n"
            "/* 010 08000010 24840020 */ addiu $a0, $a0, %lo(func_08000020_20)\n")
        registry = self.base / "segmented_graphics_exclusions.json"
        exclusions = [
            dict(section="file_24", type=kind, vram=site, target_vram="0x08000020")
            for kind, site in [("R_MIPS_HI16", "0x08000000"), ("R_MIPS_LO16", "0x08000004")]
        ]
        with patch.object(scanner, "__file__", str(self.base / "reloc_candidates.py")):
            registry.write_text(json.dumps({"rom_sha1_to_exclusions": {"other": exclusions}}))
            self.assertEqual(parse(self.asm, self.splat, self.rom)["candidate_relocations"], 5)
            registry.write_text(json.dumps({"rom_sha1_to_exclusions": {digest: exclusions}}))
            result = parse(self.asm, self.splat, self.rom)
        self.assertEqual([row["vram"] for row in result["relocations"]["file_24"]],
                         ["0x08000008", "0x0800000C", "0x08000010"])

    def test_wrong_rom_hash_rejected(self):
        self.rom.write_bytes(self.rom.read_bytes()[:-4] + bytes([1, 2, 3, 4]))
        with self.assertRaisesRegex(ValueError, "SHA-1"):
            parse(self.asm, self.splat, self.rom)

    def test_bad_instruction_annotation_rejected(self):
        self.asm_file.write_text(self.asm_file.read_text().replace("24840020", "24840024"))
        with self.assertRaisesRegex(ValueError, "Assembly/ROM"):
            parse(self.asm, self.splat, self.rom)

    def test_unpaired_target_rejected(self):
        self.asm_file.write_text(self.asm_file.read_text().splitlines()[0] + "\n")
        with self.assertRaisesRegex(ValueError, "unpaired"):
            parse(self.asm, self.splat, self.rom)

    def test_symbol_addends(self):
        self.assertEqual(symbol_address("func_08001230_6C0 + 0x8"), 0x08001238)
        self.assertEqual(symbol_address("D_08001230_6C0 - 4"), 0x0800122C)
        self.assertIsNone(symbol_address("func_80001230_ABCD"))

    def test_overlay_bss_reference_is_included(self):
        import hashlib
        import yaml

        data = self.rom.read_bytes()
        data = data[:4] + (0x24840048).to_bytes(4, 'big') + data[8:]
        self.rom.write_bytes(data)

        cfg = yaml.safe_load(self.splat.read_text())
        cfg['sha1'] = hashlib.sha1(data).hexdigest()
        cfg['segments'][0]['bss_size'] = 0x20
        self.splat.write_text(yaml.safe_dump(cfg))
        self.asm_file.write_text(
            self.asm_file.read_text().replace(
                'func_08000020_20', 'func_08000048_48'
            ).replace('24840020', '24840048')
        )
        result = parse(self.asm, self.splat, self.rom)
        self.assertEqual(result['candidate_relocations'], 3)
        self.assertEqual(result['relocations']['file_24'][0]['target_vram'],
                         '0x08000048')


if __name__ == "__main__":
    unittest.main()
