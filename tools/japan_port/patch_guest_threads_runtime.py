#!/usr/bin/env python3
"""Generate a build-local guest-thread audit for the pinned N64ModernRuntime.

Stage 2 is observational: it never stops a guest thread, clears RDRAM,
relaunches the process, or reports that an in-process reset is safe.
The original N64ModernRuntime submodule remains untouched.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(source: str, original: str, replacement: str, label: str) -> str:
    occurrences = source.count(original)
    if occurrences != 1:
        raise ValueError(
            f"{label}: pinned runtime changed; expected one occurrence, got {occurrences}"
        )
    return source.replace(original, replacement, 1)


def instrument_threads(source: str) -> str:
    source = replace_once(
        source,
        "#include <cstdio>\n",
        "#include <cstdio>\n#include <atomic>\n#include <cstdint>\n",
        "instrumentation headers",
    )
    source = replace_once(
        source,
        "static ultramodern::threads::callbacks_t threads_callbacks;\n",
        """static ultramodern::threads::callbacks_t threads_callbacks;

// Atomic lifecycle counts are observational only. Reset must not clear RAM
// until every host guest thread is joined and other guest workers quiesce.
static std::atomic<uint64_t> jp_guest_threads_created{0};
static std::atomic<uint64_t> jp_guest_threads_finished{0};
static std::atomic<uint64_t> jp_guest_threads_joined{0};

static uint64_t jp_saturating_difference(uint64_t a, uint64_t b) {
    return a > b ? a - b : 0;
}

void ultramodern::report_guest_thread_reset_blockers() {
    const uint64_t created = jp_guest_threads_created.load(std::memory_order_relaxed);
    const uint64_t finished = jp_guest_threads_finished.load(std::memory_order_relaxed);
    const uint64_t joined = jp_guest_threads_joined.load(std::memory_order_relaxed);
    std::fprintf(stderr,
        "[Goemon JP reset audit] created=%llu finished=%llu joined=%llu "
        "active=%llu unjoined=%llu; reset unavailable (guest teardown pending).\\n",
        static_cast<unsigned long long>(created),
        static_cast<unsigned long long>(finished),
        static_cast<unsigned long long>(joined),
        static_cast<unsigned long long>(jp_saturating_difference(created, finished)),
        static_cast<unsigned long long>(jp_saturating_difference(finished, joined)));
}
""",
        "lifecycle counters and reset audit",
    )
    # Counters are updated at the point a guest host thread has been started
    # and acknowledged init. It cannot execute game code before osStartThread.
    source = replace_once(
        source,
        '    context->initialized.wait();\n'
        '    debug_printf("[os] Thread %d is ready to be started\\n", t->id);\n',
        '    context->initialized.wait();\n'
        '    jp_guest_threads_created.fetch_add(1, std::memory_order_relaxed);\n'
        '    debug_printf("[os] Thread %d is ready to be started\\n", t->id);\n',
        "created counter",
    )
    source = replace_once(
        source,
        "    ultramodern::cleanup_thread(thread_context);\n",
        "    jp_guest_threads_finished.fetch_add(1, std::memory_order_relaxed);\n"
        "    ultramodern::cleanup_thread(thread_context);\n",
        "finished counter",
    )
    source = replace_once(
        source,
        "            to_delete->host_thread.join();\n"
        "            delete to_delete;\n",
        "            to_delete->host_thread.join();\n"
        "            jp_guest_threads_joined.fetch_add(1, std::memory_order_relaxed);\n"
        "            delete to_delete;\n",
        "joined counter",
    )
    return (
        "// Generated JP guest-thread reset audit; original submodule not modified.\n"
        "namespace ultramodern { void report_guest_thread_reset_blockers(); }\n"
        + source
    )


def write_if_changed(path: Path, value: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == value:
        return False
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(value, encoding="utf-8")
    temp.replace(path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = (args.runtime / "ultramodern/src/threads.cpp").read_text(
        encoding="utf-8"
    )
    dest = args.output / "threads.cpp"
    did_change = write_if_changed(dest, instrument_threads(original))
    print(f"[JP thread audit] {'Updated' if did_change else 'Unchanged'}: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
