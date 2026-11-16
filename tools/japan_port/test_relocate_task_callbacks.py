"""ROM-free guards for Japanese task callback relocation code generation."""
import unittest

try:
    from .relocate_task_callbacks import inject, validate_rom, HOOK_NAME
except ImportError:
    from relocate_task_callbacks import inject, validate_rom, HOOK_NAME

SOURCE = """#include "recomp.h"
#include "funcs.h"
RECOMP_FUNC void func_800143AC_14FAC(uint8_t* rdram, recomp_context* ctx) {
    TRACE_ENTRY()
    // 0x800143AC: addiu       $sp, $sp, -0x18
    // 0x800143B8: jal         0x80001E50
    func_80001E50_2A50(rdram, ctx);
        goto after_0;
after_0:
    // 0x800143C0: lw          $ra, 0x14($sp)
    TRACE_RETURN()
}
RECOMP_FUNC void later(uint8_t* rdram, recomp_context* ctx) {
    TRACE_ENTRY()
}
"""


class JapanTaskCallbackTests(unittest.TestCase):
    def test_injects_exactly_one_guarded_translation(self):
        result = inject(SOURCE)
        self.assertEqual(result.count("jp_relocate_task_callbacks(rdram, ctx, jp_task);"), 1)
        self.assertIn("const gpr jp_task = ctx->r4;", result)
        self.assertIn("func_80013D54_14954(rdram, ctx);", result)
        self.assertIn("base + offset >= 0x80800000u", result)
        self.assertIn("const recomp_context preserved = *ctx;", result)

    def test_refuses_duplicate_hook(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            inject(inject(SOURCE))

    def test_wrong_task_function_fails(self):
        with self.assertRaisesRegex(ValueError, "task setup"):
            inject(SOURCE.replace("func_800143AC_14FAC", "unknown_800143AC"))

    def test_missing_callback_setup_fails(self):
        with self.assertRaisesRegex(ValueError, "TLB setup"):
            inject(SOURCE.replace("func_80001E50_2A50", "not_the_tlb_setup"))

    def test_non_japanese_rom_rejected(self):
        with self.assertRaisesRegex(ValueError, "Japanese"):
            validate_rom(bytes(64))


if __name__ == "__main__":
    unittest.main()
