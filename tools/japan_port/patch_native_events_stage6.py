#!/usr/bin/env python3
"""JP v0.2.11 reset stage 6: native VI/RSP/RT64 event-worker audit.

This source overlay is an opt-in, read-only lifetime and busy-state
instrumentation of pinned N64ModernRuntime events.cpp. It does NOT
terminate workers, suspend the renderer, reset RDRAM, or re-enter boot.
"""
from __future__ import annotations

import argparse
from pathlib import Path


MARKER = "// Generated JP native event worker audit; original runtime unmodified."


def once(source: str, before: str, after: str, reason: str) -> str:
    count = source.count(before)
    if count != 1:
        raise ValueError(f"{reason}: pinned runtime changed (matches={count})")
    return source.replace(before, after, 1)


STATE = r"""// Worker-mask semantics:
//   0x1 = VI producer, 0x2 = RT64 gfx consumer, 0x4 = RSP task consumer.
// These are HOST threads, not the N64 OSThreads in the guest registry.
// A zero busy mask is only a momentary sample, NEVER a reset barrier.
static constexpr unsigned JP_EVENT_VI = 0x1u;
static constexpr unsigned JP_EVENT_GFX = 0x2u;
static constexpr unsigned JP_EVENT_RSP = 0x4u;
static constexpr unsigned JP_EVENT_ALL = JP_EVENT_VI | JP_EVENT_GFX | JP_EVENT_RSP;
static std::atomic<unsigned> jp_event_started{0};
static std::atomic<unsigned> jp_event_active{0};
static std::atomic<unsigned> jp_event_busy{0};
static std::atomic<unsigned> jp_event_joined{0};

struct JpEventWorkerLifetime {
    unsigned bit;
    explicit JpEventWorkerLifetime(unsigned value) : bit(value) {
        jp_event_started.fetch_or(bit, std::memory_order_release);
        jp_event_active.fetch_or(bit, std::memory_order_release);
    }
    ~JpEventWorkerLifetime() {
        jp_event_active.fetch_and(~bit, std::memory_order_release);
    }
    JpEventWorkerLifetime(const JpEventWorkerLifetime&) = delete;
    JpEventWorkerLifetime& operator=(const JpEventWorkerLifetime&) = delete;
};

struct JpEventWorkerBusy {
    unsigned bit;
    explicit JpEventWorkerBusy(unsigned value) : bit(value) {
        jp_event_busy.fetch_or(bit, std::memory_order_release);
    }
    ~JpEventWorkerBusy() {
        jp_event_busy.fetch_and(~bit, std::memory_order_release);
    }
    JpEventWorkerBusy(const JpEventWorkerBusy&) = delete;
    JpEventWorkerBusy& operator=(const JpEventWorkerBusy&) = delete;
};

void ultramodern::report_native_event_reset_blockers() {
    const unsigned started = jp_event_started.load(std::memory_order_acquire);
    const unsigned active = jp_event_active.load(std::memory_order_acquire);
    const unsigned busy = jp_event_busy.load(std::memory_order_acquire);
    const unsigned joined = jp_event_joined.load(std::memory_order_acquire);
    std::fprintf(stderr,
        "[Goemon JP native workers] started=0x%X active=0x%X busy=0x%X "
        "joined=0x%X; VI=1 gfx=2 RSP=4; reset disabled.\n",
        started, active, busy, joined);
}

void ultramodern::report_native_event_exit_status() {
    const unsigned started = jp_event_started.load(std::memory_order_acquire);
    const unsigned active = jp_event_active.load(std::memory_order_acquire);
    const unsigned busy = jp_event_busy.load(std::memory_order_acquire);
    const unsigned joined = jp_event_joined.load(std::memory_order_acquire);
    const bool event_threads_joined = started == JP_EVENT_ALL &&
        active == 0 && joined == JP_EVENT_ALL && busy == 0;
    std::fprintf(stderr,
        "[Goemon JP native exit] events_joined=%s started=0x%X active=0x%X "
        "busy=0x%X joined=0x%X; guest/start/save quiescence NOT proven.\n",
        event_threads_joined ? "yes" : "no", started, active, busy, joined);
}

"""


def instrument_events(source: str) -> str:
    if MARKER in source or "jp_event_started" in source:
        raise ValueError("JP stage-6 event worker audit already applied")
    src = once(
        source,
        "#include <thread>\n",
        "#include <thread>\n#include <cstdio>\n",
        "event worker diagnostics headers",
    )
    src = once(
        src,
        "static ultramodern::events::callbacks_t events_callbacks{};\n",
        "namespace ultramodern {\n"
        "    void report_native_event_reset_blockers();\n"
        "    void report_native_event_exit_status();\n"
        "}\n\n"
        "static ultramodern::events::callbacks_t events_callbacks{};\n",
        "event worker diagnostic function declarations",
    )
    src = once(
        src,
        "ultramodern::renderer::ViRegs* ultramodern::renderer::get_vi_regs() {\n",
        STATE + "ultramodern::renderer::ViRegs* ultramodern::renderer::get_vi_regs() {\n",
        "event worker lifetime state",
    )
    src = once(
        src,
        'void vi_thread_func() {\n    ultramodern::set_native_thread_name("VI Thread");\n',
        'void vi_thread_func() {\n'
        '    JpEventWorkerLifetime jp_event_lifetime(JP_EVENT_VI);\n'
        '    ultramodern::set_native_thread_name("VI Thread");\n',
        "VI worker lifetime",
    )
    src = once(
        src,
        'void task_thread_func(uint8_t* rdram, moodycamel::LightweightSemaphore* thread_ready) {\n'
        '    ultramodern::set_native_thread_name("SP Task Thread");\n',
        'void task_thread_func(uint8_t* rdram, moodycamel::LightweightSemaphore* thread_ready) {\n'
        '    JpEventWorkerLifetime jp_event_lifetime(JP_EVENT_RSP);\n'
        '    ultramodern::set_native_thread_name("SP Task Thread");\n',
        "RSP task worker lifetime",
    )
    src = once(
        src,
        "        if (task == nullptr) {\n            return;\n        }\n\n"
        "        if (!ultramodern::rsp::run_task(PASS_RDRAM task)) {\n",
        "        if (task == nullptr) {\n            return;\n        }\n\n"
        "        JpEventWorkerBusy jp_event_busy_scope(JP_EVENT_RSP);\n"
        "        if (!ultramodern::rsp::run_task(PASS_RDRAM task)) {\n",
        "RSP task in-flight scope",
    )
    src = once(
        src,
        "void gfx_thread_func(uint8_t* rdram, moodycamel::LightweightSemaphore* thread_ready, "
        "ultramodern::renderer::WindowHandle window_handle) {\n",
        "void gfx_thread_func(uint8_t* rdram, moodycamel::LightweightSemaphore* thread_ready, "
        "ultramodern::renderer::WindowHandle window_handle) {\n"
        "    JpEventWorkerLifetime jp_event_lifetime(JP_EVENT_GFX);\n",
        "RT64 gfx worker lifetime",
    )
    src = once(
        src,
        "            if (const auto* task_action = std::get_if<SpTaskAction>(&action)) {\n",
        "            if (const auto* task_action = std::get_if<SpTaskAction>(&action)) {\n"
        "                JpEventWorkerBusy jp_event_busy_scope(JP_EVENT_GFX);\n",
        "RT64 gfx in-flight task scope",
    )
    src = once(
        src,
        "void ultramodern::join_event_threads() {\n"
        "    events_context.sp.gfx_thread.join();\n"
        "    events_context.vi.thread.join();\n"
        "\n"
        "    // Send a null RSP task to indicate that the RSP task thread should exit.\n"
        "    events_context.sp_task_queue.enqueue(nullptr);\n"
        "    events_context.sp.task_thread.join();\n"
        "}\n",
        "void ultramodern::join_event_threads() {\n"
        "    events_context.sp.gfx_thread.join();\n"
        "    jp_event_joined.fetch_or(JP_EVENT_GFX, std::memory_order_release);\n"
        "    events_context.vi.thread.join();\n"
        "    jp_event_joined.fetch_or(JP_EVENT_VI, std::memory_order_release);\n"
        "\n"
        "    // Original RSP sentinel and join are preserved.\n"
        "    events_context.sp_task_queue.enqueue(nullptr);\n"
        "    events_context.sp.task_thread.join();\n"
        "    jp_event_joined.fetch_or(JP_EVENT_RSP, std::memory_order_release);\n"
        "    ultramodern::report_native_event_exit_status();\n"
        "}\n",
        "native event worker join confirmation",
    )
    return MARKER + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    src = args.runtime / "ultramodern/src/events.cpp"
    dest = args.output / "events.cpp"
    data = instrument_events(src.read_text(encoding="utf-8"))
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.read_text(encoding="utf-8") == data:
        print(f"[JP native stage6] Unchanged: {dest}")
        return
    temp = dest.with_suffix(".cpp.tmp")
    temp.write_text(data, encoding="utf-8")
    temp.replace(dest)
    print(f"[JP native stage6] Updated: {dest}")


if __name__ == "__main__":
    main()
