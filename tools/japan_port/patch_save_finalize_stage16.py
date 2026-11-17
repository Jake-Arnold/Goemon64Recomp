#!/usr/bin/env python3
"""JP Stage16: finish pending save mutations after worker join on PC exit.

Compose Stage7's existing pinned pi.cpp overlay. Track mutation epochs within
save_buffer_mutex; only an existing successful backup-finalize advances the
persisted epoch. After the worker joins on NORMAL APP EXIT, synchronize the
last pending snapshot once if necessary. No F8 stop, fsync durability claim,
new save format, or live-generation rearm is enabled.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_stage7():
    path = Path(__file__).with_name("patch_native_boot_save_audio_stage7.py")
    spec = importlib.util.spec_from_file_location("jp_save_stage7", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing Stage7 generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage7 = load_stage7()


EXIT_FINALIZE = r"""    // Stage16: normal app EXIT ONLY. Guest spawning has finished, Stage9
    // joined all guest threads, and the saving worker has been joined.
    // Any mutation not covered by the worker's last successful finalize
    // receives a final *synchronous* backup-finalize attempt.
    const auto jp_save_exit_expected =
        jp_save_mutation_epoch.load(std::memory_order_acquire);
    const auto jp_save_exit_previous =
        jp_save_finalized_epoch.load(std::memory_order_acquire);
    bool jp_save_exit_final_attempted = false;
    if (jp_save_worker_joined.load(std::memory_order_acquire) &&
        jp_save_exit_expected > jp_save_exit_previous) {
        jp_save_exit_final_attempted = true;
        try {
            update_save_file();
        } catch (const std::exception& e) {
            // Preserve failed-closed proof instead of unwinding shutdown.
            std::fprintf(stderr,
                "[Goemon JP save finalize stage16] final flush error: %s\\n",
                e.what());
        } catch (...) {
            std::fprintf(stderr,
                "[Goemon JP save finalize stage16] final flush unknown error.\\n");
        }
    }
    const auto jp_save_exit_completed =
        jp_save_finalized_epoch.load(std::memory_order_acquire);
    const bool jp_save_exit_complete =
        jp_save_worker_joined.load(std::memory_order_acquire) &&
        !jp_save_worker_active.load(std::memory_order_acquire) &&
        !jp_save_file_io_active.load(std::memory_order_acquire) &&
        jp_save_exit_completed >= jp_save_exit_expected;
    jp_save_exit_finalized.store(jp_save_exit_complete,
                                 std::memory_order_release);
    std::fprintf(stderr,
        "[Goemon JP save finalize stage16] mutated=%llu finalized_epoch=%llu "
        "final_attempt=%u finalized=%u durable=unproven; "
        "PC exit only, F8 disabled.\n",
        static_cast<unsigned long long>(jp_save_exit_expected),
        static_cast<unsigned long long>(jp_save_exit_completed),
        static_cast<unsigned>(jp_save_exit_final_attempted),
        static_cast<unsigned>(jp_save_exit_complete));
"""


def instrument_pi(original: str) -> str:
    marker = "// JP stage16 save mutation epoch / exit-only final backup finalize."
    if marker in original or "jp_save_mutation_epoch" in original:
        raise ValueError("Stage16 save finalization already instrumented")
    src = stage7.instrument_pi(original)
    replace = stage7.once
    src = replace(
        src,
        "#include <memory>\n#include <atomic>\n#include <cstdio>\n",
        "#include <memory>\n#include <atomic>\n#include <cstdio>\n"
        "#include <cstdint>\n#include <exception>\n",
        "Stage16 explicit fixed-width integer and exception headers",
    )
    src = replace(
        src,
        "static std::atomic_uint64_t jp_save_flush_successes{0};\n",
        "static std::atomic_uint64_t jp_save_flush_successes{0};\n"
        "static std::atomic_uint64_t jp_save_mutation_epoch{0};\n"
        "static std::atomic_uint64_t jp_save_finalized_epoch{0};\n"
        "static std::atomic_bool jp_save_exit_finalized{false};\n",
        "Stage16 mutation, last-finalized and exit proof state",
    )
    src = replace(
        src,
        "        !jp_save_file_io_active.load(std::memory_order_acquire);\n",
        "        !jp_save_file_io_active.load(std::memory_order_acquire) &&\n"
        "        jp_save_exit_finalized.load(std::memory_order_acquire);\n",
        "Stage16 save-ready predicate needs final mutation coverage",
    )
    src = replace(
        src,
        "    jp_save_flush_attempts.fetch_add(1, std::memory_order_relaxed);\n",
        "    jp_save_flush_attempts.fetch_add(1, std::memory_order_relaxed);\n"
        "    std::uint64_t jp_save_snapshot_epoch = 0;\n",
        "Stage16 local snapshot epoch for a successful disk finalization",
    )
    src = replace(
        src,
        "            save_file.write(save_context.save_buffer.data(), save_context.save_buffer.size());\n",
        "            save_file.write(save_context.save_buffer.data(), save_context.save_buffer.size());\n"
        "            jp_save_snapshot_epoch =\n"
        "                jp_save_mutation_epoch.load(std::memory_order_acquire);\n"
        "            if (!save_file.good()) saving_failed = true;\n",
        "Stage16 capture mutation snapshot while holding save buffer mutex",
    )
    src = replace(
        src,
        "        jp_save_flush_successes.fetch_add(1, std::memory_order_relaxed);\n",
        "        jp_save_flush_successes.fetch_add(1, std::memory_order_relaxed);\n"
        "        // Never advance persisted epoch on backup finalize failure.\n"
        "        jp_save_finalized_epoch.store(jp_save_snapshot_epoch,\n"
        "                                       std::memory_order_release);\n",
        "Stage16 advance last-finalized epoch only after successful finalize",
    )
    # Every mutation epoch increments while save_buffer_mutex is held.
    src = replace(
        src,
        "        memcpy(&save_context.save_buffer[offset], in, count);\n",
        "        memcpy(&save_context.save_buffer[offset], in, count);\n"
        "        jp_save_mutation_epoch.fetch_add(1, std::memory_order_release);\n",
        "Stage16 save_write_ptr mutation ordering",
    )
    src = replace(
        src,
        "            save_context.save_buffer[offset + i] = MEM_B(i, rdram_address);\n"
        "        }\n",
        "            save_context.save_buffer[offset + i] = MEM_B(i, rdram_address);\n"
        "        }\n"
        "        jp_save_mutation_epoch.fetch_add(1, std::memory_order_release);\n",
        "Stage16 guest save_write mutation ordering",
    )
    src = replace(
        src,
        "        std::fill_n(save_context.save_buffer.begin() + start, size, value);\n",
        "        std::fill_n(save_context.save_buffer.begin() + start, size, value);\n"
        "        jp_save_mutation_epoch.fetch_add(1, std::memory_order_release);\n",
        "Stage16 save_clear mutation ordering",
    )
    src = replace(
        src,
        "    }\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP save exit] joined=%u worker=%u file_io=%u \"\n",
        "    }\n" + EXIT_FINALIZE +
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP save exit] joined=%u worker=%u file_io=%u \"\n",
        "Stage16 synchronous pending-write flush after saving thread joins",
    )
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    src = (args.runtime / "librecomp/src/pi.cpp").read_text(encoding="utf-8")
    updated = stage7.stage1.write_if_changed(args.output, instrument_pi(src))
    print(f"[JP save stage16] {'Updated' if updated else 'Unchanged'}: {args.output}")


if __name__ == "__main__":
    main()
