#!/usr/bin/env python3
"""JP v0.2.13 reset stage 8: non-destructive graphics queue settlement audit.

Compose the pinned stage-6 events instrumenter and preserve stage-7
boot/save/audio sources. This counts and observes graphics work; it
does not consume, discard, reset or replay any queued action.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage6():
    path = Path(__file__).with_name("patch_native_events_stage6.py")
    spec = importlib.util.spec_from_file_location("jp_stage6_events", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Stage 6 source generator unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage6 = load_stage6()


def once(src: str, old: str, new: str, description: str) -> str:
    return stage6.once(src, old, new, description)


QUEUE_AUDIT = r"""// JP stage8: graphics RSP tasks submitted, dequeued and completed.
static std::atomic<uint64_t> jp_gfx_tasks_submitted{0};
static std::atomic<uint64_t> jp_gfx_tasks_started{0};
static std::atomic<uint64_t> jp_gfx_tasks_completed{0};

"""


QUEUE_FUNCTIONS = r"""// This is a necessary read-only observation, NOT a reset safety barrier.
// size_approx() is not a linearizable snapshot and producers can still
// enqueue after a query returns. Only a generation stop can forbid that.
bool ultramodern::jp_graphics_queue_settled_for_future_reset() {
    return jp_event_gfx_joined.load(std::memory_order_acquire) &&
        !jp_event_gfx_active.load(std::memory_order_acquire) &&
        jp_event_gfx_tasks_pending.load(std::memory_order_acquire) == 0 &&
        jp_gfx_tasks_submitted.load(std::memory_order_acquire) ==
            jp_gfx_tasks_completed.load(std::memory_order_acquire) &&
        events_context.action_queue.size_approx() == 0;
}

void ultramodern::jp_report_graphics_queue_settlement() {
    const auto submitted = jp_gfx_tasks_submitted.load(std::memory_order_acquire);
    const auto started = jp_gfx_tasks_started.load(std::memory_order_acquire);
    const auto completed = jp_gfx_tasks_completed.load(std::memory_order_acquire);
    const auto pending = jp_event_gfx_tasks_pending.load(std::memory_order_acquire);
    const auto queued_approx = events_context.action_queue.size_approx();
    std::fprintf(stderr,
        "[Goemon JP gfx queue] submitted=%llu started=%llu completed=%llu "
        "pending=%llu action_queue_approx=%zu joined=%u; "
        "no generation stop or queue reset.\n",
        static_cast<unsigned long long>(submitted),
        static_cast<unsigned long long>(started),
        static_cast<unsigned long long>(completed),
        static_cast<unsigned long long>(pending),
        static_cast<size_t>(queued_approx),
        static_cast<unsigned>(jp_event_gfx_joined.load(std::memory_order_acquire)));
}

"""


def instrument_events(original: str) -> str:
    marker = "// Generated JP graphics task queue settlement audit; pinned submodule unchanged."
    if marker in original or "jp_gfx_tasks_submitted" in original:
        raise ValueError("JP stage-8 graphics queue instrumentation already applied")
    src = stage6.instrument_events(original)
    src = once(
        src,
        "    bool jp_event_workers_joined_for_future_reset();\n",
        "    bool jp_event_workers_joined_for_future_reset();\n"
        "    bool jp_graphics_queue_settled_for_future_reset();\n"
        "    void jp_report_graphics_queue_settlement();\n",
        "graphics queue public function declarations",
    )
    src = once(
        src,
        "static std::atomic<uint64_t> jp_event_sp_tasks_pending{0};\n",
        "static std::atomic<uint64_t> jp_event_sp_tasks_pending{0};\n\n"
        + QUEUE_AUDIT,
        "graphics queue counters",
    )
    src = once(
        src,
        "} events_context{};\n",
        "} events_context{};\n\n" + QUEUE_FUNCTIONS,
        "post-definition queue snapshot functions",
    )
    src = once(
        src,
        "        jp_event_gfx_tasks_pending.fetch_add(1, std::memory_order_release);\n"
        "        events_context.action_queue.enqueue(SpTaskAction{ *task });\n",
        "        jp_gfx_tasks_submitted.fetch_add(1, std::memory_order_relaxed);\n"
        "        jp_event_gfx_tasks_pending.fetch_add(1, std::memory_order_release);\n"
        "        events_context.action_queue.enqueue(SpTaskAction{ *task });\n",
        "count graphics submission before queue publication",
    )
    src = once(
        src,
        "            if (const auto* task_action = std::get_if<SpTaskAction>(&action)) {\n",
        "            if (const auto* task_action = std::get_if<SpTaskAction>(&action)) {\n"
        "                jp_gfx_tasks_started.fetch_add(1, std::memory_order_relaxed);\n",
        "graphics work dequeued from action queue",
    )
    src = once(
        src,
        "                ultramodern::extensions::on_displaylist_completed(displaylist);\n"
        "                jp_event_gfx_tasks_pending.fetch_sub(1, std::memory_order_release);\n",
        "                ultramodern::extensions::on_displaylist_completed(displaylist);\n"
        "                jp_gfx_tasks_completed.fetch_add(1, std::memory_order_release);\n"
        "                jp_event_gfx_tasks_pending.fetch_sub(1, std::memory_order_release);\n",
        "graphics task processing completed",
    )
    src = once(
        src,
        '        "pending_gfx=%llu pending_sp=%llu; event-only shutdown.\\n",\n'
        '        static_cast<unsigned long long>(jp_event_gfx_tasks_pending.load(std::memory_order_acquire)),\n'
        '        static_cast<unsigned long long>(jp_event_sp_tasks_pending.load(std::memory_order_acquire)));\n',
        '        "pending_gfx=%llu pending_sp=%llu; event-only shutdown.\\n",\n'
        '        static_cast<unsigned long long>(jp_event_gfx_tasks_pending.load(std::memory_order_acquire)),\n'
        '        static_cast<unsigned long long>(jp_event_sp_tasks_pending.load(std::memory_order_acquire)));\n'
        '    // Snapshot only, after native event joins. Never dequeue or replay\n'
        '    // action records while guest producers may remain alive.\n'
        '    ultramodern::jp_report_graphics_queue_settlement();\n',
        "report pending queue after verified normal event joins",
    )
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    for filename, transform in (
        ("threads.cpp", stage6.stage5.instrument_threads),
        ("mesgqueue.cpp", stage6.stage5.stage4.instrument_messages),
        ("scheduling.cpp", stage6.stage5.instrument_scheduler),
        ("events.cpp", instrument_events),
    ):
        source = args.runtime / "ultramodern/src" / filename
        dest = args.output / filename
        changed = stage6.stage5.stage4.stage3.write_if_changed(
            dest, transform(source.read_text(encoding="utf-8"))
        )
        print(f"[JP graphics stage8] {'Updated' if changed else 'Unchanged'}: {dest}")


if __name__ == "__main__":
    main()
