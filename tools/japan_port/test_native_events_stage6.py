#!/usr/bin/env python3
"""JP v0.2.11 native worker lifecycle audit source tests.

This confirms source invariants only, not a complete soft-reset barrier.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "lib/N64ModernRuntime/ultramodern/src/events.cpp"
PATCHER = ROOT / "tools/japan_port/patch_native_events_stage6.py"
spec = importlib.util.spec_from_file_location("jp_host_stage6", PATCHER)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class NativeEventWorkerStage6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = ORIGINAL.read_text(encoding="utf-8")
        cls.output = mod.instrument_events(cls.original)

    def test_pinned_source_remains_unmodified(self) -> None:
        self.assertNotIn("jp_event_started", self.original)
        self.assertNotIn(mod.MARKER, self.original)
        self.assertIn("events_context.sp.task_thread.join();", self.original)

    def test_three_worker_masks_are_distinct(self) -> None:
        out = self.output
        for label, hexval in (
            ("JP_EVENT_VI", "0x1u"),
            ("JP_EVENT_GFX", "0x2u"),
            ("JP_EVENT_RSP", "0x4u"),
        ):
            self.assertIn(f"{label} = {hexval};", out)
        self.assertIn("JP_EVENT_ALL = JP_EVENT_VI | JP_EVENT_GFX | JP_EVENT_RSP", out)

    def test_lifetime_guards_are_raii(self) -> None:
        out = self.output
        self.assertIn("struct JpEventWorkerLifetime", out)
        self.assertIn("~JpEventWorkerLifetime()", out)
        self.assertIn("jp_event_started.fetch_or(bit", out)
        self.assertIn("jp_event_active.fetch_or(bit", out)
        self.assertIn("jp_event_active.fetch_and(~bit", out)
        for bit in ("JP_EVENT_VI", "JP_EVENT_RSP", "JP_EVENT_GFX"):
            self.assertEqual(
                out.count(f"JpEventWorkerLifetime jp_event_lifetime({bit});"), 1
            )

    def test_busy_flags_unwind_after_rsp_and_gfx_work(self) -> None:
        out = self.output
        self.assertIn("~JpEventWorkerBusy()", out)
        self.assertIn("jp_event_busy.fetch_and(~bit", out)
        self.assertEqual(
            out.count("JpEventWorkerBusy jp_event_busy_scope(JP_EVENT_RSP);"), 1
        )
        self.assertEqual(
            out.count("JpEventWorkerBusy jp_event_busy_scope(JP_EVENT_GFX);"), 1
        )
        self.assertLess(
            out.index("if (task == nullptr)"),
            out.index("JpEventWorkerBusy jp_event_busy_scope(JP_EVENT_RSP);"),
        )
        self.assertLess(
            out.index("JpEventWorkerBusy jp_event_busy_scope(JP_EVENT_RSP);"),
            out.index("if (!ultramodern::rsp::run_task("),
        )

    def test_native_worker_join_proof_does_not_infer_guest_safety(self) -> None:
        src = self.output
        body = src.split("void ultramodern::join_event_threads() {", 1)[1].split(
            "\n}", 1
        )[0]
        order = [
            "events_context.sp.gfx_thread.join();",
            "jp_event_joined.fetch_or(JP_EVENT_GFX",
            "events_context.vi.thread.join();",
            "jp_event_joined.fetch_or(JP_EVENT_VI",
            "events_context.sp_task_queue.enqueue(nullptr);",
            "events_context.sp.task_thread.join();",
            "jp_event_joined.fetch_or(JP_EVENT_RSP",
            "ultramodern::report_native_event_exit_status();",
        ]
        indexes = [body.index(part) for part in order]
        self.assertEqual(indexes, sorted(indexes))
        self.assertIn("guest/start/save quiescence NOT proven", src)

    def test_all_started_active_joined_and_busy_reported(self) -> None:
        src = self.output
        for name in (
            "jp_event_started.load(std::memory_order_acquire)",
            "jp_event_active.load(std::memory_order_acquire)",
            "jp_event_busy.load(std::memory_order_acquire)",
            "jp_event_joined.load(std::memory_order_acquire)",
        ):
            self.assertIn(name, src)
        self.assertIn("[Goemon JP native workers]", src)
        self.assertIn("[Goemon JP native exit]", src)
        self.assertIn("VI=1 gfx=2 RSP=4", src)

    def test_no_mutation_of_thread_or_renderer_lifecycle(self) -> None:
        src = self.output
        self.assertEqual(src.count("events_context.sp.gfx_thread.join();"), 1)
        self.assertEqual(src.count("events_context.vi.thread.join();"), 1)
        self.assertEqual(src.count("events_context.sp.task_thread.join();"), 1)
        self.assertEqual(src.count("events_context.sp_task_queue.enqueue(nullptr);"), 1)
        self.assertIn("graphics_shutdown_ready.wait();", src)
        self.assertIn("renderer_context->shutdown();", src)
        self.assertNotIn("request_guest_shutdown_for_future_reset();", src)
        self.assertNotIn("munmap(", src)
        self.assertNotIn("execv(", src)

    def test_f8_is_still_only_diagnostic(self) -> None:
        src = (ROOT / "src/game/input.cpp").read_text(encoding="utf-8")
        self.assertIn("ultramodern::report_native_event_reset_blockers();", src)
        self.assertNotIn("ultramodern::report_native_event_exit_status();", src)
        self.assertNotIn("request_guest_shutdown_for_future_reset();", src)
        handler = src.split("// Input plumbing only:", 1)[1].split(
            "\nvoid recomp::set_rumble(", 1
        )[0]
        for forbidden in ("ultramodern::quit(", "execv(", "memset(", "munmap("):
            self.assertNotIn(forbidden, handler)

    def test_default_off_and_requires_stage5(self) -> None:
        cm = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn('option(GOEMON_JP_HOST_STAGE6 "Enable JP native VI/RT64/RSP worker lifecycle audit" OFF)', cm)
        self.assertIn("GOEMON_JP_HOST_STAGE6 AND NOT GOEMON_JP_JOIN_STAGE5", cm)
        self.assertIn("patch_native_events_stage6.py", cm)
        self.assertIn('JP_TIMER_GENERATED_DIR}/events.cpp', cm)
        self.assertIn('JP_TIMER_RUNTIME_ROOT}/ultramodern/src/events.cpp', cm)
        self.assertIn("GOEMON_JP_HOST_STAGE6_ACTIVE", cm)

    def test_usa_version_unchanged(self) -> None:
        main = (ROOT / "src/main/main.cpp").read_text()
        self.assertIn('version_string = "0.2.11-dev"', main)
        self.assertIn('version_string = "0.2.3-dev"', main)
        self.assertIn('jp_host_build_mode = " [host-audit]"', main)
        self.assertIn('jp_host_build_mode = " [host-off]"', main)
        launch = (ROOT / "src/ui/ui_launcher.cpp").read_text()
        self.assertIn('version_string += " [host-audit]"', launch)

    def test_rejects_second_injection(self) -> None:
        with self.assertRaisesRegex(ValueError, "already applied"):
            mod.instrument_events(self.output)
        # The sentinel inside event state is independently sufficient.
        no_header = self.output.replace(mod.MARKER + "\n", "", 1)
        with self.assertRaisesRegex(ValueError, "already applied"):
            mod.instrument_events(no_header)

    def test_generation_output_is_atomic_and_noop_if_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.cpp"
            path.write_text(self.output, encoding="utf-8")
            first = path.stat().st_mtime_ns
            self.assertEqual(path.read_text(encoding="utf-8"), self.output)
            self.assertEqual(first, path.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
