"""Verify all five JP native hook validators and atomic generated-C writes.

All ROM validators remain mandatory in production. Unit fixtures only
substitute their checks to exercise composition without redistributing ROMs.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

try:
    from . import (
        prepare_japan_recomp, jp_loader_hook, relocate_task_callbacks,
        jp_data_fixups, jp_file80_data_fixups, jp_sasuke_bomb_camera_fix,
    )
except ImportError:
    import prepare_japan_recomp
    import jp_loader_hook
    import relocate_task_callbacks
    import jp_data_fixups
    import jp_file80_data_fixups
    import jp_sasuke_bomb_camera_fix


class TestNativeHookPreparation(TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.rom = self.directory / "japan-decompressed.z64"
        self.rom.write_bytes(b"synthetic test input, not game bytes")
        self.generated = self.directory / "RecompiledFuncs"
        self.generated.mkdir()
        self.sources = {
            "funcs_0.c": "loader-original\n",
            "funcs_8.c": "callback-original\n",
            "funcs_32.c": "sasuke-original\n",
        }
        for filename, original in self.sources.items():
            (self.generated / filename).write_text(original)

    def assert_no_partial_modifications(self):
        for filename, original in self.sources.items():
            self.assertEqual(
                (self.generated / filename).read_text(),
                original,
                f"Atomicity violated for {filename}",
            )

    def test_all_five_hooks_written_only_after_validation(self):
        with (
            patch.object(jp_loader_hook, "check_rom") as loader_check,
            patch.object(relocate_task_callbacks, "validate_rom") as callback_check,
            patch.object(jp_data_fixups, "validate_rom") as data_check,
            patch.object(jp_file80_data_fixups, "validate_rom") as file80_check,
            patch.object(jp_sasuke_bomb_camera_fix, "validate_rom") as sasuke_check,
            patch.object(jp_loader_hook, "inject", side_effect=lambda s: s + "loader-hook\n"),
            patch.object(relocate_task_callbacks, "inject", side_effect=lambda s: s + "callback-hook\n"),
            patch.object(jp_data_fixups, "inject", side_effect=lambda s: s + "data-fixups\n"),
            patch.object(jp_file80_data_fixups, "inject", side_effect=lambda s: s + "file80-fixups\n"),
            patch.object(jp_sasuke_bomb_camera_fix, "inject", side_effect=lambda s: s + "sasuke-fix\n"),
        ):
            result = prepare_japan_recomp.apply_verified_native_hooks(
                self.generated, self.rom
            )
        for check in (loader_check, callback_check, data_check,
                      file80_check, sasuke_check):
            check.assert_called_once()
        self.assertIn("loader-hook", (self.generated / "funcs_0.c").read_text())
        patched_8 = (self.generated / "funcs_8.c").read_text()
        for marker in ("callback-hook", "data-fixups", "file80-fixups"):
            self.assertIn(marker, patched_8)
        self.assertIn("sasuke-fix", (self.generated / "funcs_32.c").read_text())
        self.assertEqual(result["native_overlay_56_data_fixups"], 15)
        self.assertEqual(result["native_overlay_80_data_fixups"], 6)
        self.assertEqual(result["native_sasuke_bomb_camera"], "0x802119E0")
        self.assertEqual(len(result["patched_generated_c_units"]), 3)

    def test_second_patch_refusal_preserves_every_source(self):
        with (
            patch.object(jp_loader_hook, "check_rom"),
            patch.object(relocate_task_callbacks, "validate_rom"),
            patch.object(jp_data_fixups, "validate_rom"),
            patch.object(jp_file80_data_fixups, "validate_rom"),
            patch.object(jp_sasuke_bomb_camera_fix, "validate_rom"),
            patch.object(jp_loader_hook, "inject", side_effect=lambda s: s + "loader-hook\n"),
            patch.object(relocate_task_callbacks, "inject", side_effect=ValueError("incompatible code")),
        ):
            with self.assertRaisesRegex(ValueError, "incompatible"):
                prepare_japan_recomp.apply_verified_native_hooks(
                    self.generated, self.rom
                )
        self.assert_no_partial_modifications()

    def test_third_patch_failure_preserves_every_source(self):
        with (
            patch.object(jp_loader_hook, "check_rom"),
            patch.object(relocate_task_callbacks, "validate_rom"),
            patch.object(jp_data_fixups, "validate_rom"),
            patch.object(jp_file80_data_fixups, "validate_rom"),
            patch.object(jp_sasuke_bomb_camera_fix, "validate_rom"),
            patch.object(jp_loader_hook, "inject", side_effect=lambda s: s + "loader-hook\n"),
            patch.object(relocate_task_callbacks, "inject", side_effect=lambda s: s + "callback-hook\n"),
            patch.object(jp_data_fixups, "inject", side_effect=ValueError("bad pointer table")),
        ):
            with self.assertRaisesRegex(ValueError, "bad pointer table"):
                prepare_japan_recomp.apply_verified_native_hooks(
                    self.generated, self.rom
                )
        self.assert_no_partial_modifications()

    def test_fourth_patch_failure_does_not_write_prior_patches(self):
        with (
            patch.object(jp_loader_hook, "check_rom"),
            patch.object(relocate_task_callbacks, "validate_rom"),
            patch.object(jp_data_fixups, "validate_rom"),
            patch.object(jp_file80_data_fixups, "validate_rom"),
            patch.object(jp_sasuke_bomb_camera_fix, "validate_rom"),
            patch.object(jp_loader_hook, "inject", side_effect=lambda s: s + "loader-hook\n"),
            patch.object(relocate_task_callbacks, "inject", side_effect=lambda s: s + "callback-hook\n"),
            patch.object(jp_data_fixups, "inject", side_effect=lambda s: s + "data-fixups\n"),
            patch.object(jp_file80_data_fixups, "inject", side_effect=ValueError("file80 incompatible")),
        ):
            with self.assertRaisesRegex(ValueError, "file80 incompatible"):
                prepare_japan_recomp.apply_verified_native_hooks(
                    self.generated, self.rom
                )
        self.assert_no_partial_modifications()

    def test_fifth_patch_failure_does_not_write_prior_patches(self):
        with (
            patch.object(jp_loader_hook, "check_rom"),
            patch.object(relocate_task_callbacks, "validate_rom"),
            patch.object(jp_data_fixups, "validate_rom"),
            patch.object(jp_file80_data_fixups, "validate_rom"),
            patch.object(jp_sasuke_bomb_camera_fix, "validate_rom"),
            patch.object(jp_loader_hook, "inject", side_effect=lambda s: s + "loader-hook\n"),
            patch.object(relocate_task_callbacks, "inject", side_effect=lambda s: s + "callback-hook\n"),
            patch.object(jp_data_fixups, "inject", side_effect=lambda s: s + "data-fixups\n"),
            patch.object(jp_file80_data_fixups, "inject", side_effect=lambda s: s + "file80-fixups\n"),
            patch.object(jp_sasuke_bomb_camera_fix, "inject", side_effect=ValueError("sasuke incompatible")),
        ):
            with self.assertRaisesRegex(ValueError, "sasuke incompatible"):
                prepare_japan_recomp.apply_verified_native_hooks(
                    self.generated, self.rom
                )
        self.assert_no_partial_modifications()

    def test_rom_gate_fails_before_any_modification(self):
        with (
            patch.object(jp_loader_hook, "check_rom", side_effect=ValueError("wrong ROM")),
            patch.object(relocate_task_callbacks, "validate_rom") as callback_check,
            patch.object(jp_data_fixups, "validate_rom") as data_check,
            patch.object(jp_file80_data_fixups, "validate_rom") as file80_check,
            patch.object(jp_sasuke_bomb_camera_fix, "validate_rom") as sasuke_check,
        ):
            with self.assertRaisesRegex(ValueError, "wrong ROM"):
                prepare_japan_recomp.apply_verified_native_hooks(
                    self.generated, self.rom
                )
        for later_validator in (callback_check, data_check, file80_check, sasuke_check):
            later_validator.assert_not_called()
        self.assert_no_partial_modifications()
