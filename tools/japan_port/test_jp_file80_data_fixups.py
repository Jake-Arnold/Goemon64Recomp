"""ROM-free source-contract tests for Japanese file 80 data fixups."""
import unittest

try:
    from .jp_file80_data_fixups import (
        FILE_ID, ROM_START, ROM_END, ROM_DATA_START, ROM_SIZE, SITE_TARGETS,
        hook_text, inject, validate_rom,
    )
except ImportError:
    from jp_file80_data_fixups import (
        FILE_ID, ROM_START, ROM_END, ROM_DATA_START, ROM_SIZE, SITE_TARGETS,
        hook_text, inject, validate_rom,
    )


SOURCE = """// Private generated C already contains verified JP callback and file56 hooks.
static void jp_relocate_file_56_data(uint8_t* rdram, uint32_t base) {}
static void jp_relocate_task_callbacks(uint8_t* rdram, recomp_context* ctx, gpr task) {
    uint32_t file_id = 56u, start = 0x7174A0u, end = 0x71B3C0u, base = 0x803D6000u;
    if (file_id == 56u && start == 0x007174A0u && end == 0x0071B3C0u &&
        base <= 0x80800000u - 0x3F20u) {
        jp_relocate_file_56_data(rdram, base);
    }
}
RECOMP_FUNC void func_800143AC_14FAC(uint8_t* rdram, recomp_context* ctx) {
    jp_relocate_task_callbacks(rdram, ctx, jp_task);
}
"""


class TestJapanFile80Fixups(unittest.TestCase):
    def test_six_exact_rom_sites(self):
        self.assertEqual(FILE_ID, 80)
        self.assertEqual((ROM_START, ROM_END, ROM_DATA_START), (0x741660, 0x742270, 0x741F50))
        self.assertEqual(ROM_SIZE, 0x0C10)
        self.assertEqual(SITE_TARGETS, (
            (0xB3C, 0x8F0), (0xB40, 0x920), (0xB44, 0x974),
            (0xB48, 0x9B0), (0xB4C, 0xA28), (0xB50, 0xA94)
        ))
        self.assertEqual(len(set(SITE_TARGETS)), 6)
        for site, target in SITE_TARGETS:
            self.assertEqual(site % 4, 0)
            self.assertGreaterEqual(site, ROM_DATA_START - ROM_START)
            self.assertLess(site, ROM_SIZE)
            self.assertGreaterEqual(target, ROM_DATA_START - ROM_START)
            self.assertLess(target, ROM_SIZE)

    def test_all_or_nothing_live_words(self):
        result = inject(SOURCE)
        self.assertIn('if (current != original && current != relocated) return;', result)
        self.assertIn('if (current == 0x08000000u + pointers[i].target)', result)
        self.assertIn('MEM_W(pointers[i].site, dst) = base + pointers[i].target;', result)
        self.assertIn('const gpr dst = (gpr)(int64_t)(int32_t)base;', result)
        self.assertEqual(result.count('jp_relocate_file_80_data(rdram, base);'), 1)
        self.assertIn('file_id == 80u && start == 0x00741660u && end == 0x00742270u', result)
        self.assertIn('base <= 0x80800000u - 0x0C10u', result)
        self.assertIn('jp_relocate_file_56_data(rdram, base);', result)
        self.assertEqual(hook_text().count('{0x0B'), 6)

    def test_rejects_double_injection(self):
        with self.assertRaisesRegex(ValueError, 'already applied'):
            inject(inject(SOURCE))

    def test_requires_prior_verified_hooks(self):
        with self.assertRaisesRegex(ValueError, 'Missing or ambiguous'):
            inject('static void jp_relocate_task_callbacks() {}')
        with self.assertRaisesRegex(ValueError, 'Missing Japanese task callback'):
            inject(SOURCE.replace('jp_relocate_task_callbacks(rdram, ctx, jp_task);', 'missing();'))

    def test_requires_exact_rom_sha(self):
        with self.assertRaisesRegex(ValueError, 'Wrong Japanese'):
            validate_rom(bytes(0x2000000))

    def test_preserves_file56_hook_and_inserts_file80_after(self):
        result = inject(SOURCE)
        self.assertLess(
            result.index('jp_relocate_file_56_data(rdram, base);'),
            result.index('jp_relocate_file_80_data(rdram, base);')
        )


if __name__ == '__main__':
    unittest.main()
