#!/usr/bin/env python3
"""Stage 4: observable guest queue waits and bounded thread-cleaner drain.

This patcher generates build-local sources from the pinned N64ModernRuntime.
It composes the stage-3 audit/stop scaffolding without enabling the stop
request, resetting RDRAM, or restarting the game. It does not edit submodules.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def import_stage3():
    path = Path(__file__).with_name("patch_guest_quiescence_stage3.py")
    spec = importlib.util.spec_from_file_location("jp_guest_stage3", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing stage-3 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage3 = import_stage3()


def once(src: str, old: str, new: str, reason: str) -> str:
    return stage3.replace_once(src, old, new, reason)


def instrument_threads(original: str) -> str:
    src = stage3.instrument_threads(original)
    src = once(
        src,
        "    while (!exited) {\n        UltraThreadContext* to_delete;\n",
        "    // On normal process shutdown, drain already-completed guest threads\n"
        "    // until the deletion queue has remained empty for one poll interval.\n"
        "    // This does NOT imply all live guest threads have stopped.\n"
        "    while (true) {\n        UltraThreadContext* to_delete;\n",
        "cleaner drain loop",
    )
    src = once(
        src,
        "            jp_guest_threads_joined.fetch_add(1, std::memory_order_relaxed);\n"
        "            delete to_delete;\n"
        "        }\n"
        "    }\n"
        "}\n\n"
        "void ultramodern::init_thread_cleanup()",
        "            jp_guest_threads_joined.fetch_add(1, std::memory_order_relaxed);\n"
        "            delete to_delete;\n"
        "        } else if (exited.load(std::memory_order_acquire)) {\n"
        "            // No completed guest thread has arrived for 10 ms.\n"
        "            // Later completions are STILL possible: never use this\n"
        "            // diagnostic as an RDRAM-reset safety barrier.\n"
        "            break;\n"
        "        }\n"
        "    }\n"
        "    const auto created = jp_guest_threads_created.load(std::memory_order_acquire);\n"
        "    const auto finished = jp_guest_threads_finished.load(std::memory_order_acquire);\n"
        "    const auto joined = jp_guest_threads_joined.load(std::memory_order_acquire);\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP cleaner] created=%llu finished=%llu joined=%llu \"\n"
        "        \"active=%llu unjoined=%llu; queue drained, guest shutdown NOT proven.\\n\",\n"
        "        static_cast<unsigned long long>(created),\n"
        "        static_cast<unsigned long long>(finished),\n"
        "        static_cast<unsigned long long>(joined),\n"
        "        static_cast<unsigned long long>(jp_saturating_difference(created, finished)),\n"
        "        static_cast<unsigned long long>(jp_saturating_difference(finished, joined)));\n"
        "}\n\n"
        "void ultramodern::init_thread_cleanup()",
        "cleaner normal-exit diagnostic",
    )
    return src


QUEUE_PROBE = r"""// JP stage-4 diagnostics only: no guest reset or message mutation.
static std::atomic<uint64_t> jp_send_waits{0};
static std::atomic<uint64_t> jp_recv_waits{0};
static std::atomic<uint64_t> jp_active_senders{0};
static std::atomic<uint64_t> jp_active_receivers{0};
static std::atomic<uint64_t> jp_external_waits{0};

struct JpQueueWaitScope {
    std::atomic<uint64_t>& counter;
    explicit JpQueueWaitScope(std::atomic<uint64_t>& counter_) : counter(counter_) {
        counter.fetch_add(1, std::memory_order_relaxed);
    }
    ~JpQueueWaitScope() {
        counter.fetch_sub(1, std::memory_order_relaxed);
    }
    JpQueueWaitScope(const JpQueueWaitScope&) = delete;
    JpQueueWaitScope& operator=(const JpQueueWaitScope&) = delete;
};

void ultramodern::report_guest_message_queue_waits() {
    std::fprintf(stderr,
        "[Goemon JP queue audit] send_waits=%llu recv_waits=%llu "
        "blocked_send=%llu blocked_recv=%llu external_timeouts=%llu; "
        "reset not armed.\n",
        static_cast<unsigned long long>(jp_send_waits.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(jp_recv_waits.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(jp_active_senders.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(jp_active_receivers.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(jp_external_waits.load(std::memory_order_relaxed)));
}

"""


def instrument_messages(original: str) -> str:
    src = original
    src = once(src, "#include <thread>\n",
               "#include <thread>\n#include <atomic>\n#include <chrono>\n#include <cstdint>\n#include <cstdio>\n",
               "message audit include")
    src = once(
        src,
        '#include "ultramodern/ultramodern.hpp"\n',
        '#include "ultramodern/ultramodern.hpp"\n\n'
        'namespace ultramodern { void report_guest_message_queue_waits(); '
        'void guest_shutdown_checkpoint(); }\n',
        "queue audit declarations",
    )
    src = once(src, "struct QueuedMessage {\n",
               QUEUE_PROBE + "struct QueuedMessage {\n",
               "queue audit state")
    # The original indefinite external wait must become bounded so the
    # stage-3 checkpoint can eventually observe a future stop request.
    # Stop is not armed in this version; the game remains unchanged.
    src = once(
        src,
        "    external_messages.wait_dequeue(to_send);\n"
        "    if (!do_send(PASS_RDRAM to_send.mq, to_send.mesg, to_send.jam, false)",
        "    while (!external_messages.wait_dequeue_timed(\n"
        "        to_send, std::chrono::milliseconds{10})) {\n"
        "        jp_external_waits.fetch_add(1, std::memory_order_relaxed);\n"
        "        ultramodern::guest_shutdown_checkpoint();\n"
        "    }\n"
        "    ultramodern::guest_shutdown_checkpoint();\n"
        "    if (!do_send(PASS_RDRAM to_send.mq, to_send.mesg, to_send.jam, false)",
        "bounded external wait with cooperative checkpoint",
    )
    # The timed external dequeue is also a guest-yield boundary.
    # Recheck cancellation after waiting, regardless of whether a message
    # arrived. Never access an old OSMesgQueue after a shutdown request.
    src = once(
        src,
        "    if (external_messages.wait_dequeue_timed(to_send, std::chrono::milliseconds{millis})) {\n",
        "    if (external_messages.wait_dequeue_timed(to_send, std::chrono::milliseconds{millis})) {\n"
        "        ultramodern::guest_shutdown_checkpoint();\n",
        "timed external dequeue success checkpoint",
    )
    src = once(
        src,
        "            external_messages.enqueue(to_send);\n"
        "        }\n"
        "    }\n"
        "}\n\n"
        "extern \"C\" void osCreateMesgQueue(",
        "            external_messages.enqueue(to_send);\n"
        "        }\n"
        "    }\n"
        "    ultramodern::guest_shutdown_checkpoint();\n"
        "}\n\n"
        "extern \"C\" void osCreateMesgQueue(",
        "timed external dequeue timeout checkpoint",
    )
    src = once(
        src,
        '            ultramodern::thread_queue_insert(PASS_RDRAM GET_MEMBER(OSMesgQueue, mq_, blocked_on_send), ultramodern::this_thread());\n'
        '            ultramodern::run_next_thread_and_wait(PASS_RDRAM1);\n',
        '            ultramodern::thread_queue_insert(PASS_RDRAM GET_MEMBER(OSMesgQueue, mq_, blocked_on_send), ultramodern::this_thread());\n'
        '            jp_send_waits.fetch_add(1, std::memory_order_relaxed);\n'
        '            JpQueueWaitScope blocked(jp_active_senders);\n'
        '            ultramodern::run_next_thread_and_wait(PASS_RDRAM1);\n',
        "send blocked-guest audit",
    )
    src = once(
        src,
        '            ultramodern::thread_queue_insert(PASS_RDRAM GET_MEMBER(OSMesgQueue, mq_, blocked_on_recv), ultramodern::this_thread());\n'
        '            ultramodern::run_next_thread_and_wait(PASS_RDRAM1);\n',
        '            ultramodern::thread_queue_insert(PASS_RDRAM GET_MEMBER(OSMesgQueue, mq_, blocked_on_recv), ultramodern::this_thread());\n'
        '            jp_recv_waits.fetch_add(1, std::memory_order_relaxed);\n'
        '            JpQueueWaitScope blocked(jp_active_receivers);\n'
        '            ultramodern::run_next_thread_and_wait(PASS_RDRAM1);\n',
        "receive blocked-guest audit",
    )
    return "// Generated JP queue audit; source submodule is unchanged.\n" + src


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sources = (
        (args.runtime / "ultramodern/src/threads.cpp",
         args.output / "threads.cpp", instrument_threads),
        (args.runtime / "ultramodern/src/mesgqueue.cpp",
         args.output / "mesgqueue.cpp", instrument_messages),
    )
    for source_path, dest_path, patch in sources:
        output = patch(source_path.read_text(encoding="utf-8"))
        changed = stage3.write_if_changed(dest_path, output)
        print(f"[JP queue stage4] {'Updated' if changed else 'Unchanged'}: {dest_path}")


if __name__ == "__main__":
    main()
