#!/usr/bin/env python3
"""Create JP-only reset-runtime source overlays without modifying the submodule.

Every change requires an exact upstream anchor. This stage only makes the
timer worker joinable at shutdown; it does not implement N64 guest reset.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def once(src: str, needle: str, replacement: str, reason: str) -> str:
    n = src.count(needle)
    if n != 1:
        raise ValueError(f"{reason}: expected exactly one pinned-runtime anchor; found {n}")
    return src.replace(needle, replacement, 1)


def timer_source(src: str) -> str:
    src = once(src,
        "using Action = std::variant<AddTimerAction, RemoveTimerAction>;",
        "struct ShutdownTimerAction {};\n\n"
        "using Action = std::variant<AddTimerAction, RemoveTimerAction, ShutdownTimerAction>;",
        "shutdown action")
    src = once(src,
        "    // Lambda to process a timer action to handle adding and removing timers",
        "    bool shutdown_requested = false;\n\n"
        "    // Lambda to process a timer action to handle adding and removing timers",
        "shutdown flag")
    src = once(src,
        "        } else if (const auto* remove_action = std::get_if<RemoveTimerAction>(&action)) {\n"
        "            active_timers.erase(remove_action->timer);\n"
        "        }\n"
        "    };",
        "        } else if (const auto* remove_action = std::get_if<RemoveTimerAction>(&action)) {\n"
        "            active_timers.erase(remove_action->timer);\n"
        "        } else if (std::holds_alternative<ShutdownTimerAction>(action)) {\n"
        "            shutdown_requested = true;\n"
        "        }\n"
        "    };",
        "action dispatch")
    src = once(src,
        "    while (true) {\n        // Empty the action queue",
        "    while (!shutdown_requested) {\n        // Empty the action queue",
        "timer worker loop")
    src = once(src,
        "        while (timer_context.action_queue.try_dequeue(cur_action)) {\n"
        "            process_timer_action(cur_action);\n"
        "        }\n\n"
        "        // If there's no timer to act on, wait for one to come in from the action queue\n"
        "        while (active_timers.empty()) {\n"
        "            timer_context.action_queue.wait_dequeue(cur_action);\n"
        "            process_timer_action(cur_action);\n"
        "        }\n\n"
        "        // Get the timer that's closest to running out",
        "        while (timer_context.action_queue.try_dequeue(cur_action)) {\n"
        "            process_timer_action(cur_action);\n"
        "        }\n"
        "        if (shutdown_requested) {\n"
        "            break;\n"
        "        }\n\n"
        "        // If there's no timer to act on, wait for one to come in from the action queue\n"
        "        while (active_timers.empty() && !shutdown_requested) {\n"
        "            timer_context.action_queue.wait_dequeue(cur_action);\n"
        "            process_timer_action(cur_action);\n"
        "        }\n"
        "        if (shutdown_requested) {\n"
        "            break;\n"
        "        }\n\n"
        "        // Get the timer that's closest to running out",
        "worker quiescence")
    src = once(src,
        "void ultramodern::init_timers(RDRAM_ARG1) {\n"
        "    timer_context.thread = std::thread{ timer_thread, PASS_RDRAM1 };\n"
        "    timer_context.thread.detach();\n"
        "}",
        "void ultramodern::init_timers(RDRAM_ARG1) {\n"
        "    // A guest generation must not reuse RDRAM until the old timer joins.\n"
        "    assert(!timer_context.thread.joinable() && \"Timer worker already active\");\n"
        "    timer_context.thread = std::thread{ timer_thread, PASS_RDRAM1 };\n"
        "}\n\n"
        "// First reset prerequisite: quiesce timers before RDRAM teardown.\n"
        "// This is not a game reset or game-entrypoint restart.\n"
        "void ultramodern::shutdown_timers() {\n"
        "    if (!timer_context.thread.joinable()) {\n"
        "        return;\n"
        "    }\n"
        "    timer_context.action_queue.enqueue(ShutdownTimerAction{});\n"
        "    timer_context.thread.join();\n"
        "    Action stale_action;\n"
        "    while (timer_context.action_queue.try_dequeue(stale_action)) {}\n"
        "    fprintf(stderr, \"[Goemon JP runtime] Timer worker joined cleanly.\\n\");\n"
        "}",
        "joinable worker")
    return "// Generated from pinned N64ModernRuntime timer.cpp; do not edit.\n" + src


def recomp_source(src: str) -> str:
    src = once(src,
        '#include "recompiler/live_recompiler.h"\n',
        '#include "recompiler/live_recompiler.h"\n\n'
        '// Private JP reset runtime build overlay, no upstream submodule edits.\n'
        'namespace ultramodern { void shutdown_timers(); }\n',
        "timer shutdown declaration")
    src = once(src,
        '    game_thread.join();\n'
        '    ultramodern::join_event_threads();',
        '    game_thread.join();\n'
        '    // Timer may still reference guest RDRAM; join before unmapping RAM.\n'
        '    ultramodern::shutdown_timers();\n'
        '    ultramodern::join_event_threads();',
        "shutdown call")
    return "// Generated from pinned N64ModernRuntime recomp.cpp; do not edit.\n" + src


def write_if_changed(path: Path, data: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == data:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()

    original_timer = (a.runtime / "ultramodern/src/timer.cpp").read_text(encoding="utf-8")
    original_recomp = (a.runtime / "librecomp/src/recomp.cpp").read_text(encoding="utf-8")
    changes = {
        a.output / "timer.cpp": timer_source(original_timer),
        a.output / "recomp.cpp": recomp_source(original_recomp),
    }
    for output, transformed in changes.items():
        changed = write_if_changed(output, transformed)
        print(f"[JP timer runtime] {'Updated' if changed else 'Unchanged'}: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
