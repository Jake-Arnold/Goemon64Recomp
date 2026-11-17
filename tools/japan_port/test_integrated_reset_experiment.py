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
        self.assertIn('option(GOEMON_JP_INTEGRATED_F8_RESET_EXPERIMENTAL "Experimental same-process F8 reset (may be unstable; disposable saves only)" OFF)', self.cmake)
        self.assertIn("GOEMON_JP_INTEGRATED_F8_RESET_EXPERIMENTAL AND NOT GOEMON_JP_TIMER_EPOCH_STAGE18", self.cmake)

    def test_frontend_macro_is_defined_after_japanese_target_exists(self):
        # CMake refuses target_compile_definitions for a not-yet-created
        # executable. This failed an actual Ubuntu configure (17 Nov).
        creation = self.cmake.index(
            "add_executable(Goemon64RecompiledJP ${JP_SOURCES})")
        macro = self.cmake.index(
            "target_compile_definitions(Goemon64RecompiledJP PRIVATE "
            "GOEMON_JP_EXPERIMENTAL_RESET_BACKEND_ACTIVE)")
        self.assertGreater(macro, creation)
        self.assertIn(
            "if(GOEMON_JP_INTEGRATED_F8_RESET_EXPERIMENTAL)\n"
            "        target_compile_definitions(Goemon64RecompiledJP PRIVATE "
            "GOEMON_JP_EXPERIMENTAL_RESET_BACKEND_ACTIVE)",
            self.cmake)

    def test_usa_only_fail_closed_audio_bridge_links(self):
        # Both native executables link the same experimental librecomp
        # archive. JP defines the real SDL callback in main.cpp, while
        # the USA executable needs its own fail-closed symbol.
        stub_path = ROOT / "src/main/jp_integrated_audio_unavailable_usa.cpp"
        stub = stub_path.read_text(encoding="utf-8")
        symbol = "bool jp_reset_audio_buffer_after_join()"
        self.assertIn(symbol, stub)
        self.assertIn("return false;", stub)
        self.assertIn("namespace recomp {", stub)
        self.assertIn(symbol, self.front)
        self.assertIn(
            '#ifdef GOEMON_JP_EXPERIMENTAL_RESET_BACKEND_ACTIVE',
            self.front)
        self.assertIn(
            "target_sources(Goemon64Recompiled PRIVATE\\n"
            '            "${CMAKE_SOURCE_DIR}/src/main/jp_integrated_audio_unavailable_usa.cpp")',
            self.cmake)
        # The JP target snapshots the USA source list *before* the stub is
        # added to the USA executable; no duplicate JP symbol.
        snapshot = self.cmake.index(
            "get_target_property(JP_SOURCES Goemon64Recompiled SOURCES)")
        stub_source = self.cmake.index(
            "src/main/jp_integrated_audio_unavailable_usa.cpp")
        self.assertGreater(stub_source, snapshot)
        compiler = shutil.which("clang++") or shutil.which("g++")
        if compiler is None:
            self.skipTest("No C++ compiler installed")
        with tempfile.TemporaryDirectory() as td:
            test_cpp = Path(td) / "test_usa_audio_link.cpp"
            binary = Path(td) / "test_usa_audio_link"
            test_cpp.write_text(
                "namespace recomp { bool jp_reset_audio_buffer_after_join(); }\\n"
                "int main() { return recomp::jp_reset_audio_buffer_after_join() "
                "? 1 : 0; }\\n",
                encoding="utf-8")
            subprocess.run(
                [compiler, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                 str(test_cpp), str(stub_path), "-o", str(binary)],
                check=True, cwd=ROOT, timeout=45)
            subprocess.run([str(binary)], check=True, cwd=ROOT,
                           timeout=15)

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
        self.assertIn("if (!external_ready)", self.script)
        self.assertIn("jp_rearm_external_messages_after_verified_exit(", self.script)
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

    def test_actual_pinned_runtime_generator_composition(self):
        # Exercise all six generated overlays from the actual pinned
        # N64ModernRuntime checkout; the old tests checked strings only.
        runtime = ROOT / "lib/N64ModernRuntime"
        inputs = {
            "threads": runtime / "ultramodern/src/threads.cpp",
            "messages": runtime / "ultramodern/src/mesgqueue.cpp",
            "events": runtime / "ultramodern/src/events.cpp",
            "timer": runtime / "ultramodern/src/timer.cpp",
            "saving": runtime / "librecomp/src/pi.cpp",
            "recomp": runtime / "librecomp/src/recomp.cpp",
        }
        if not all(path.is_file() for path in inputs.values()):
            self.skipTest("Requires pinned N64ModernRuntime checkout")
        import importlib.util

        def module(name, filename):
            spec = importlib.util.spec_from_file_location(
                name, ROOT / "tools/japan_port" / filename)
            assert spec and spec.loader
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        stage7 = module("jp_reset_stage7_test", "patch_native_boot_save_audio_stage7.py")
        stage9 = module("jp_reset_stage9_test", "patch_guest_exit_stage9.py")
        stage14 = module("jp_reset_stage14_test", "patch_config_publisher_fence_stage14.py")
        stage12 = module("jp_reset_stage12_test", "patch_exit_barrier_stage12.py")
        stage16 = module("jp_reset_stage16_test", "patch_save_finalize_stage16.py")
        stage17 = module("jp_reset_stage17_test", "patch_timer_producer_fence_stage17.py")
        stage18 = module("jp_reset_stage18_test", "patch_timer_epoch_stage18.py")
        integrated = module("jp_reset_integrated_test", "patch_integrated_reset_experiment.py")

        original = {key: path.read_text(encoding="utf-8")
                    for key, path in inputs.items()}
        generated = {
            "threads": stage9.instrument_threads(original["threads"]),
            "messages": stage9.stage8.stage6.stage5.stage4.instrument_messages(original["messages"]),
            "events": stage14.instrument_events(original["events"]),
            "timer": stage18.instrument_stage17_timer(
                stage17.instrument_timer(original["timer"])),
            "saving": stage16.instrument_pi(original["saving"]),
            "recomp": stage17.instrument_recomp_after_stage12(
                stage12.instrument_recomp_stage7(
                    stage7.instrument_recomp(original["recomp"]))),
        }
        methods = {
            "threads": integrated.threads,
            "messages": integrated.messages,
            "events": integrated.events,
            "timer": integrated.timer,
            "saving": integrated.saving,
            "recomp": integrated.recomp,
        }
        emit_root = os.environ.get("JP_INTEGRATED_EMIT_DIR")
        outputs = {
            "threads": "threads_reset.cpp",
            "messages": "mesgqueue_integrated.cpp",
            "events": "events_integrated.cpp",
            "timer": "timer_integrated.cpp",
            "saving": "pi_integrated.cpp",
            "recomp": "recomp_integrated.cpp",
        }
        for key, transform in methods.items():
            with self.subTest(component=key):
                result = transform(generated[key])
                self.assertGreater(len(result), 500)
                self.assertIn("// Experimental ", result)
                if emit_root:
                    destination = Path(emit_root) / outputs[key]
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(result, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "already"):
                    transform(result)

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
