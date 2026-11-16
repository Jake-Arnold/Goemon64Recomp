#!/usr/bin/env python3
"""JP stage 5: guarded guest-join readiness and scheduler stop gating.

Generated build-tree sources only, composing validated stage 4.  This
does NOT call the guest stop request, stop any game thread, clear RDRAM,
or restart the game. A future reset coordinator must first quiesce the
native boot, events, graphics, RSP, audio, timer and save workers.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def _load_stage4():
    path = Path(__file__).with_name("patch_queue_cleaner_stage4.py")
    spec = importlib.util.spec_from_file_location("jp_guest_stage4", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing stage-4 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage4 = _load_stage4()


def once(source: str, needle: str, replacement: str, label: str) -> str:
    return stage4.once(source, needle, replacement, label)


def instrument_threads(original: str) -> str:
    src = stage4.instrument_threads(original)
    # Stage 2 intentionally prefixes a forward declaration ahead of the
    # original C++ includes. The stage-5 API introduces std::uint32_t in
    # that early declaration, so <cstdint> must precede it.
    src = once(
        src,
        "// Generated JP guest-thread reset audit; original submodule not modified.\n",
        "// Generated JP guest-thread reset audit; original submodule not modified.\n"
        "#include <cstdint>\n",
        "early join API integer type include",
    )
    src = once(
        src,
        "#include <mutex>\n#include <unordered_set>\n",
        "#include <mutex>\n#include <condition_variable>\n#include <chrono>\n#include <unordered_set>\n",
        "join barrier headers",
    )
    src = once(
        src,
        "    void guest_shutdown_checkpoint();\n",
        "    void guest_shutdown_checkpoint();\n"
        "    bool guest_shutdown_requested_for_future_reset();\n"
        "    bool wait_for_guest_joins_for_future_reset(std::uint32_t timeout_ms);\n"
        "    void report_guest_join_barrier_readiness();\n",
        "join barrier namespace declarations",
    )
    src = once(
        src,
        "static std::mutex jp_guest_context_mutex;\n"
        "static std::unordered_set<UltraThreadContext*> jp_guest_contexts;\n",
        "static std::mutex jp_guest_context_mutex;\n"
        "static std::condition_variable jp_guest_join_cv;\n"
        "static std::unordered_set<UltraThreadContext*> jp_guest_contexts;\n",
        "join barrier state",
    )
    anchor = "// NOT EXPOSED IN THE GAME UI. This primitive is incomplete until the\n"
    api = r"""// Read-only scheduling gate: on a later coordinated stop, newly
// scheduled guest workers must never be enqueued after the stop request.
bool ultramodern::guest_shutdown_requested_for_future_reset() {
    return jp_guest_stop_requested.load(std::memory_order_acquire);
}

// This is ONLY the guest-host-thread join condition, never proof that RDRAM
// can be cleared: the native boot, renderer, RSP, VI, DMA, save, timer and
// other event workers are NOT included in this registry.
// No production code calls this method in v0.2.10.
bool ultramodern::wait_for_guest_joins_for_future_reset(std::uint32_t timeout_ms) {
    if (thread_self != NULLPTR ||
        !jp_guest_stop_requested.load(std::memory_order_acquire)) {
        return false; // Calling from a guest would wait on itself.
    }
    std::unique_lock<std::mutex> lock(jp_guest_context_mutex);
    return jp_guest_join_cv.wait_for(
        lock, std::chrono::milliseconds{timeout_ms}, [] {
            return jp_guest_stop_requested.load(std::memory_order_acquire) &&
                jp_guest_creations_in_flight.load(std::memory_order_acquire) == 0 &&
                jp_guest_contexts.empty() &&
                jp_guest_threads_created.load(std::memory_order_acquire) ==
                    jp_guest_threads_finished.load(std::memory_order_acquire) &&
                jp_guest_threads_finished.load(std::memory_order_acquire) ==
                    jp_guest_threads_joined.load(std::memory_order_acquire);
        });
}

// F8 only calls this report; it cannot stop workers.
void ultramodern::report_guest_join_barrier_readiness() {
    std::lock_guard<std::mutex> lock(jp_guest_context_mutex);
    const bool requested = jp_guest_stop_requested.load(std::memory_order_acquire);
    const auto spawned = jp_guest_creations_in_flight.load(std::memory_order_acquire);
    const auto finished = jp_guest_threads_finished.load(std::memory_order_acquire);
    const auto joined = jp_guest_threads_joined.load(std::memory_order_acquire);
    std::fprintf(stderr,
        "[Goemon JP join barrier] tracked=%zu spawning=%llu finished=%llu "
        "joined=%llu stop=%s; guest-only barrier not armed, RDRAM reset disabled.\n",
        jp_guest_contexts.size(),
        static_cast<unsigned long long>(spawned),
        static_cast<unsigned long long>(finished),
        static_cast<unsigned long long>(joined),
        requested ? "requested" : "not-armed");
}

"""
    src = once(src, anchor, api + anchor, "guarded join-only API")
    # Strictly stop new guest scheduling after any future stop request.
    src = once(
        src,
        'extern "C" void osCreateThread(RDRAM_ARG PTR(OSThread) t_, OSId id, PTR(thread_func_t) entrypoint, PTR(void) arg, PTR(void) sp, OSPri pri) {\n',
        'extern "C" void osCreateThread(RDRAM_ARG PTR(OSThread) t_, OSId id, PTR(thread_func_t) entrypoint, PTR(void) arg, PTR(void) sp, OSPri pri) {\n'
        '    if (ultramodern::guest_shutdown_requested_for_future_reset())\n'
        '        throw ultramodern::thread_terminated{};\n',
        "prevent new guest creation from touching RDRAM after stop",
    )
    src = once(
        src,
        'extern "C" void osStartThread(RDRAM_ARG PTR(OSThread) t_) {\n',
        'extern "C" void osStartThread(RDRAM_ARG PTR(OSThread) t_) {\n'
        '    if (ultramodern::guest_shutdown_requested_for_future_reset()) return;\n',
        "start guard",
    )
    # Rejection happens under the same mutex as a stop request; its wake
    # must notify an already waiting coordinator as the in-flight count falls.
    src = once(
        src,
        "            jp_guest_creations_in_flight.fetch_sub(1, std::memory_order_relaxed);\n"
        "            delete context;\n",
        "            jp_guest_creations_in_flight.fetch_sub(1, std::memory_order_relaxed);\n"
        "            jp_guest_join_cv.notify_all();\n"
        "            delete context;\n",
        "rejected creation notification",
    )
    src = once(
        src,
        "    jp_guest_creations_in_flight.fetch_sub(1, std::memory_order_release);\n"
        '    debug_printf("[os] Thread %d is ready to be started\\n", t->id);\n',
        "    jp_guest_creations_in_flight.fetch_sub(1, std::memory_order_release);\n"
        "    jp_guest_join_cv.notify_all();\n"
        '    debug_printf("[os] Thread %d is ready to be started\\n", t->id);\n',
        "successful creation notification",
    )
    # Finish event: registry removal is always after std::thread::join,
    # joined count is committed before notifying the waiter.
    src = once(
        src,
        "            jp_guest_threads_joined.fetch_add(1, std::memory_order_relaxed);\n"
        "            delete to_delete;\n",
        "            jp_guest_threads_joined.fetch_add(1, std::memory_order_release);\n"
        "            jp_guest_join_cv.notify_all();\n"
        "            delete to_delete;\n",
        "joined worker notification",
    )
    return src


def instrument_scheduler(original: str) -> str:
    # The pinned function signatures remain in generated output, so exact
    # anchor checks alone cannot detect a second patch application.
    marker = "// JP stage-5 scheduler stop gate; original submodule unchanged."
    declaration = "namespace ultramodern { bool guest_shutdown_requested_for_future_reset(); }"
    if marker in original or declaration in original:
        raise ValueError("Stage-5 scheduling stop gate already applied")
    src = original
    src = once(
        src, '#include "ultramodern/ultramodern.hpp"\n',
        '#include "ultramodern/ultramodern.hpp"\n'
        "namespace ultramodern { bool guest_shutdown_requested_for_future_reset(); }\n",
        "scheduler namespace gate",
    )
    for signature in (
        "void ultramodern::schedule_running_thread(RDRAM_ARG PTR(OSThread) t_) {\n",
        "void ultramodern::check_running_queue(RDRAM_ARG1) {\n",
    ):
        src = once(
            src, signature,
            signature + "    if (ultramodern::guest_shutdown_requested_for_future_reset()) return;\n",
            "stop gate in " + signature.split("(")[0],
        )
    return "// JP stage-5 scheduler stop gate; original submodule unchanged.\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sources = (
        ("threads.cpp", instrument_threads),
        ("mesgqueue.cpp", stage4.instrument_messages),
        ("scheduling.cpp", instrument_scheduler),
    )
    for filename, patch in sources:
        source = args.runtime / "ultramodern/src" / filename
        destination = args.output / filename
        changed = stage4.stage3.write_if_changed(
            destination, patch(source.read_text(encoding="utf-8"))
        )
        print(f"[JP join stage5] {'Updated' if changed else 'Unchanged'}: {destination}")


if __name__ == "__main__":
    main()
