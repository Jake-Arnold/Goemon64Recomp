"""Validate Japanese PC-runtime entrypoint symbol naming."""
import tomllib
import unittest

try:
    from .candidate_symbols import render
except ImportError:
    from candidate_symbols import render


class JapanEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.sections = [
            {"name": "entry", "start": 0x1000, "end": 0x1050, "vram": 0x80000400},
            {"name": "file_24", "start": 0x6AD000, "end": 0x6AD080,
             "vram": 0x08000000},
        ]
        self.functions = [
            {"section": "entry", "name": "func_80000400_1000",
             "rom": 0x1000, "vram": 0x80000400, "size": 0x38},
            {"section": "file_24", "name": "func_08000000_6AD000",
             "rom": 0x6AD000, "vram": 0x08000000, "size": 0x20},
        ]

    def test_entrypoint_is_named_for_native_runtime(self):
        source = tomllib.loads(render(self.sections, self.functions))
        self.assertEqual(source["section"][0]["functions"][0]["name"],
                         "recomp_entrypoint")
        self.assertEqual(source["section"][1]["functions"][0]["name"],
                         "func_08000000_6AD000")

    def test_wrong_entrypoint_address_fails_closed(self):
        functions = [dict(entry) for entry in self.functions]
        functions[0]["vram"] = 0x80000404
        with self.assertRaisesRegex(ValueError, "entrypoint"):
            render(self.sections, functions)

    def test_wrong_entrypoint_size_fails_closed(self):
        functions = [dict(entry) for entry in self.functions]
        functions[0]["size"] = 0x40
        with self.assertRaisesRegex(ValueError, "entrypoint"):
            render(self.sections, functions)


if __name__ == "__main__":
    unittest.main()
