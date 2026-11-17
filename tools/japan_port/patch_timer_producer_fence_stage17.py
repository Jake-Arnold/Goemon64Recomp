#!/usr/bin/env python3
"""JP Stage17: fence timer API publishers before normal-exit timer join.

Pinned runtime sources are read but not edited. Stage1's generated timer.cpp
is composed with a producer gate. On normal app exit, osSetTimer and
osStopTimer are denied after gate closure, and joined worker + fully returned
producer permits are necessary before guest RDRAM can be unmapped. This is
NOT a live F8 stop or a timer rearm protocol.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage1():
    path = Path(__file__).with_name("patch_timer_runtime.py")
    spec = importlib.util.spec_from_file_location("jp_reset_timer_stage1_for17", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing pinned Stage1 timer generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage1 = load_stage1()


TIMER_PRODUCER_STATE = r"""// Stage17: count actual osSetTimer/osStopTimer enqueue publishers.
// The gate owns no guest pointers and is never closed by F8.
static goemon_jp::reset::PublisherGate jp_timer_publisher_gate{1};
static std::atomic_bool jp_timer_exit_gate_drained{false};
static std::atomic_bool jp_timer_exit_worker_joined{false};

void ultramodern::jp_report_timer_producer_stage17() {
    const auto state = jp_timer_publisher_gate.snapshot();
    std::fprintf(stderr,
        "[Goemon JP timer producer stage17] generation=%llu open=%u "
        "inflight=%llu accepted=%llu rejected=%llu "
        "f8_close=0 epoch_rearm=unproven; no live reset.\n",
        static_cast<unsigned long long>(state.generation),
        static_cast<unsigned>(state.open),
        static_cast<unsigned long long>(state.in_flight),
        static_cast<unsigned long long>(state.accepted),
        static_cast<unsigned long long>(state.rejected));
}

bool ultramodern::jp_timer_exit_joined_stage17() {
    // This must be checked only after shutdown_timers() has returned,
    // on the normal-exit owner thread. It is NOT a future rearm proof.
    const auto state = jp_timer_publisher_gate.snapshot();
    return jp_timer_exit_gate_drained.load(std::memory_order_acquire) &&
        jp_timer_exit_worker_joined.load(std::memory_order_acquire) &&
        !timer_context.thread.joinable() && !state.open &&
        state.in_flight == 0;
}

"""


def instrument_timer(original: str) -> str:
    marker = "// JP Stage17 timer publisher fence, generated from pinned runtime."
    if marker in original or "jp_timer_publisher_gate" in original:
        raise ValueError("Stage17 timer already instrumented")
    src = stage1.timer_source(original)
    replace = stage1.once
    src = replace(
        src,
        "#include <thread>\n#include <cstdio>\n",
        "#include <thread>\n#include <cstdio>\n"
        "#include <atomic>\n#include \"jp_generation_publisher_gate.hpp\"\n",
        "timer gate header inclusion",
    )
    src = replace(
        src,
        "namespace ultramodern { void shutdown_timers(); }\n",
        "namespace ultramodern { void shutdown_timers(); }\n"
        "namespace ultramodern {\n"
        "    void jp_report_timer_producer_stage17();\n"
        "    bool jp_timer_exit_joined_stage17();\n"
        "}\n",
        "timer producer report and exit proof forward declarations",
    )
    src = replace(
        src,
        "void ultramodern::init_timers(RDRAM_ARG1) {\n",
        TIMER_PRODUCER_STATE + "void ultramodern::init_timers(RDRAM_ARG1) {\n",
        "timer producer state before worker initializer",
    )
    src = replace(
        src,
        "void ultramodern::shutdown_timers() {\n"
        "    if (!timer_context.thread.joinable()) {\n",
        "void ultramodern::shutdown_timers() {\n"
        "    // PC exit only: close timer APIs before enqueuing ShutdownTimerAction.\n"
        "    // If a producer remains in-flight on timeout, fail closed and\n"
        "    // preserve RDRAM instead of pretending a worker join proves safety.\n"
        "    const bool jp_timer_publishers_done =\n"
        "        jp_timer_publisher_gate.close_for_pc_exit(\n"
        "            std::chrono::milliseconds{500});\n"
        "    jp_timer_exit_gate_drained.store(jp_timer_publishers_done,\n"
        "                                     std::memory_order_release);\n"
        "    if (!timer_context.thread.joinable()) {\n",
        "timer producer close before worker join",
    )
    src = replace(
        src,
        "    timer_context.thread.join();\n"
        "    Action stale_action;\n",
        "    timer_context.thread.join();\n"
        "    jp_timer_exit_worker_joined.store(true, std::memory_order_release);\n"
        "    Action stale_action;\n",
        "timer worker join must be an actual join",
    )
    src = replace(
        src,
        "    fprintf(stderr, \"[Goemon JP runtime] Timer worker joined cleanly.\\n\");\n",
        "    const auto jp_timer_exit_state = jp_timer_publisher_gate.snapshot();\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP timer exit stage17] producers_drained=%u \"\n"
        "        \"worker_joined=%u open=%u inflight=%llu accepted=%llu \"\n"
        "        \"rejected=%llu timer_safe=%u \"\n"
        "        \"epoch_rearm=unproven; normal PC exit only.\\n\",\n"
        "        static_cast<unsigned>(jp_timer_publishers_done),\n"
        "        static_cast<unsigned>(jp_timer_exit_worker_joined.load(std::memory_order_acquire)),\n"
        "        static_cast<unsigned>(jp_timer_exit_state.open),\n"
        "        static_cast<unsigned long long>(jp_timer_exit_state.in_flight),\n"
        "        static_cast<unsigned long long>(jp_timer_exit_state.accepted),\n"
        "        static_cast<unsigned long long>(jp_timer_exit_state.rejected),\n"
        "        static_cast<unsigned>(ultramodern::jp_timer_exit_joined_stage17()));\n"
        "    fprintf(stderr, \"[Goemon JP runtime] Timer worker joined cleanly.\\n\");\n",
        "post-join timer publisher proof log",
    )
    src = replace(
        src,
        "extern \"C\" int osSetTimer(RDRAM_ARG PTR(OSTimer) t_, OSTime countdown, OSTime interval, PTR(OSMesgQueue) mq, OSMesg msg) {\n",
        "extern \"C\" int osSetTimer(RDRAM_ARG PTR(OSTimer) t_, OSTime countdown, OSTime interval, PTR(OSMesgQueue) mq, OSMesg msg) {\n"
        "    // Permit covers guest timer memory writes and queue publication.\n"
        "    auto jp_timer_lease = jp_timer_publisher_gate.try_acquire();\n"
        "    if (!jp_timer_lease) return -1;\n",
        "timer guest-memory and enqueue fence",
    )
    src = replace(
        src,
        "extern \"C\" int osStopTimer(RDRAM_ARG PTR(OSTimer) t_) {\n",
        "extern \"C\" int osStopTimer(RDRAM_ARG PTR(OSTimer) t_) {\n"
        "    auto jp_timer_lease = jp_timer_publisher_gate.try_acquire();\n"
        "    if (!jp_timer_lease) return -1;\n",
        "timer stop enqueue fence",
    )
    return marker + "\n" + src


def instrument_recomp_after_stage12(stage12_source: str) -> str:
    marker = "// JP Stage17 exit-timer fence added after Stage12 census."
    if marker in stage12_source or "jp_timer_exit_joined_stage17" in stage12_source:
        raise ValueError("Stage17 RDRAM release guard already instrumented")
    if "// Generated JP stage12 post-join exit census" not in stage12_source:
        raise ValueError("Stage17 requires the actual generated Stage12 recomp source")
    replace = stage1.once
    src = replace(
        stage12_source,
        "namespace ultramodern { void shutdown_timers(); }\n",
        "namespace ultramodern { void shutdown_timers(); }\n"
        "namespace ultramodern { bool jp_timer_exit_joined_stage17(); }\n",
        "Stage17 exit timer proof declaration",
    )
    src = replace(
        src,
        "    if (jp_guest_exit_drained) {\n"
        "    // Free rdram.\n",
        "    // Stage17: RDRAM may only be released if timer API publishers\n"
        "    // also stopped before the joined timer worker was destroyed.\n"
        "    if (jp_guest_exit_drained &&\n"
        "        ultramodern::jp_timer_exit_joined_stage17()) {\n"
        "    // Free rdram.\n",
        "fail-closed RDRAM memory unmap guard",
    )
    src = replace(
        src,
        "guest join proof failed; OS process exit will reclaim it.",
        "guest/timer join or publisher proof failed; OS process exit will reclaim it.",
        "accurate RDRAM retained diagnosis",
    )
    src = replace(
        src,
        "        jp_exit_save_joined && jp_exit_audio_dispatch_idle;\n",
        "        jp_exit_save_joined && jp_exit_audio_dispatch_idle &&\n"
        "        ultramodern::jp_timer_exit_joined_stage17();\n",
        "full known-shutdown result additionally requires timer publisher fence",
    )
    return marker + "\n" + src


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--timer-source", type=Path, required=True)
    p.add_argument("--stage12-source", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    results = [
        (args.output_dir / "timer_stage17.cpp",
         instrument_timer(args.timer_source.read_text(encoding="utf-8"))),
        (args.output_dir / "recomp_stage17.cpp",
         instrument_recomp_after_stage12(args.stage12_source.read_text(encoding="utf-8"))),
    ]
    for dest, code in results:
        changed = stage1.write_if_changed(dest, code)
        print(f"[JP timer stage17] {'Updated' if changed else 'Unchanged'}: {dest}")


if __name__ == "__main__":
    main()
