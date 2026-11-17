#!/usr/bin/env python3
"""JP stage11: read-only live-generation producer preflight on F8.

Stage10 proves exit-only draining. This stage observes what is still
active WHILE the PC app is running. It does not request stop, drain
queues, pause audio, reset RDRAM or re-enter the native boot routine.
Pinned N64ModernRuntime sources remain untouched.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage10():
    path = Path(__file__).with_name("patch_action_drain_stage10.py")
    spec = importlib.util.spec_from_file_location("jp_reset_stage10", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing stage10 source generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage10 = load_stage10()

REPORT = r"""// Stage11: snapshot only, on a single F8 press during live gameplay.
// IMPORTANT: an empty queue is NOT a generation-stop barrier. This function
// does not claim guest/thread/audio/save/input producers are covered.
void ultramodern::jp_report_live_generation_preflight() {
    const bool initialized = jp_event_workers_initialized.load(std::memory_order_acquire);
    const bool vi = jp_event_vi_active.load(std::memory_order_acquire);
    const bool gfx = jp_event_gfx_active.load(std::memory_order_acquire);
    const bool sp = jp_event_sp_active.load(std::memory_order_acquire);
    const auto gfx_pending = jp_event_gfx_tasks_pending.load(std::memory_order_acquire);
    const auto sp_pending = jp_event_sp_tasks_pending.load(std::memory_order_acquire);
    const auto submitted = jp_gfx_tasks_submitted.load(std::memory_order_acquire);
    const auto completed = jp_gfx_tasks_completed.load(std::memory_order_acquire);
    const auto queued = events_context.action_queue.size_approx();
    bool config_open;
    {
        std::lock_guard<std::mutex> lock(jp_config_action_publish_mutex);
        config_open = !jp_config_actions_closed_for_pc_exit;
    }
    // Each bit means a KNOWN outstanding activity, not a complete census:
    // 0 VI, 1 GFX, 2 SP, 3 pending GFX, 4 pending SP,
    // 5 submitted != completed, 6 action queue nonempty, 7 config open.
    const unsigned blockers =
        (vi ? 1u : 0u) |
        (gfx ? 2u : 0u) |
        (sp ? 4u : 0u) |
        (gfx_pending ? 8u : 0u) |
        (sp_pending ? 16u : 0u) |
        (submitted != completed ? 32u : 0u) |
        (queued ? 64u : 0u) |
        (config_open ? 128u : 0u);
    std::fprintf(stderr,
        "[Goemon JP live preflight stage11] initialized=%u vi=%u gfx=%u sp=%u "
        "pending_gfx=%llu pending_sp=%llu gfx_submitted=%llu gfx_completed=%llu "
        "actions_approx=%zu config_open=%u blockers=0x%02X ready=0; "
        "guest/boot/timer/audio/save/input fences unproven; "
        "F8 diagnostic only, no generation stop or RDRAM reset.\n",
        static_cast<unsigned>(initialized),
        static_cast<unsigned>(vi), static_cast<unsigned>(gfx),
        static_cast<unsigned>(sp),
        static_cast<unsigned long long>(gfx_pending),
        static_cast<unsigned long long>(sp_pending),
        static_cast<unsigned long long>(submitted),
        static_cast<unsigned long long>(completed),
        static_cast<size_t>(queued),
        static_cast<unsigned>(config_open), blockers);
}

"""


def instrument_events(original: str) -> str:
    marker = "// Generated JP stage11 live-preflight census; no F8 stop."
    if marker in original or "jp_report_live_generation_preflight()" in original:
        raise ValueError("Stage11 live preflight already applied")
    src = stage10.instrument_events(original)
    src = stage10.once(
        src,
        "    bool jp_drain_action_queue_after_pc_exit(bool all_guests_joined);\n",
        "    bool jp_drain_action_queue_after_pc_exit(bool all_guests_joined);\n"
        "    void jp_report_live_generation_preflight();\n",
        "stage11 runtime diagnostic declaration",
    )
    src = stage10.once(
        src,
        "bool ultramodern::jp_drain_action_queue_after_pc_exit(bool all_guests_joined) {\n",
        REPORT + "bool ultramodern::jp_drain_action_queue_after_pc_exit(bool all_guests_joined) {\n",
        "stage11 live diagnostic before exit-only queue drain",
    )
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("guest",), required=True)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    base = args.runtime / "ultramodern/src"
    transforms = (
        ("threads.cpp", stage10.stage9.instrument_threads),
        ("mesgqueue.cpp", stage10.stage8.stage6.stage5.stage4.instrument_messages),
        ("scheduling.cpp", stage10.stage8.stage6.stage5.instrument_scheduler),
        ("events.cpp", instrument_events),
    )
    write = stage10.stage8.stage6.stage5.stage4.stage3.write_if_changed
    for name, transform in transforms:
        destination = args.output / name
        updated = write(destination, transform((base / name).read_text(encoding="utf-8")))
        print(f"[JP live stage11] {'Updated' if updated else 'Unchanged'}: {destination}")


if __name__ == "__main__":
    main()
