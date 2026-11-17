#!/usr/bin/env python3
"""JP stage10: classify and drain abandoned host action records at PC exit.

This is NOT a live F8 reset. The native boot must have finished and all
guest OSThreads and native VI/GFX/SP workers must have joined before the
queue is examined. Incomplete shutdown skips the drain and retains RAM.

Everything is generated into the build directory from the pinned runtime.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _load_stage9():
    src = Path(__file__).with_name("patch_guest_exit_stage9.py")
    spec = importlib.util.spec_from_file_location("jp_stage9", src)
    if spec is None or spec.loader is None:
        raise RuntimeError("Stage9 source generator is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage9 = _load_stage9()
stage8 = stage9.stage8


def once(src: str, old: str, new: str, label: str) -> str:
    return stage8.once(src, old, new, label)


ACTION_DRAIN = r"""// Stage10: normal-PC-exit cleanup only, NEVER called from live F8.
// UI config notifications are the sole surviving action producer after
// successful guest/VI/SP joins. Close its publishing path under the same
// mutex used to drain the queue. In a future true reset, every producer
// and the entire generation must be covered by a stronger coordinator.
static std::mutex jp_config_action_publish_mutex;
static bool jp_config_actions_closed_for_pc_exit = false;

bool ultramodern::jp_drain_action_queue_after_pc_exit(bool all_guests_joined) {
    if (!all_guests_joined ||
        !jp_event_gfx_joined.load(std::memory_order_acquire) ||
        !jp_event_vi_joined.load(std::memory_order_acquire) ||
        !jp_event_sp_joined.load(std::memory_order_acquire)) {
        std::fprintf(stderr,
            "[Goemon JP action exit stage10] skipped=1 guests_joined=%u "
            "native_joined=%u/%u/%u; do not drain live-generation work.\n",
            static_cast<unsigned>(all_guests_joined),
            static_cast<unsigned>(jp_event_gfx_joined.load(std::memory_order_acquire)),
            static_cast<unsigned>(jp_event_vi_joined.load(std::memory_order_acquire)),
            static_cast<unsigned>(jp_event_sp_joined.load(std::memory_order_acquire)));
        return false;
    }
    std::lock_guard<std::mutex> lock(jp_config_action_publish_mutex);
    jp_config_actions_closed_for_pc_exit = true;
    uint64_t abandoned_screen = 0;
    uint64_t abandoned_config = 0;
    uint64_t unexpected_graphics = 0;
    Action queued;
    while (events_context.action_queue.try_dequeue(queued)) {
        if (std::holds_alternative<ScreenUpdateAction>(queued)) {
            abandoned_screen++;
        } else if (std::holds_alternative<UpdateConfigAction>(queued)) {
            abandoned_config++;
        } else if (std::holds_alternative<SpTaskAction>(queued)) {
            unexpected_graphics++;
        }
    }
    // This is a snapshot AFTER known native/guest producers have joined,
    // not a reusable reset barrier. No renderer work is executed here.
    const auto remainder = events_context.action_queue.size_approx();
    const auto pending = jp_event_gfx_tasks_pending.load(std::memory_order_acquire);
    const bool expected_only =
        unexpected_graphics == 0 && pending == 0 && remainder == 0 &&
        jp_gfx_tasks_submitted.load(std::memory_order_acquire) ==
            jp_gfx_tasks_completed.load(std::memory_order_acquire);
    std::fprintf(stderr,
        "[Goemon JP action exit stage10] skipped=0 screen=%llu config=%llu "
        "unexpected_graphics=%llu pending_gfx=%llu remaining_approx=%zu "
        "expected_only=%u; PC exit only, no F8 reset.\n",
        static_cast<unsigned long long>(abandoned_screen),
        static_cast<unsigned long long>(abandoned_config),
        static_cast<unsigned long long>(unexpected_graphics),
        static_cast<unsigned long long>(pending),
        static_cast<size_t>(remainder),
        static_cast<unsigned>(expected_only));
    return expected_only;
}

"""


def instrument_events(original: str) -> str:
    marker = "// Generated JP stage10 PC-exit abandoned action census; no F8 drain."
    if marker in original or "jp_config_actions_closed_for_pc_exit" in original:
        raise ValueError("JP stage10 action queue instrumentation already applied")
    src = stage8.instrument_events(original)
    src = once(
        src,
        "    void jp_report_graphics_queue_settlement();\n",
        "    void jp_report_graphics_queue_settlement();\n"
        "    bool jp_drain_action_queue_after_pc_exit(bool all_guests_joined);\n",
        "stage10 event drain declaration",
    )
    src = once(
        src,
        "void ultramodern::trigger_config_action() {\n"
        "    events_context.action_queue.enqueue(UpdateConfigAction{});\n"
        "}\n",
        ACTION_DRAIN
        + "void ultramodern::trigger_config_action() {\n"
        + "    // The renderer has exited: do not enqueue stale UI config work.\n"
        + "    std::lock_guard<std::mutex> lock(jp_config_action_publish_mutex);\n"
        + "    if (jp_config_actions_closed_for_pc_exit) return;\n"
        + "    events_context.action_queue.enqueue(UpdateConfigAction{});\n"
        + "}\n",
        "stage10 config publication gate and normal-exit queue drain",
    )
    return marker + "\n" + src


def instrument_recomp_stage7(original: str) -> str:
    marker = "// Generated JP stage10 PC-exit action census; no live F8 cleanup."
    if marker in original or "jp_drain_action_queue_after_pc_exit(" in original:
        raise ValueError("JP stage10 native exit already instrumented")
    src = stage9.instrument_recomp_stage7(original)
    src = once(
        src,
        "    void request_guest_shutdown_for_future_reset();\n",
        "    bool jp_drain_action_queue_after_pc_exit(bool all_guests_joined);\n"
        "    void request_guest_shutdown_for_future_reset();\n",
        "recomp exit action drain forward declaration",
    )
    src = once(
        src,
        "    ultramodern::join_event_threads();\n"
        "    ultramodern::join_thread_cleaner_thread();\n",
        "    ultramodern::join_event_threads();\n"
        "    // Only after guest + VI/GFX/SP workers are fully joined can\n"
        "    // abandoned screen/config action records be classified safely.\n"
        "    const bool jp_actions_expected_only =\n"
        "        ultramodern::jp_drain_action_queue_after_pc_exit(jp_guest_exit_drained);\n"
        "    (void)jp_actions_expected_only; // Not a real reset barrier.\n"
        "    ultramodern::join_thread_cleaner_thread();\n",
        "normal exit action drain after guest+native workers joined",
    )
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("guest", "recomp"), required=True)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    write = stage8.stage6.stage5.stage4.stage3.write_if_changed
    if args.mode == "guest":
        if args.runtime is None:
            parser.error("--runtime required for guest mode")
        transforms = (
            ("threads.cpp", stage9.instrument_threads),
            ("mesgqueue.cpp", stage8.stage6.stage5.stage4.instrument_messages),
            ("scheduling.cpp", stage8.stage6.stage5.instrument_scheduler),
            ("events.cpp", instrument_events),
        )
        for name, transform in transforms:
            original = (args.runtime / "ultramodern/src" / name).read_text()
            dest = args.output / name
            updated = write(dest, transform(original))
            print(f"[JP action stage10] {'Updated' if updated else 'Unchanged'}: {dest}")
    else:
        if args.source is None:
            parser.error("--source required for recomp mode")
        updated = write(args.output, instrument_recomp_stage7(args.source.read_text()))
        print(f"[JP action stage10] {'Updated' if updated else 'Unchanged'}: {args.output}")


if __name__ == "__main__":
    main()
