"""Unit tests for byte-order conversion and strict version gates."""
import tempfile
import unittest
from pathlib import Path

try:
    from . import rom
except ImportError:
    import rom


class RomTests(unittest.TestCase):
    def setUp(self):
        self.data = rom.NORMAL_MAGIC + bytes(range(4, 64))

    def test_z64(self):
        self.assertEqual(rom.normalize(self.data), (self.data, "z64"))

    def test_v64(self):
        data = bytearray(self.data)
        data[::2], data[1::2] = self.data[1::2], self.data[::2]
        self.assertEqual(rom.normalize(data), (self.data, "v64"))

    def test_n64(self):
        data = b"".join(self.data[i:i + 4][::-1] for i in range(0, len(self.data), 4))
        self.assertEqual(rom.normalize(data), (self.data, "n64"))

    def test_unknown_magic_rejected(self):
        with self.assertRaises(rom.RomError):
            rom.normalize(b"none" + self.data[4:])

    def test_wrong_length_rejected(self):
        with self.assertRaises(rom.RomError):
            rom.normalize(self.data + b"x")

    def test_bad_hash_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "fake.z64"
            file.write_bytes(self.data)
            with self.assertRaises(rom.RomError):
                rom.checked(file, "0" * 40, len(self.data))


if __name__ == "__main__":
    unittest.main()
