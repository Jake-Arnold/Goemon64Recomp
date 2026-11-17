#!/usr/bin/env python3
"""Stage18: synchronize Japanese timer timebase; no production epoch rearm.

Compose the verified Stage17 generated timer, preserving its publisher
fence, worker join and guest memory guards. Replace the old unsynchronized
start_time/ostime_offset with a mutex-protected generation clock. F8 reads
only a snapshot. Generation transitions compile exclusively in the
standalone host-test binary, not the native game.
"""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path


def load_stage1():
    path = Path(__file__).with_name("patch_timer_runtime.py")
    spec = importlib.util.spec_from_file_location("jp_reset_timer_stage1_for18", path)
    if not spec or not spec.loader:
        raise RuntimeError("Missing Stage1 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage1 = load_stage1()


def instrument_stage17_timer(source: str) -> str:
    marker = "// JP Stage18 synchronized timer epoch clock; no production reset."
    if marker in source or "jp_timer_epoch_clock" in source:
        raise ValueError("Stage18 timer source already instrumented")
    if "// JP Stage17 timer publisher fence, generated from pinned runtime." not in source:
        raise ValueError("Stage18 requires the generated Stage17 timer source")
    replace = stage1.once
    src = replace(
        source,
        '#include <atomic>\n#include "jp_generation_publisher_gate.hpp"\n',
        '#include <atomic>\n#include "jp_generation_publisher_gate.hpp"\n'
        '#include "jp_timer_epoch_clock.hpp"\n',
        "Stage18 clock header after Stage17 publisher gate",
    )
    src = replace(
        src,
        '    bool jp_timer_exit_joined_stage17();\n',
        '    bool jp_timer_exit_joined_stage17();\n'
        '    void jp_report_timer_epoch_stage18();\n',
        "Stage18 report prototype",
    )
    src = replace(
        src,
        'static std::chrono::high_resolution_clock::time_point start_time = std::chrono::high_resolution_clock::now();\n',
        '// Stage18: timebase is owned by a synchronized per-generation clock.\n',
        "replace unguarded clock anchor",
    )
    src = replace(
        src,
        '// Offset of the duration since program start used to calculate the value for osGetTime. \n'
        'static int64_t ostime_offset = 0;\n',
        '',
        "replace unguarded guest osGetTime offset",
    )
    src = replace(
        src,
        "constexpr uint32_t counter_per_ms = 46'875 * speed_multiplier;\n",
        "constexpr uint32_t counter_per_ms = 46'875 * speed_multiplier;\n"
        "static goemon_jp::reset::TimerEpochClock jp_timer_epoch_clock{counter_per_ms};\n",
        "initialize JP clock after original tick-rate constant",
    )
    src = replace(
        src,
        '    return start_time + ticks_to_duration(ticks);\n',
        '    return jp_timer_epoch_clock.start() + ticks_to_duration(ticks);\n',
        "timer wake deadline tied to current clock epoch",
    )
    src = replace(
        src,
        '    return duration_to_ticks(std::chrono::high_resolution_clock::now() - start_time);\n',
        '    return jp_timer_epoch_clock.ticks_now();\n',
        "timer time_now uses guarded timebase",
    )
    src = replace(
        src,
        '    return start_time;\n',
        '    return jp_timer_epoch_clock.start();\n',
        "ultramodern clock origin",
    )
    src = replace(
        src,
        '    return std::chrono::high_resolution_clock::now() - start_time;\n',
        '    return jp_timer_epoch_clock.since_start();\n',
        "ultramodern elapsed time",
    )
    src = replace(
        src,
        '    uint64_t total_count = time_now() - ostime_offset;\n',
        '    uint64_t total_count = jp_timer_epoch_clock.guest_time();\n',
        "osGetTime synchronized with offset",
    )
    src = replace(
        src,
        '    ostime_offset = time_now() - t;\n',
        '    jp_timer_epoch_clock.set_guest_time(t);\n',
        "osSetTime synchronized with offset",
    )
    report = r"""// Stage18 live diagnostics: a snapshot, not a stop or generation rearm.
void ultramodern::jp_report_timer_epoch_stage18() {
    const auto epoch = jp_timer_epoch_clock.snapshot();
    std::fprintf(stderr,
        "[Goemon JP timer clock stage18] generation=%llu "
        "ticks=%llu guest_time=%llu synchronized=1 "
        "rearm_enabled=0 f8_no_change=1; native reset unavailable.\n",
        static_cast<unsigned long long>(epoch.generation),
        static_cast<unsigned long long>(epoch.ticks),
        static_cast<unsigned long long>(epoch.guest_time));
}

"""
    src = replace(
        src,
        'void ultramodern::jp_report_timer_producer_stage17() {\n',
        report + 'void ultramodern::jp_report_timer_producer_stage17() {\n',
        "Stage18 snapshot adjacent to Stage17 producer report",
    )
    if "ostime_offset" in src or "return start_time" in src:
        raise ValueError("Old unsynchronized timebase references remain")
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage17-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = instrument_stage17_timer(args.stage17_source.read_text(encoding="utf-8"))
    modified = stage1.write_if_changed(args.output, result)
    print(f"[JP timer epoch stage18] {'Updated' if modified else 'Unchanged'}: {args.output}")


if __name__ == "__main__":
    main()
