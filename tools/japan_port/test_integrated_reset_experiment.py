#!/usr/bin/env python3
"""Integrated F8 reset experiment: source and native host regression.

Run AFTER CMake generation to inspect the *actual* generated runtime.
A passing host test is not a claim that the graphics game reset works.
"""
from __future__ import annotations
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "build-generated/japan-native-game/jp_reset_timer_runtime"

class IntegratedResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / "tools/japan_port/patch_integrated_reset_experiment.py").read_text()
        cls.cmake = (ROOT / "CMakeLists.txt").read_text()
        cls.input = (ROOT / "src/game/input.cpp").read_text()
        cls.front = (ROOT / "src/main/main.cpp").read_text()
        cls.gate = (ROOT / "src/game/jp_generation_publisher_gate.hpp").read_text()
        cls.clock = (ROOT / "src/game/jp_timer_epoch_clock.hpp").read_text()

    def test_default_off_and_requires_stage18(self):
        self.assertIn('option(GOEMON_JP_INTEGRATED_F8_RESET_EXPERIMENTAL', self.cmake)
        self.assertIn(' " OFF)', self.cmake)
        self.assertIn("GOEMON_JP_INTEGRATED_F8_RESET_EXPERIMENTAL AND NOT GOEMON_JP_TIMER_EPOCH_STAGE18", self.cmake)

    def test_six_generated_runtime_owners_together(self):
        for name in ("threads_reset.cpp", "mesgqueue_integrated.cpp", "events_integrated.cpp",
                     "timer_integrated.cpp", "pi_integrated.cpp",
                     "recomp_integrated.cpp"):
            self.assertIn(name, self.script)
            self.assertIn(name, self.cmake)
        self.assertIn("JP_INTEGRATED_RESULT EQUAL 0", self.cmake)

    def test_no_process_replacement(self):
        for token in ("execv(", "execvp(", "system(", "fork(", "posix_spawn("):
            self.assertNotIn(token, self.script)
            self.assertNotIn(token, self.front)

    def test_requested_from_f8_but_not_direct_memory_cleanup(self):
        h = self.input.split("[Goemon JP reset] Request received;", 1)[0]
        self.assertIn("jp_request_integrated_reset();", self.input)
        self.assertIn("#ifdef GOEMON_JP_EXPERIMENTAL_RESET_BACKEND_ACTIVE", self.input)
        for token in ("munmap(", "memset(", "request_guest_shutdown_for_future_reset("):
            self.assertNotIn(token, h)

    def test_reset_goes_through_verified_normal_exit_barrier(self):
        self.assertIn("jp_exit_known_joined && jp_guest_exit_drained", self.script)
        self.assertIn("jp_integrated_rdram_released", self.script)
        self.assertIn("jp_external_queue_drained", self.script)
        self.assertIn("reason=unproven-shutdown-or-memory-release", self.script)
        self.assertIn("result=ABORT", self.script)

    def test_rearms_guest_timer_events_and_saving(self):
        for token in ("jp_rearm_guest_after_verified_exit",
                      "jp_rearm_timer_after_verified_exit",
                      "jp_rearm_events_after_verified_exit",
                      "jp_rearm_saving_after_verified_exit"):
            self.assertIn(token, self.script)
        self.assertIn("if (!audio_ready)", self.script)
        self.assertIn("result=REARMED", self.script)

    def test_reuses_same_window_and_audio_device(self):
        self.assertIn("if (window != nullptr)", self.front)
        self.assertIn("SDL window reused=", self.front)
        self.assertIn("jp_reset_audio_buffer_after_join()", self.front)
        self.assertIn("SDL_ClearQueuedAudio(audio_device)", self.front)
        self.assertNotIn("SDL_DestroyWindow(window)", self.front)

    def test_guarded_clock_and_gate_renewal(self):
        self.assertIn("#ifdef GOEMON_JP_EXPERIMENTAL_RESET_BACKEND_ACTIVE", self.gate)
        self.assertIn("!all_old_workers_joined || open_ || in_flight_ != 0", self.gate)
        self.assertIn("generation_ == std::numeric_limits<std::uint64_t>::max()", self.gate)
        self.assertIn("rebase_after_verified_exit", self.clock)
        self.assertIn("!proof.guest_refs_released", self.clock)

    def test_no_unproven_live_memory_clear(self):
        for f in (self.script, self.input):
            self.assertNotIn("memset(rdram", f)
            self.assertNotIn("mprotect(rdram", f)

    def test_generated_runtime_integration(self):
        files = [GEN / name for name in
                 ("threads_reset.cpp","mesgqueue_integrated.cpp","events_integrated.cpp",
                  "timer_integrated.cpp","pi_integrated.cpp",
                  "recomp_integrated.cpp")]
        if not all(f.exists() for f in files):
            self.skipTest("Run integrated reset CMake configure to generate runtime sources")
        texts = [f.read_text() for f in files]
        self.assertIn("jp_rearm_guest_after_verified_exit()", texts[0])
        self.assertIn("jp_flush_external_messages_after_join(", texts[1])
        self.assertIn("jp_rearm_events_after_verified_exit(", texts[2])
        self.assertIn("jp_rearm_timer_after_verified_exit(", texts[3])
        self.assertIn("jp_rearm_saving_after_verified_exit()", texts[4])
        self.assertIn("jp_request_integrated_reset()", texts[5])
        self.assertIn("jp_exit_known_joined && jp_guest_exit_drained", texts[5])
        self.assertIn("jp_integrated_rdram_released", texts[5])
        self.assertIn("jp_external_queue_drained", texts[5])
        self.assertIn("for (;;) {", texts[5])

    def test_host_double_reboot_gate_regression(self):
        compiler = shutil.which("g++") or shutil.which("c++")
        if compiler is None:
            self.skipTest("No C++ compiler installed")
        source = Path(__file__).with_name("test_integrated_reset_gates.cpp")
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "jp_reset_gates"
            subprocess.run([compiler, "-std=c++20", "-O2", "-Wall",
                            "-Wextra", "-Werror", "-pthread",
                            str(source), "-o", str(target)],
                           check=True, cwd=ROOT, timeout=45)
            result = subprocess.run([str(target)], check=True, cwd=ROOT,
                                    capture_output=True, text=True, timeout=25)
            self.assertIn("generation=3 repeated=2", result.stdout)

if __name__ == "__main__":
    unittest.main()
