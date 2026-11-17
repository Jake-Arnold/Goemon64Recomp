#!/usr/bin/env python3
"""JP Stage12: normal-PC-exit cross-subsystem quiescence census.

This is a *read-only post-join observer*, not a live F8 barrier. It combines
Stage9 guest join + Stage10 action cleanup with existing Stage6/7/8 predicates
only after save thread join. Even when all known predicates pass, SDL audio,
timer epoch, outside publishers and generation restart remain unproven.
Generated recomp source only; no modifications to the pinned runtime.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage10():
    path = Path(__file__).with_name("patch_action_drain_stage10.py")
    spec = importlib.util.spec_from_file_location("jp_reset_stage10", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing Stage10 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage10 = load_stage10()


EXIT_SNAPSHOT = r"""    // Stage12: PC-exit-only census once guest/native/cleaner/save joins have
    // returned and Stage10 has finished classifying abandoned host actions.
    // NEVER call this from live F8 or interpret it as a reset approval.
    const bool jp_exit_boot_joined =
        recomp::jp_native_boot_joined_for_future_reset();
    const bool jp_exit_native_joined =
        ultramodern::jp_event_workers_joined_for_future_reset();
    const bool jp_exit_graphics_settled =
        ultramodern::jp_graphics_queue_settled_for_future_reset();
    const bool jp_exit_save_joined =
        ultramodern::jp_save_worker_joined_for_future_reset();
    const bool jp_exit_audio_dispatch_idle =
        ultramodern::jp_audio_dispatch_idle_for_future_reset();
    const bool jp_exit_known_joined =
        jp_guest_exit_drained && jp_exit_boot_joined && jp_exit_native_joined &&
        jp_exit_graphics_settled && jp_actions_expected_only &&
        jp_exit_save_joined && jp_exit_audio_dispatch_idle;
    std::fprintf(stderr,
        "[Goemon JP exit barrier stage12] guest=%u boot=%u native=%u "
        "graphics=%u action=%u save=%u audio_dispatch=%u known_joined=%u "
        "timer_epoch=unproven sdl_audio=unproven producer_fences=unproven "
        "restart=0; PC exit only, F8 disabled.\n",
        static_cast<unsigned>(jp_guest_exit_drained),
        static_cast<unsigned>(jp_exit_boot_joined),
        static_cast<unsigned>(jp_exit_native_joined),
        static_cast<unsigned>(jp_exit_graphics_settled),
        static_cast<unsigned>(jp_actions_expected_only),
        static_cast<unsigned>(jp_exit_save_joined),
        static_cast<unsigned>(jp_exit_audio_dispatch_idle),
        static_cast<unsigned>(jp_exit_known_joined));
"""


def instrument_recomp_stage7(original: str) -> str:
    marker = "// Generated JP stage12 post-join exit census; F8 remains read-only."
    if marker in original or "[Goemon JP exit barrier stage12]" in original:
        raise ValueError("Stage12 exit census already instrumented")
    src = stage10.instrument_recomp_stage7(original)
    src = stage10.once(
        src,
        "namespace ultramodern { void shutdown_timers(); }\n",
        "namespace ultramodern { void shutdown_timers(); }\n"
        "namespace ultramodern {\n"
        "    bool jp_event_workers_joined_for_future_reset();\n"
        "    bool jp_graphics_queue_settled_for_future_reset();\n"
        "    bool jp_save_worker_joined_for_future_reset();\n"
        "    bool jp_audio_dispatch_idle_for_future_reset();\n"
        "}\n"
        "namespace recomp { bool jp_native_boot_joined_for_future_reset(); }\n",
        "stage12 cross-subsystem read-only predicate declarations",
    )
    src = stage10.once(
        src,
        "    ultramodern::join_saving_thread();\n",
        "    ultramodern::join_saving_thread();\n" + EXIT_SNAPSHOT,
        "stage12 census after saving worker join",
    )
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("recomp",), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write = stage10.stage8.stage6.stage5.stage4.stage3.write_if_changed
    updated = write(args.output, instrument_recomp_stage7(
        args.source.read_text(encoding="utf-8")))
    print(f"[JP exit barrier stage12] {'Updated' if updated else 'Unchanged'}: {args.output}")


if __name__ == "__main__":
    main()
