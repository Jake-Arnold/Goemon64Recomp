"""ROM-free regression checks for native Japanese overlay hook generation."""
import unittest

try:
    from .jp_loader_hook import inject, check_rom
except ImportError:
    from jp_loader_hook import inject, check_rom

SOURCE = (
    '#include "recomp.h"\n'
    'RECOMP_FUNC void func_80001BA0_27A0(uint8_t* rdram, recomp_context* ctx) {\n'
    '    TRACE_ENTRY()\n}\n'
)


class JapanLoaderHookTests(unittest.TestCase):
    def test_injects_exact_function(self):
        patched = inject(SOURCE)
        self.assertIn("jp_native_register_file_overlay(rdram, ctx);", patched)
        self.assertEqual(patched.count("jp_native_register_file_overlay(rdram, ctx);"), 1)
        self.assertIn("(gpr)(int64_t)(int32_t)raw_addr", patched)

    def test_rejects_second_injection(self):
        with self.assertRaisesRegex(ValueError, "already present"):
            inject(inject(SOURCE))

    def test_rejects_missing_loader(self):
        with self.assertRaisesRegex(ValueError, "Missing unique"):
            inject('#include "recomp.h"\n')

    def test_rejects_wrong_rom(self):
        with self.assertRaisesRegex(ValueError, "exact Japanese"):
            check_rom(bytes(32))


if __name__ == "__main__":
    unittest.main()
