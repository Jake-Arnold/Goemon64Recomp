"""Validate native JP loader+callback hook orchestration is atomic and guarded."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

try:
    from . import prepare_japan_recomp, jp_loader_hook, relocate_task_callbacks
except ImportError:
    import prepare_japan_recomp
    import jp_loader_hook
    import relocate_task_callbacks


class TestNativeHookPreparation(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.rom = self.directory / "japan-decompressed.z64"
        self.rom.write_bytes(b"synthetic test input, not game bytes")
        self.generated = self.directory / "RecompiledFuncs"
        self.generated.mkdir()
        (self.generated / "funcs_0.c").write_text("loader-original\n")
        (self.generated / "funcs_8.c").write_text("callback-original\n")

    def test_both_patch_outputs_written_after_validation(self):
        with (
            patch.object(jp_loader_hook, "check_rom") as loader_check,
            patch.object(relocate_task_callbacks, "validate_rom") as callback_check,
            patch.object(jp_loader_hook, "inject", side_effect=lambda s: s + "loader-hook\n"),
            patch.object(relocate_task_callbacks, "inject", side_effect=lambda s: s + "callback-hook\n"),
        ):
            result = prepare_japan_recomp.apply_verified_native_hooks(
                self.generated, self.rom
            )
        loader_check.assert_called_once()
        callback_check.assert_called_once()
        self.assertIn("loader-hook", (self.generated / "funcs_0.c").read_text())
        self.assertIn("callback-hook", (self.generated / "funcs_8.c").read_text())
        self.assertEqual(len(result["patched_generated_c_units"]), 2)

    def test_second_patch_refusal_preserves_first_source(self):
        with (
            patch.object(jp_loader_hook, "check_rom"),
            patch.object(relocate_task_callbacks, "validate_rom"),
            patch.object(jp_loader_hook, "inject", side_effect=lambda s: s + "loader-hook\n"),
            patch.object(relocate_task_callbacks, "inject", side_effect=ValueError("incompatible code")),
        ):
            with self.assertRaisesRegex(ValueError, "incompatible"):
                prepare_japan_recomp.apply_verified_native_hooks(
                    self.generated, self.rom
                )
        self.assertEqual((self.generated / "funcs_0.c").read_text(), "loader-original\n")
        self.assertEqual((self.generated / "funcs_8.c").read_text(), "callback-original\n")

    def test_rom_gate_fails_before_modifications(self):
        with (
            patch.object(jp_loader_hook, "check_rom", side_effect=ValueError("wrong ROM")),
            patch.object(relocate_task_callbacks, "validate_rom") as callback_check,
        ):
            with self.assertRaisesRegex(ValueError, "wrong ROM"):
                prepare_japan_recomp.apply_verified_native_hooks(self.generated, self.rom)
        callback_check.assert_not_called()
        self.assertEqual((self.generated / "funcs_0.c").read_text(), "loader-original\n")
        self.assertEqual((self.generated / "funcs_8.c").read_text(), "callback-original\n")
