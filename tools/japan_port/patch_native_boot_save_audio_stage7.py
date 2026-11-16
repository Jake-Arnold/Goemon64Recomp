#!/usr/bin/env python3
"""JP stage 7: read-only native boot, save worker and audio handoff census.

Pinned N64ModernRuntime files remain unchanged. Generated sources compose
the verified stage-1 timer shutdown and are built only with the opt-in
GOEMON_JP_BOOT_STAGE7 option. No reset is requested or implemented.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


def load_timer_stage1():
    path = Path(__file__).with_name("patch_timer_runtime.py")
    spec = importlib.util.spec_from_file_location("jp_reset_timer_stage1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing stage-1 timer generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage1 = load_timer_stage1()


def once(src: str, before: str, after: str, label: str) -> str:
    return stage1.once(src, before, after, label)


BOOT_STATE = r"""// JP stage7 diagnostic only: joining the PC application game-start
// worker occurs on ordinary EXIT, not when F8 is pressed.
static std::atomic_bool jp_boot_thread_active{false};
static std::atomic_bool jp_boot_entry_active{false};
static std::atomic_bool jp_boot_thread_joined{false};
static std::atomic_uint64_t jp_boot_entry_calls{0};

struct JpBootActiveScope {
    std::atomic_bool& active;
    explicit JpBootActiveScope(std::atomic_bool& flag) : active(flag) {
        active.store(true, std::memory_order_release);
    }
    ~JpBootActiveScope() {
        active.store(false, std::memory_order_release);
    }
};

void recomp::jp_report_native_boot_lifecycle() {
    std::fprintf(stderr,
        "[Goemon JP native boot] worker=%u entry_active=%u entries=%llu "
        "joined=%u; no coordinated stop or memory reset.\n",
        static_cast<unsigned>(jp_boot_thread_active.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_boot_entry_active.load(std::memory_order_acquire)),
        static_cast<unsigned long long>(jp_boot_entry_calls.load(std::memory_order_relaxed)),
        static_cast<unsigned>(jp_boot_thread_joined.load(std::memory_order_acquire)));
}

// This single-worker predicate is not a reset barrier. Joining the native
// boot worker on normal app exit does NOT mean guest OSThreads are joined.
bool recomp::jp_native_boot_joined_for_future_reset() {
    return jp_boot_thread_joined.load(std::memory_order_acquire) &&
        !jp_boot_thread_active.load(std::memory_order_acquire) &&
        !jp_boot_entry_active.load(std::memory_order_acquire);
}

"""


def instrument_recomp(original: str) -> str:
    src = stage1.recomp_source(original)
    marker = "// JP stage7 native boot census, generated from pinned recomp.cpp."
    src = once(
        src, "#include <cstdio>\n",
        "#include <cstdio>\n#include <atomic>\n",
        "boot lifecycle atomic header",
    )
    src = once(
        src,
        "namespace ultramodern { void shutdown_timers(); }\n",
        "namespace ultramodern { void shutdown_timers(); }\n"
        "namespace recomp {\n"
        "    void jp_report_native_boot_lifecycle();\n"
        "    bool jp_native_boot_joined_for_future_reset();\n"
        "}\n",
        "boot census function declarations after native headers",
    )
    src = once(
        src,
        "std::atomic_bool exited = false;\n",
        BOOT_STATE + "std::atomic_bool exited = false;\n",
        "boot census state",
    )
    src = once(
        src,
        "                try {\n"
        "                    game_entry.entrypoint(rdram, context);\n",
        "                jp_boot_entry_calls.fetch_add(1, std::memory_order_relaxed);\n"
        "                JpBootActiveScope jp_entry_scope(jp_boot_entry_active);\n"
        "                try {\n"
        "                    game_entry.entrypoint(rdram, context);\n",
        "boot entrypoint activity scope",
    )
    src = once(
        src,
        "    std::thread game_thread{[](ultramodern::renderer::WindowHandle window_handle, uint8_t* rdram) {\n",
        "    jp_boot_thread_joined.store(false, std::memory_order_release);\n"
        "    std::thread game_thread{[](ultramodern::renderer::WindowHandle window_handle, uint8_t* rdram) {\n"
        "        JpBootActiveScope jp_native_scope(jp_boot_thread_active);\n",
        "game-start native thread lifecycle",
    )
    src = once(
        src,
        "    game_thread.join();\n"
        "    // Timer may still reference guest RDRAM; join before unmapping RAM.\n",
        "    game_thread.join();\n"
        "    jp_boot_thread_joined.store(true, std::memory_order_release);\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP boot exit] joined=1 entry_active=%u; PC app shutdown only.\\n\",\n"
        "        static_cast<unsigned>(jp_boot_entry_active.load(std::memory_order_acquire)));\n"
        "    // Timer may still reference guest RDRAM; join before unmapping RAM.\n",
        "native boot join before timer shutdown",
    )
    return marker + "\n" + src


SAVE_STATE = r"""// JP stage7 saving audit, independent of guest memory and save payloads.
static std::atomic_bool jp_save_worker_initialized{false};
static std::atomic_bool jp_save_worker_active{false};
static std::atomic_bool jp_save_worker_joined{false};
static std::atomic_bool jp_save_file_io_active{false};
static std::atomic_uint64_t jp_save_write_signals{0};
static std::atomic_uint64_t jp_save_flush_attempts{0};
static std::atomic_uint64_t jp_save_flush_successes{0};

struct JpSaveActiveScope {
    std::atomic_bool& active;
    explicit JpSaveActiveScope(std::atomic_bool& flag) : active(flag) {
        active.store(true, std::memory_order_release);
    }
    ~JpSaveActiveScope() {
        active.store(false, std::memory_order_release);
    }
};

void ultramodern::jp_report_save_worker_lifecycle() {
    std::fprintf(stderr,
        "[Goemon JP save audit] initialized=%u worker=%u joined=%u "
        "file_io=%u write_signals=%llu flush_attempts=%llu flush_ok=%llu; "
        "pending/durable writes unproven.\n",
        static_cast<unsigned>(jp_save_worker_initialized.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_save_worker_active.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_save_worker_joined.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_save_file_io_active.load(std::memory_order_acquire)),
        static_cast<unsigned long long>(jp_save_write_signals.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(jp_save_flush_attempts.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(jp_save_flush_successes.load(std::memory_order_relaxed)));
}

bool ultramodern::jp_save_worker_joined_for_future_reset() {
    // Save completion and durability require a separate flush protocol.
    return jp_save_worker_initialized.load(std::memory_order_acquire) &&
        jp_save_worker_joined.load(std::memory_order_acquire) &&
        !jp_save_worker_active.load(std::memory_order_acquire) &&
        !jp_save_file_io_active.load(std::memory_order_acquire);
}

"""


def instrument_pi(original: str) -> str:
    marker = "// JP stage7 save worker census; pinned pi.cpp unchanged."
    if marker in original or "jp_save_worker_initialized" in original:
        raise ValueError("JP stage7 save instrumentation already applied")
    src = once(
        original, "#include <memory>\n",
        "#include <memory>\n#include <atomic>\n#include <cstdio>\n",
        "save worker atomic/stdio headers",
    )
    src = once(
        src, "#include <ultramodern/ultramodern.hpp>\n",
        "#include <ultramodern/ultramodern.hpp>\n"
        "namespace ultramodern {\n"
        "    void jp_report_save_worker_lifecycle();\n"
        "    bool jp_save_worker_joined_for_future_reset();\n"
        "}\n",
        "save worker function declarations",
    )
    src = once(src, "} save_context;\n",
               "} save_context;\n\n" + SAVE_STATE,
               "save worker audit state")
    src = once(
        src, "void update_save_file() {\n",
        "void update_save_file() {\n"
        "    JpSaveActiveScope jp_save_file_scope(jp_save_file_io_active);\n"
        "    jp_save_flush_attempts.fetch_add(1, std::memory_order_relaxed);\n",
        "save file IO RAII scope",
    )
    src = once(
        src,
        "    if (saving_failed) {\n"
        "        ultramodern::error_handling::message_box(",
        "    if (!saving_failed) {\n"
        "        jp_save_flush_successes.fetch_add(1, std::memory_order_relaxed);\n"
        "    }\n"
        "    if (saving_failed) {\n"
        "        ultramodern::error_handling::message_box(",
        "save successful finalization accounting",
    )
    src = once(
        src, "void saving_thread_func(RDRAM_ARG1) {\n",
        "void saving_thread_func(RDRAM_ARG1) {\n"
        "    JpSaveActiveScope jp_save_scope(jp_save_worker_active);\n",
        "save worker activity scope",
    )
    needle = "    save_context.write_sempahore.signal();\n"
    count = src.count(needle)
    if count != 3:
        raise ValueError(
            f"save write signal sites: expected 3 pinned-runtime anchors, found {count}"
        )
    src = src.replace(
        needle,
        "    jp_save_write_signals.fetch_add(1, std::memory_order_relaxed);\n"
        + needle,
    )
    src = once(
        src,
        "    save_context.saving_thread = std::thread{saving_thread_func, PASS_RDRAM};\n",
        "    jp_save_worker_joined.store(false, std::memory_order_release);\n"
        "    save_context.saving_thread = std::thread{saving_thread_func, PASS_RDRAM};\n"
        "    jp_save_worker_initialized.store(true, std::memory_order_release);\n",
        "save worker initialized",
    )
    src = once(
        src,
        "        save_context.saving_thread.join();\n"
        "    }\n"
        "}\n\n"
        "void do_dma(",
        "        save_context.saving_thread.join();\n"
        "        jp_save_worker_joined.store(true, std::memory_order_release);\n"
        "    }\n"
        "    std::fprintf(stderr,\n"
        "        \"[Goemon JP save exit] joined=%u worker=%u file_io=%u \"\n"
        "        \"write_signals=%llu flush_ok=%llu; save-only shutdown, durability unproven.\\n\",\n"
        "        static_cast<unsigned>(jp_save_worker_joined.load(std::memory_order_acquire)),\n"
        "        static_cast<unsigned>(jp_save_worker_active.load(std::memory_order_acquire)),\n"
        "        static_cast<unsigned>(jp_save_file_io_active.load(std::memory_order_acquire)),\n"
        "        static_cast<unsigned long long>(jp_save_write_signals.load(std::memory_order_relaxed)),\n"
        "        static_cast<unsigned long long>(jp_save_flush_successes.load(std::memory_order_relaxed)));\n"
        "}\n\n"
        "void do_dma(",
        "save worker join and normal-exit audit",
    )
    return marker + "\n" + src


AUDIO_STATE = r"""// JP stage7 audio dispatch preflight: describes synchronous runtime
// callback use, not the SDL audio device's separate buffered playback.
static std::atomic_bool jp_audio_initialized{false};
static std::atomic_bool jp_audio_callbacks_installed{false};
static std::atomic_uint64_t jp_audio_queued_chunks{0};
static std::atomic_uint64_t jp_audio_samples_submitted{0};
static std::atomic_uint32_t jp_audio_dispatch_inflight{0};

struct JpAudioDispatchScope {
    JpAudioDispatchScope() {
        jp_audio_dispatch_inflight.fetch_add(1, std::memory_order_acq_rel);
    }
    ~JpAudioDispatchScope() {
        jp_audio_dispatch_inflight.fetch_sub(1, std::memory_order_acq_rel);
    }
};

void ultramodern::jp_report_audio_dispatch_lifecycle() {
    std::fprintf(stderr,
        "[Goemon JP audio audit] initialized=%u callbacks=%u "
        "dispatch_inflight=%u chunks=%llu samples=%llu; SDL device unverified.\n",
        static_cast<unsigned>(jp_audio_initialized.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_audio_callbacks_installed.load(std::memory_order_acquire)),
        static_cast<unsigned>(jp_audio_dispatch_inflight.load(std::memory_order_acquire)),
        static_cast<unsigned long long>(jp_audio_queued_chunks.load(std::memory_order_relaxed)),
        static_cast<unsigned long long>(jp_audio_samples_submitted.load(std::memory_order_relaxed)));
}

bool ultramodern::jp_audio_dispatch_idle_for_future_reset() {
    // This is not a sound-device or output-buffer shutdown barrier.
    return jp_audio_initialized.load(std::memory_order_acquire) &&
        jp_audio_callbacks_installed.load(std::memory_order_acquire) &&
        jp_audio_dispatch_inflight.load(std::memory_order_acquire) == 0;
}

"""


def instrument_audio(original: str) -> str:
    marker = "// JP stage7 audio dispatch census; pinned audio.cpp unchanged."
    if marker in original or "jp_audio_dispatch_inflight" in original:
        raise ValueError("JP stage7 audio instrumentation already applied")
    src = once(
        original, "#include <cassert>\n",
        "#include <cassert>\n#include <atomic>\n#include <cstdio>\n",
        "audio audit headers",
    )
    src = once(
        src, '#include "ultramodern/ultramodern.hpp"\n',
        '#include "ultramodern/ultramodern.hpp"\n'
        "namespace ultramodern {\n"
        "    void jp_report_audio_dispatch_lifecycle();\n"
        "    bool jp_audio_dispatch_idle_for_future_reset();\n"
        "}\n",
        "audio audit declarations",
    )
    src = once(
        src,
        "static ultramodern::audio_callbacks_t audio_callbacks;\n",
        "static ultramodern::audio_callbacks_t audio_callbacks;\n\n" + AUDIO_STATE,
        "audio audit state",
    )
    src = once(
        src,
        "    audio_callbacks = callbacks;\n",
        "    audio_callbacks = callbacks;\n"
        "    jp_audio_callbacks_installed.store(true, std::memory_order_release);\n",
        "audio callbacks installed",
    )
    src = once(
        src,
        "    set_audio_frequency(48000);\n",
        "    set_audio_frequency(48000);\n"
        "    jp_audio_initialized.store(true, std::memory_order_release);\n",
        "audio initialized",
    )
    src = once(
        src,
        "void ultramodern::queue_audio_buffer(RDRAM_ARG PTR(int16_t) audio_data_, uint32_t byte_count) {\n",
        "void ultramodern::queue_audio_buffer(RDRAM_ARG PTR(int16_t) audio_data_, uint32_t byte_count) {\n"
        "    JpAudioDispatchScope jp_dispatch_scope;\n",
        "audio callback activity",
    )
    src = once(
        src,
        "    if (sample_count > 0 && audio_callbacks.queue_samples) {\n"
        "        audio_callbacks.queue_samples(TO_PTR(int16_t, audio_data_), sample_count);\n",
        "    if (sample_count > 0 && audio_callbacks.queue_samples) {\n"
        "        jp_audio_queued_chunks.fetch_add(1, std::memory_order_relaxed);\n"
        "        jp_audio_samples_submitted.fetch_add(sample_count, std::memory_order_relaxed);\n"
        "        audio_callbacks.queue_samples(TO_PTR(int16_t, audio_data_), sample_count);\n",
        "audio submission count before callback",
    )
    return marker + "\n" + src


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sources = (
        ("librecomp/src/recomp.cpp", "recomp_stage7.cpp", instrument_recomp),
        ("librecomp/src/pi.cpp", "pi_stage7.cpp", instrument_pi),
        ("ultramodern/src/audio.cpp", "audio_stage7.cpp", instrument_audio),
    )
    for original, generated, transform in sources:
        source = args.runtime / original
        destination = args.output / generated
        changed = stage1.write_if_changed(
            destination, transform(source.read_text(encoding="utf-8"))
        )
        print(f"[JP native stage7] {'Updated' if changed else 'Unchanged'}: {destination}")


if __name__ == "__main__":
    main()
