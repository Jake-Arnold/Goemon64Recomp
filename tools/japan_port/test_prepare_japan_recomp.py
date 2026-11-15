"""Validate isolated Japanese N64Recomp config before optional trials."""
import tempfile
import unittest
from pathlib import Path

try:
    from .prepare_japan_recomp import validate_config, EXPECTED_TLB
except ImportError:
    from prepare_japan_recomp import validate_config, EXPECTED_TLB

TOML = '''[input]
entrypoint = 0x80000400
output_func_path = "build-generated/japan/RecompiledFuncs"
symbols_file_path = "build-generated/japan/japan-PROVISIONAL.syms.toml"
rom_file_path = "build-generated/japan/baserom.decompressed.z64"
relocatable_sections_path = "mnsg.overlays.txt"
'''


class JapaneseTrialConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root/'mnsg.japan.toml').write_text(TOML)
        (self.root/'mnsg.overlays.txt').write_text('\n'.join(EXPECTED_TLB)+'\n')
        self.sections = [{'name':name[1:]} for name in EXPECTED_TLB]

    def tearDown(self):
        self.temporary.cleanup()

    def test_correct_experimental_config(self):
        validate_config(self.root, self.sections)

    def test_usa_binary_must_not_be_reused(self):
        path = self.root/'mnsg.japan.toml'
        path.write_text(TOML.replace('japan/baserom.decompressed.z64','usa/baserom.decompressed.z64'))
        with self.assertRaisesRegex(ValueError,'config mismatch'):
            validate_config(self.root, self.sections)

    def test_invalid_overlay_list_rejected(self):
        (self.root/'mnsg.overlays.txt').write_text('.file_24\n')
        with self.assertRaisesRegex(ValueError,'overlay'):
            validate_config(self.root, self.sections)

    def test_missing_japan_overlay_rejected(self):
        with self.assertRaisesRegex(ValueError,'does not define'):
            validate_config(self.root, self.sections[:-1])


if __name__ == '__main__':
    unittest.main()
