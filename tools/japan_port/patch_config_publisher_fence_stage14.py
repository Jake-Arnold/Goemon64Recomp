#!/usr/bin/env python3
"""JP Stage14 config-action producer fence composed atop Stage11.

The production config queue publisher acquires a counted RAII permit before
enqueueing. At NORMAL PC EXIT ONLY, Stage10's action drain now permanently
closes permit admission and waits for all accepted enqueue operations to
finish before clearing abandoned actions. Live F8 only reports gate state.
No live close, generation transition, RDRAM reset, or runtime submodule edit.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage11():
    path = Path(__file__).with_name("patch_live_preflight_stage11.py")
    spec = importlib.util.spec_from_file_location("jp_reset_stage11", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing Stage11 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage11 = load_stage11()
stage10 = stage11.stage10

GATE_REPORT = r"""// Stage14 counted config queue producer permits. This snapshot is
// read-only even when requested by F8 while the live worker is active.
void ultramodern::jp_report_config_action_producer_gate() {
    const auto state = jp_config_publisher_gate.snapshot();
    std::fprintf(stderr,
        "[Goemon JP config producer stage14] generation=%llu open=%u "
        "inflight=%llu accepted=%llu rejected=%llu "
        "f8_close=0; no reset or queue drain.\n",
        static_cast<unsigned long long>(state.generation),
        static_cast<unsigned>(state.open),
        static_cast<unsigned long long>(state.in_flight),
        static_cast<unsigned long long>(state.accepted),
        static_cast<unsigned long long>(state.rejected));
}

"""


def instrument_events(original: str) -> str:
    marker = "// Generated JP stage14 config producer fence; F8 observes only."
    if marker in original or "jp_config_publisher_gate" in original:
        raise ValueError("Stage14 producer fence already instrumented")
    src = stage11.instrument_events(original)

    src = stage10.once(
        src,
        "static std::mutex jp_config_action_publish_mutex;\n",
        "static goemon_jp::reset::PublisherGate jp_config_publisher_gate{1};\n"
        "static std::mutex jp_config_action_publish_mutex;\n",
        "stage14 guarded config producer gate state",
    )
    src = stage10.once(
        src,
        "    void jp_report_live_generation_preflight();\n",
        "    void jp_report_live_generation_preflight();\n"
        "    void jp_report_config_action_producer_gate();\n",
        "stage14 read-only report declaration",
    )
    src = stage10.once(
        src,
        "        return false;\n"
        "    }\n"
        "    std::lock_guard<std::mutex> lock(jp_config_action_publish_mutex);\n"
        "    jp_config_actions_closed_for_pc_exit = true;\n",
        "        return false;\n"
        "    }\n"
        "    // PC EXIT ONLY: close admission first, wait for every acquired\n"
        "    // publication lease to return, then drain after all other workers.\n"
        "    if (!jp_config_publisher_gate.close_for_pc_exit(\n"
        "            std::chrono::milliseconds{500})) {\n"
        "        std::fprintf(stderr,\n"
        "            \"[Goemon JP config fence stage14] drained=0; \"\n"
        "            \"publisher permit timeout, skip action drain.\\n\");\n"
        "        return false;\n"
        "    }\n"
        "    std::lock_guard<std::mutex> lock(jp_config_action_publish_mutex);\n"
        "    jp_config_actions_closed_for_pc_exit = true;\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP config fence stage14] drained=1 closed=1; \"\n"
        "        \"normal PC exit only.\\n\");\n",
        "stage14 close-before-drain and bounded permit wait",
    )
    src = stage10.once(
        src,
        "void ultramodern::trigger_config_action() {\n"
        "    // The renderer has exited: do not enqueue stale UI config work.\n",
        "void ultramodern::trigger_config_action() {\n"
        "    // The lease covers the enqueue through method return, ensuring\n"
        "    // the close-before-drain fence cannot miss an in-flight publisher.\n"
        "    auto jp_permit = jp_config_publisher_gate.try_acquire();\n"
        "    if (!jp_permit) return;\n"
        "    // The renderer has exited: do not enqueue stale UI config work.\n",
        "stage14 wrap active native config action enqueue in RAII lease",
    )
    src = stage10.once(
        src,
        "bool ultramodern::jp_drain_action_queue_after_pc_exit(bool all_guests_joined) {\n",
        GATE_REPORT
        + "bool ultramodern::jp_drain_action_queue_after_pc_exit(bool all_guests_joined) {\n",
        "stage14 report before action drain",
    )
    # The pinned events.cpp uses the include path supplied only to JP's
    # ultramodern build when Stage14 is explicitly enabled.
    return marker + "\n#include \"jp_generation_publisher_gate.hpp\"\n" + src


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
        print(f"[JP publisher stage14] {'Updated' if updated else 'Unchanged'}: {destination}")


if __name__ == "__main__":
    main()
