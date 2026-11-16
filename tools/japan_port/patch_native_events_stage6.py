#!/usr/bin/env python3
"""JP reset stage 6: read-only native event-worker and task lifecycle audit.

The original N64ModernRuntime submodule remains untouched. This composes
stage 5's generated guest-thread sources with an opt-in generated events.cpp.
No stage-6 function requests shutdown, stops a worker or resets guest RAM.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage5():
    path = Path(__file__).with_name("patch_guest_join_stage5.py")
    spec = importlib.util.spec_from_file_location("jp_stage5", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing pinned stage-5 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage5 = load_stage5()


def once(src: str, old: str, new: str, label: str) -> str:
    return stage5.once(src, old, new, label)


EVENT_STATE = r"""// JP stage6 event-worker census. These flags only describe native
// VI, RT64 graphics and SP/RSP-task host workers, NOT guest OSThreads.
static std::atomic_bool jp_event_workers_initialized{false};
static std::atomic_bool jp_event_vi_active{false};
static std::atomic_bool jp_event_gfx_active{false};
static std::atomic_bool jp_event_sp_active{false};
static std::atomic_bool jp_event_vi_joined{false};
static std::atomic_bool jp_event_gfx_joined{false};
static std::atomic_bool jp_event_sp_joined{false};
// Pending includes tasks being processed. A queued graphics ScreenUpdateAction
// is not counted because it is not an N64 RSP task.
static std::atomic<uint64_t> jp_event_gfx_tasks_pending{0};
static std::atomic<uint64_t> jp_event_sp_tasks_pending{0};

struct JpEventWorkerScope {
    std::atomic_bool& active;
    explicit JpEventWorkerScope(std::atomic_bool& flag) : active(flag) {
        active.store(true, std::memory_order_release);
    }
    ~JpEventWorkerScope() {
        active.store(false, std::memory_order_release);
    }
    JpEventWorkerScope(const JpEventWorkerScope&) = delete;
    JpEventWorkerScope& operator=(const JpEventWorkerScope&) = delete;
};

bool ultramodern::jp_event_workers_joined_for_future_reset() {
    // Event-only predicate. It DOES NOT cover native boot, audio, saving,
    // guest workers, timers, or pending display/action queue records.
    return jp_event_workers_initialized.load(std::memory_order_acquire) &&
        jp_event_vi_joined.load(std::memory_order_acquire) &&
        jp_event_gfx_joined.load(std::memory_order_acquire) &&
        jp_event_sp_joined.load(std::memory_order_acquire) &&
        !jp_event_vi_active.load(std::memory_order_acquire) &&
        !jp_event_gfx_active.load(std::memory_order_acquire) &&
        !jp_event_sp_active.load(std::memory_order_acquire) &&
        jp_event_gfx_tasks_pending.load(std::memory_order_acquire) == 0 &&
        jp_event_sp_tasks_pending.load(std::memory_order_acquire) == 0;
}

void ultramodern::jp_report_native_event_worker_blockers() {
    std::fprintf(stderr,
        "[Goemon JP native workers] vi=%u gfx=%u sp=%u "
        "pending_gfx=%llu pending_sp=%llu joined=%u/%u/%u; "
        "event-only audit, RDRAM reset unavailable.\n",
        static_cast<unsigned>(jp_event_vi_active.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_event_gfx_active.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_event_sp_active.load(std::memory_order_acquire)),
        static_cast<unsigned long long>(jp_event_gfx_tasks_pending.load(std::memory_order_acquire)),
        static_cast<unsigned long long>(jp_event_sp_tasks_pending.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_event_vi_joined.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_event_gfx_joined.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_event_sp_joined.load(std::memory_order_acquire)));
}

"""


def instrument_events(original: str) -> str:
    marker = "// Generated JP native event-worker audit; pinned submodule unchanged."
    if marker in original or "jp_event_workers_initialized" in original:
        raise ValueError("JP stage-6 event instrumentation already applied")
    src = original
    src = once(
        src, "#include <cstring>\n",
        "#include <cstring>\n#include <cstdio>\n",
        "native event audit stdio include",
    )
    src = once(
        src, '#include "ultramodern/renderer_context.hpp"\n',
        '#include "ultramodern/renderer_context.hpp"\n'
        "namespace ultramodern {\n"
        "    void jp_report_native_event_worker_blockers();\n"
        "    bool jp_event_workers_joined_for_future_reset();\n"
        "}\n",
        "native event audit public declarations",
    )
    src = once(
        src,
        "static ultramodern::events::callbacks_t events_callbacks{};\n",
        EVENT_STATE + "static ultramodern::events::callbacks_t events_callbacks{};\n",
        "event lifecycle state",
    )
    for signature,flag in (
        ("void vi_thread_func() {\n", "jp_event_vi_active"),
        ("void task_thread_func(uint8_t* rdram, moodycamel::LightweightSemaphore* thread_ready) {\n", "jp_event_sp_active"),
        ("void gfx_thread_func(uint8_t* rdram, moodycamel::LightweightSemaphore* thread_ready, ultramodern::renderer::WindowHandle window_handle) {\n", "jp_event_gfx_active"),
    ):
        src = once(
            src, signature,
            signature + f"    JpEventWorkerScope jp_worker_scope({flag});\n",
            f"{flag} worker RAII lifetime",
        )
    # The producer increments before it exposes the work to the consumer.
    src = once(
        src,
        "        events_context.action_queue.enqueue(SpTaskAction{ *task });\n",
        "        jp_event_gfx_tasks_pending.fetch_add(1, std::memory_order_release);\n"
        "        events_context.action_queue.enqueue(SpTaskAction{ *task });\n",
        "graphics task submission count",
    )
    src = once(
        src,
        "        events_context.sp_task_queue.enqueue(task);\n",
        "        jp_event_sp_tasks_pending.fetch_add(1, std::memory_order_release);\n"
        "        events_context.sp_task_queue.enqueue(task);\n",
        "SP task submission count",
    )
    src = once(
        src,
        "                ultramodern::extensions::on_displaylist_completed(displaylist);\n",
        "                ultramodern::extensions::on_displaylist_completed(displaylist);\n"
        "                jp_event_gfx_tasks_pending.fetch_sub(1, std::memory_order_release);\n",
        "graphics task completion count",
    )
    src = once(
        src,
        "        // Tell the game that the RSP has completed\n"
        "        sp_complete();\n",
        "        // Tell the game that the RSP has completed\n"
        "        sp_complete();\n"
        "        jp_event_sp_tasks_pending.fetch_sub(1, std::memory_order_release);\n",
        "SP task completion count",
    )
    src = once(
        src,
        "void ultramodern::init_events(RDRAM_ARG ultramodern::renderer::WindowHandle window_handle) {\n",
        "void ultramodern::init_events(RDRAM_ARG ultramodern::renderer::WindowHandle window_handle) {\n"
        "    jp_event_workers_initialized.store(false, std::memory_order_release);\n"
        "    jp_event_vi_joined.store(false, std::memory_order_release);\n"
        "    jp_event_gfx_joined.store(false, std::memory_order_release);\n"
        "    jp_event_sp_joined.store(false, std::memory_order_release);\n",
        "initial event state",
    )
    src = once(
        src,
        "    events_context.vi.thread = std::thread{ vi_thread_func };\n",
        "    events_context.vi.thread = std::thread{ vi_thread_func };\n"
        "    jp_event_workers_initialized.store(true, std::memory_order_release);\n",
        "event worker launch ready",
    )
    src = once(
        src,
        "    events_context.sp.gfx_thread.join();\n"
        "    events_context.vi.thread.join();\n\n"
        "    // Send a null RSP task to indicate that the RSP task thread should exit.\n"
        "    events_context.sp_task_queue.enqueue(nullptr);\n"
        "    events_context.sp.task_thread.join();\n",
        "    events_context.sp.gfx_thread.join();\n"
        "    jp_event_gfx_joined.store(true, std::memory_order_release);\n"
        "    events_context.vi.thread.join();\n"
        "    jp_event_vi_joined.store(true, std::memory_order_release);\n\n"
        "    // Keep the proven shutdown order; the sentinel releases the SP task worker.\n"
        "    events_context.sp_task_queue.enqueue(nullptr);\n"
        "    events_context.sp.task_thread.join();\n"
        "    jp_event_sp_joined.store(true, std::memory_order_release);\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 \"\n"
        "        \"pending_gfx=%llu pending_sp=%llu; event-only shutdown.\\n\",\n"
        "        static_cast<unsigned long long>(jp_event_gfx_tasks_pending.load(std::memory_order_acquire)),\n"
        "        static_cast<unsigned long long>(jp_event_sp_tasks_pending.load(std::memory_order_acquire)));\n",
        "ordered native event joins",
    )
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sources = (
        ("threads.cpp", stage5.instrument_threads),
        ("mesgqueue.cpp", stage5.stage4.instrument_messages),
        ("scheduling.cpp", stage5.instrument_scheduler),
        ("events.cpp", instrument_events),
    )
    for filename, instrument in sources:
        path = args.runtime / "ultramodern/src" / filename
        output = args.output / filename
        changed = stage5.stage4.stage3.write_if_changed(
            output, instrument(path.read_text(encoding="utf-8"))
        )
        print(f"[JP native stage6] {'Updated' if changed else 'Unchanged'}: {output}")


if __name__ == "__main__":
    main()
