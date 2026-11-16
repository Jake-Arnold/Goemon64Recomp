#!/usr/bin/env python3
"""Build-tree-only stage-3 guest shutdown primitives for pinned N64ModernRuntime.

Stage 2 counts guest OSThreads. Stage 3 tracks their contexts, provides
cooperative stop checks at native scheduling points, and prepares an explicit
stop request. No production code CALLS the stop request in this stage. F8
remains a diagnostic. In particular, no memory clearing is permitted.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage2():
    path = Path(__file__).with_name("patch_guest_threads_runtime.py")
    spec = importlib.util.spec_from_file_location("jp_thread_stage2", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing pinned stage-2 guest-thread generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage2 = load_stage2()


def replace_once(src: str, old: str, new: str, label: str) -> str:
    return stage2.replace_once(src, old, new, label)


def instrument_threads(original: str) -> str:
    src = stage2.instrument_threads(original)
    src = replace_once(
        src,
        "#include <cstdint>\n",
        "#include <cstdint>\n#include <mutex>\n#include <unordered_set>\n",
        "stage3 guest-registry headers",
    )
    src = replace_once(
        src,
        "namespace ultramodern { void report_guest_thread_reset_blockers(); }\n",
        "namespace ultramodern { void report_guest_thread_reset_blockers(); }\n"
        "namespace ultramodern {\n"
        "    void report_guest_shutdown_readiness();\n"
        "    void request_guest_shutdown_for_future_reset();\n"
        "    void guest_shutdown_checkpoint();\n"
        "}\n",
        "stage3 namespace declarations",
    )

    anchor = "void ultramodern::threads::set_callbacks(const callbacks_t& callbacks) {\n"
    additions = """// This registry owns no contexts. It is consulted only while guest RDRAM
// is intact; contexts are removed AFTER their host threads have joined.
// This is preparation for a later reset barrier, not the barrier itself.
static std::mutex jp_guest_context_mutex;
static std::unordered_set<UltraThreadContext*> jp_guest_contexts;
static std::atomic<bool> jp_guest_stop_requested{false};
static std::atomic<uint64_t> jp_guest_creations_in_flight{0};

void ultramodern::report_guest_shutdown_readiness() {
    std::lock_guard<std::mutex> lock(jp_guest_context_mutex);
    std::fprintf(stderr,
        "[Goemon JP guest stop] tracked=%zu spawning=%llu stop=%s; "
        "guest stop and memory reset disabled.\\n",
        jp_guest_contexts.size(),
        static_cast<unsigned long long>(
            jp_guest_creations_in_flight.load(std::memory_order_relaxed)),
        jp_guest_stop_requested.load(std::memory_order_acquire)
            ? "requested" : "not-armed");
}

// NOT EXPOSED IN THE GAME UI. This primitive is incomplete until the
// renderer/RSP/event queues and main game entry thread can also quiesce.
// A later stage must coordinate reset ownership BEFORE calling this.
// Never unmap, memset, or re-enter the game based on this call alone.
void ultramodern::request_guest_shutdown_for_future_reset() {
    std::lock_guard<std::mutex> lock(jp_guest_context_mutex);
    jp_guest_stop_requested.store(true, std::memory_order_release);
    for (UltraThreadContext* context : jp_guest_contexts) {
        context->running.signal();
    }
}

// Cooperative checkpoint: only valid for threads running in the
// native OSThread trampoline, where thread_terminated is caught.
void ultramodern::guest_shutdown_checkpoint() {
    if (thread_self != NULLPTR &&
        jp_guest_stop_requested.load(std::memory_order_acquire)) {
        throw ultramodern::thread_terminated{};
    }
}

"""
    # thread_self must be declared before guest_shutdown_checkpoint.
    # Insert after its thread_local definition, not before callbacks.
    src = replace_once(
        src,
        "thread_local PTR(OSThread) thread_self = NULLPTR;\n",
        "thread_local PTR(OSThread) thread_self = NULLPTR;\n\n" + additions,
        "stage3 registry and cooperative shutdown declarations",
    )

    src = replace_once(
        src,
        "void wait_for_resumed(RDRAM_ARG UltraThreadContext* thread_context) {\n"
        "    thread_context->running.wait();\n",
        "void wait_for_resumed(RDRAM_ARG UltraThreadContext* thread_context) {\n"
        "    thread_context->running.wait();\n"
        "    // The wake may be a shutdown signal rather than N64 scheduling.\n"
        "    ultramodern::guest_shutdown_checkpoint();\n",
        "scheduler semaphore checkpoint",
    )
    src = replace_once(
        src,
        "    if (self->context == thread_context) {\n"
        '        debug_printf("[Thread] Thread started: %d\\n", self->id);\n',
        "    if (!jp_guest_stop_requested.load(std::memory_order_acquire) &&\n"
        "        self->context == thread_context) {\n"
        '        debug_printf("[Thread] Thread started: %d\\n", self->id);\n',
        "skip guest entrypoint after stop",
    )
    src = replace_once(
        src,
        "        self->context = nullptr;\n"
        "        run_next_thread(PASS_RDRAM1);\n",
        "        self->context = nullptr;\n"
        "        // A shutdown wake is NOT an invitation to schedule another guest.\n"
        "        if (!jp_guest_stop_requested.load(std::memory_order_acquire)) {\n"
        "            run_next_thread(PASS_RDRAM1);\n"
        "        }\n",
        "skip scheduling successor after stop",
    )
    src = replace_once(
        src,
        "void ultramodern::run_next_thread_and_wait(RDRAM_ARG1) {\n",
        "void ultramodern::run_next_thread_and_wait(RDRAM_ARG1) {\n"
        "    ultramodern::guest_shutdown_checkpoint();\n",
        "yield scheduling checkpoint",
    )
    src = replace_once(
        src,
        "void ultramodern::resume_thread_and_wait(RDRAM_ARG OSThread *t) {\n",
        "void ultramodern::resume_thread_and_wait(RDRAM_ARG OSThread *t) {\n"
        "    ultramodern::guest_shutdown_checkpoint();\n",
        "explicit scheduling checkpoint",
    )

    # Registration precedes std::thread creation. The lock also serialises
    # registering new guest workers with a possible future stop request.
    src = replace_once(
        src,
        "    UltraThreadContext* context = new UltraThreadContext{};\n"
        "    t->context = context;\n",
        "    jp_guest_creations_in_flight.fetch_add(1, std::memory_order_relaxed);\n"
        "    UltraThreadContext* context = new UltraThreadContext{};\n"
        "    {\n"
        "        std::lock_guard<std::mutex> lock(jp_guest_context_mutex);\n"
        "        if (jp_guest_stop_requested.load(std::memory_order_acquire)) {\n"
        "            jp_guest_creations_in_flight.fetch_sub(1, std::memory_order_relaxed);\n"
        "            delete context;\n"
        "            throw ultramodern::thread_terminated{};\n"
        "        }\n"
        "        jp_guest_contexts.insert(context);\n"
        "    }\n"
        "    t->context = context;\n",
        "register guest context before host spawn",
    )
    src = replace_once(
        src,
        "    context->initialized.wait();\n"
        "    jp_guest_threads_created.fetch_add(1, std::memory_order_relaxed);\n",
        "    context->initialized.wait();\n"
        "    jp_guest_threads_created.fetch_add(1, std::memory_order_relaxed);\n"
        "    jp_guest_creations_in_flight.fetch_sub(1, std::memory_order_release);\n",
        "track in-flight guest host creation",
    )
    src = replace_once(
        src,
        "            to_delete->host_thread.join();\n"
        "            jp_guest_threads_joined.fetch_add(1, std::memory_order_relaxed);\n",
        "            to_delete->host_thread.join();\n"
        "            {\n"
        "                std::lock_guard<std::mutex> lock(jp_guest_context_mutex);\n"
        "                jp_guest_contexts.erase(to_delete);\n"
        "            }\n"
        "            jp_guest_threads_joined.fetch_add(1, std::memory_order_relaxed);\n",
        "retire guest registry only after host join",
    )
    return src


def write_if_changed(path: Path, content: str) -> bool:
    return stage2.write_if_changed(path, content)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runtime", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    source = (args.runtime / "ultramodern/src/threads.cpp").read_text(encoding="utf-8")
    output = args.output / "threads.cpp"
    changed = write_if_changed(output, instrument_threads(source))
    print(f"[JP guest stop] {'Updated' if changed else 'Unchanged'}: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
