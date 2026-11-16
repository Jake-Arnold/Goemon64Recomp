#!/usr/bin/env python3
"""JP stage 9: bounded guest stop and join only on normal PC app exit.

In-process F8 remains a read-only diagnostic. On PC process shutdown,
the game-start native thread has first joined; guest OSThread host workers
are then asked to exit cooperatively while the RDRAM mapping still exists.
If the bounded join proof fails, the app skips munmap and lets process
termination recover the mapping rather than causing a use-after-unmap.

All patched runtime files are generated into the CMake build tree.
Never modify the pinned N64ModernRuntime git submodule.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def import_stage8():
    source = Path(__file__).with_name("patch_graphics_queue_stage8.py")
    spec = importlib.util.spec_from_file_location("jp_reset_stage8", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing stage-8 source generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage8 = import_stage8()


def once(source: str, old: str, new: str, label: str) -> str:
    return stage8.once(source, old, new, label)


def instrument_threads(original: str) -> str:
    marker = "// JP stage9 bounded guest cleanup at PC exit; no F8 stop."
    if marker in original:
        raise ValueError("Stage9 guest cleaner already patched")
    source = stage8.stage6.stage5.instrument_threads(original)
    source = once(
        source,
        "    // On normal process shutdown, drain already-completed guest threads\n"
        "    // until the deletion queue has remained empty for one poll interval.\n",
        "    // Stage9: keep the cleaner alive for a bounded coordinated guest\n"
        "    // stop attempt AFTER PC shutdown begins. A mere empty queue is\n"
        "    // never evidence that running guest threads have terminated.\n"
        "    auto jp_cleanup_exit_deadline = std::chrono::steady_clock::time_point::max();\n",
        "cleaner shutdown deadline",
    )
    source = once(
        source,
        "        } else if (exited.load(std::memory_order_acquire)) {\n"
        "            // No completed guest thread has arrived for 10 ms.\n"
        "            // Later completions are STILL possible: never use this\n"
        "            // diagnostic as an RDRAM-reset safety barrier.\n"
        "            break;\n"
        "        }\n",
        "        } else if (exited.load(std::memory_order_acquire)) {\n"
        "            const auto now = std::chrono::steady_clock::now();\n"
        "            if (jp_cleanup_exit_deadline ==\n"
        "                    std::chrono::steady_clock::time_point::max()) {\n"
        "                jp_cleanup_exit_deadline = now + std::chrono::milliseconds{1500};\n"
        "            }\n"
        "            // Only stop after an explicit coordinator request and\n"
        "            // the actual host join counter proves completion.\n"
        "            const bool requested = jp_guest_stop_requested.load(std::memory_order_acquire);\n"
        "            const bool all_joined =\n"
        "                jp_guest_creations_in_flight.load(std::memory_order_acquire) == 0 &&\n"
        "                jp_guest_threads_created.load(std::memory_order_acquire) ==\n"
        "                    jp_guest_threads_joined.load(std::memory_order_acquire);\n"
        "            if ((requested && all_joined) || now >= jp_cleanup_exit_deadline) {\n"
        "                break;\n"
        "            }\n"
        "        }\n",
        "bounded cleaner shutdown without treating empty queue as join",
    )
    return marker + "\n" + source


def instrument_recomp_stage7(original: str) -> str:
    marker = "// JP stage9 normal-PC-exit guest stop and RDRAM retain guard."
    if marker in original or "[Goemon JP guest exit stage9]" in original:
        raise ValueError("Stage9 recomp source already patched")
    if "// JP stage7 native boot census" not in original:
        raise ValueError("Stage9 requires the generated stage7 recomp source")
    source = once(
        original,
        "#include <cstdio>\n#include <atomic>\n",
        "#include <cstdio>\n#include <atomic>\n#include <cstdint>\n",
        "normal exit guest join API integer header",
    )
    source = once(
        source,
        "namespace ultramodern { void shutdown_timers(); }\n",
        "namespace ultramodern { void shutdown_timers(); }\n"
        "namespace ultramodern {\n"
        "    void request_guest_shutdown_for_future_reset();\n"
        "    bool wait_for_guest_joins_for_future_reset(std::uint32_t timeout_ms);\n"
        "}\n",
        "normal exit guest stop declarations",
    )
    source = once(
        source,
        "    game_thread.join();\n"
        "    jp_boot_thread_joined.store(true, std::memory_order_release);\n",
        "    game_thread.join();\n"
        "    jp_boot_thread_joined.store(true, std::memory_order_release);\n"
        "    // PC APP EXIT ONLY: all future guest spawning from the native boot\n"
        "    // entry has now stopped. F8 must NOT call either method below.\n"
        "    ultramodern::request_guest_shutdown_for_future_reset();\n"
        "    const bool jp_guest_exit_drained =\n"
        "        ultramodern::wait_for_guest_joins_for_future_reset(900);\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP guest exit stage9] joined=%u; \"\n"
        "        \"PC exit only; F8 not armed.\\n\",\n"
        "        static_cast<unsigned>(jp_guest_exit_drained));\n",
        "arm guest stop only after game-start host joined",
    )
    source = once(
        source,
        "    // Free rdram.\n"
        "    bool free_failed;\n",
        "    // Never unmap while a stale guest worker can still touch RDRAM.\n"
        "    // When the bounded guest join check fails, preserve this mapping\n"
        "    // until the OS terminates the process; no same-process reset.\n"
        "    if (jp_guest_exit_drained) {\n"
        "    // Free rdram.\n"
        "    bool free_failed;\n",
        "conditional RDRAM unmap only with fully joined guests",
    )
    source = once(
        source,
        '    if (free_failed) {\n        printf("Failed to free rdram\\n");\n    }\n}\n',
        '    if (free_failed) {\n        printf("Failed to free rdram\\n");\n    }\n'
        '    } else {\n'
        '        std::fprintf(stderr,\n'
        '            "[Goemon JP guest exit stage9] RDRAM retained: "\n'
        '            "guest join proof failed; OS process exit will reclaim it.\\n");\n'
        '    }\n'
        '}\n',
        "unmap failed-join closed",
    )
    return marker + "\n" + source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("guest", "recomp"), required=True)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.mode == "guest":
        if args.runtime is None:
            parser.error("--runtime required for guest mode")
        for filename, patch in (
            ("threads.cpp", instrument_threads),
            ("mesgqueue.cpp", stage8.stage6.stage5.stage4.instrument_messages),
            ("scheduling.cpp", stage8.stage6.stage5.instrument_scheduler),
            ("events.cpp", stage8.instrument_events),
        ):
            src = (args.runtime / "ultramodern/src" / filename).read_text(encoding="utf-8")
            dest = args.output / filename
            changed = stage8.stage6.stage5.stage4.stage3.write_if_changed(dest, patch(src))
            print(f"[JP exit stage9] {'Updated' if changed else 'Unchanged'}: {dest}")
    else:
        if args.source is None:
            parser.error("--source required for recomp mode")
        src = args.source.read_text(encoding="utf-8")
        changed = stage8.stage6.stage5.stage4.stage3.write_if_changed(
            args.output, instrument_recomp_stage7(src)
        )
        print(f"[JP exit stage9] {'Updated' if changed else 'Unchanged'}: {args.output}")


if __name__ == "__main__":
    main()
