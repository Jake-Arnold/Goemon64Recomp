"""ROM-free checks for the USA/JP audio RSP config translation."""
import tomllib
import unittest

try:
    from .rsp_config import render_config, verify_roms, JP_OFFSET, TEXT_SIZE
except ImportError:
    from rsp_config import render_config, verify_roms, JP_OFFSET, TEXT_SIZE


def original():
    return {
        "text_offset": 0x546B0,
        "text_size": 0xE20,
        "text_address": 0x04001080,
        "output_function_name": "aspMain",
        "extra_indirect_branch_targets": [
            0x1118, 0x1470, 0x11DC, 0x1B38,
            0x1214, 0x187C, 0x1254, 0x12D0,
            0x12EC, 0x1328, 0x140C, 0x1294,
            0x1E24, 0x138C, 0x170C, 0x144C,
        ],
    }


class RspConfigTests(unittest.TestCase):
    def test_rebases_only_text_offset_and_output(self):
        from pathlib import Path
        rendered = render_config(original(), Path("/tmp/jp.z64"), Path("/tmp/rsp-jp.cpp"))
        data = tomllib.loads(rendered)
        self.assertEqual(data["text_offset"], JP_OFFSET)
        self.assertEqual(data["text_size"], TEXT_SIZE)
        self.assertEqual(data["rom_file_path"], "/tmp/jp.z64")
        self.assertEqual(data["output_file_path"], "/tmp/rsp-jp.cpp")
        self.assertEqual(data["extra_indirect_branch_targets"],
                         original()["extra_indirect_branch_targets"])

    def test_rejects_wrong_upstream_offset(self):
        from pathlib import Path
        config = original()
        config["text_offset"] = 0x54930
        with self.assertRaisesRegex(ValueError, "text_offset"):
            render_config(config, Path("/tmp/jp.z64"), Path("/tmp/out.cpp"))

    def test_rejects_unrecognised_indirect_targets(self):
        from pathlib import Path
        config = original()
        config["extra_indirect_branch_targets"] = [0x1118]
        with self.assertRaisesRegex(ValueError, "branch targets"):
            render_config(config, Path("/tmp/jp.z64"), Path("/tmp/out.cpp"))

    def test_unknown_rom_rejected(self):
        with self.assertRaisesRegex(ValueError, "USA decompressed"):
            verify_roms(bytes(64), bytes(64))


if __name__ == "__main__":
    unittest.main()
