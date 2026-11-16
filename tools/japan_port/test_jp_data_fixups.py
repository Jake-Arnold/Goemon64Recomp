"""ROM-free tests for Japanese overlay 56 native data pointer fixups."""
import unittest

try:
    from .jp_data_fixups import (
        SITE_TARGETS, ROM_DATA_START, ROM_START, ROM_SIZE,
        inject, hook_text, validate_rom
    )
except ImportError:
    from jp_data_fixups import (
        SITE_TARGETS, ROM_DATA_START, ROM_START, ROM_SIZE,
        inject, hook_text, validate_rom
    )

SOURCE = """// Generated Japanese N64Recomp source with callback relocation.
static void jp_relocate_task_callbacks(uint8_t* rdram, recomp_context* ctx, gpr task) {
    uint32_t file_id = 56;
    uint32_t start = 0x7174A0u, end = 0x71B3C0u, base = 0x803D6000u;
    if (end <= start || end > 0x02000000u) return;
}
RECOMP_FUNC void func_800143AC_14FAC(uint8_t* rdram, recomp_context* ctx) {
    jp_relocate_task_callbacks(rdram, ctx, jp_task);
}
"""


class TestJapanOverlay56DataFixups(unittest.TestCase):
    def test_exactly_two_tables_and_fifteen_entries(self):
        self.assertEqual(len(SITE_TARGETS), 15)
        self.assertEqual(SITE_TARGETS[0], (0x3AB0, 0x39F0))
        self.assertEqual(SITE_TARGETS[8], (0x3AD0, 0x3AA4))
        self.assertEqual(SITE_TARGETS[9], (0x3ECC, 0x244C))
        self.assertEqual(SITE_TARGETS[-1], (0x3EE0, 0x2600))
        self.assertEqual(len({site for site, _ in SITE_TARGETS}), 15)
        for site, target in SITE_TARGETS:
            self.assertEqual(site % 4, 0)
            self.assertGreaterEqual(site, ROM_DATA_START - ROM_START)
            self.assertLess(site, ROM_SIZE)
            self.assertLess(target, ROM_SIZE)

    def test_injection_has_single_call_and_all_or_nothing_guard(self):
        updated = inject(SOURCE)
        self.assertEqual(
            updated.count("jp_relocate_file_56_data(rdram, base);"), 1
        )
        self.assertIn("if (current != original && current != relocated) return;", updated)
        self.assertIn("if (file_id == 56u && start == 0x007174A0u", updated)
        self.assertIn("const gpr dst = (gpr)(int64_t)(int32_t)base;", updated)
        self.assertIn("base <= 0x80800000u - 0x3F20u", updated)

    def test_rejects_double_application(self):
        with self.assertRaisesRegex(ValueError, "already applied"):
            inject(inject(SOURCE))

    def test_requires_known_generated_c_anchors(self):
        with self.assertRaisesRegex(ValueError, "anchors missing"):
            inject(SOURCE.replace("jp_relocate_task_callbacks(", "unknown_callback("))

    def test_requires_same_rom_hash(self):
        with self.assertRaisesRegex(ValueError, "Wrong Japanese"):
            validate_rom(bytes(0x100))

    def test_uses_only_source_metadata_not_game_bytes(self):
        helper = hook_text()
        self.assertEqual(helper.count("{0x"), 15)


if __name__ == "__main__":
    unittest.main()
