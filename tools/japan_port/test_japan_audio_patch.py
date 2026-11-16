"""ROM-free regression for the Japanese signed audio-buffer correction."""
import tomllib
import unittest
from pathlib import Path


class JapanAudioPatchTests(unittest.TestCase):
    def test_exact_instruction_override(self):
        root = Path(__file__).resolve().parents[2]
        config = tomllib.loads((root / "mnsg.japan.toml").read_text())
        self.assertEqual(config["input"]["entrypoint"], 0x80000400)
        self.assertEqual(config["patches"]["stubs"], [])
        patches = config["patches"]["instruction"]
        self.assertEqual(len(patches), 1)
        self.assertEqual(patches[0], {
            "func": "func_80037E80_38A80",
            "vram": 0x80037F00,
            "value": 0x00E3082A,
        })


if __name__ == "__main__":
    unittest.main()
