#!/usr/bin/env python3
"""Experimental JP F8 in-process reset attempt.

This is ONE integrated owner-driven generation transition. It composes the
proven Stage9-18 generated runtime overlays, does not touch pinned submodules
or ROMs, and rejects a new generation unless the previous one passed ALL
existing joined/queue/save/timer checks. Native app remains in recomp::start()
with its SDL_Window reused. There is no execv or process replacement.

The first Ubuntu run is mandatory: the source patch alone is NOT proof that
all RT64/VI/SDL/guest static state can be reinitialized. Default OFF.
"""
from __future__ import annotations

import argparse
from pathlib import Path


def once(src: str, old: str, new: str, label: str) -> str:
    n = src.count(old)
    if n != 1:
        raise ValueError(f"Experimental reset {label}: expected one anchor, found {n}")
    return src.replace(old, new, 1)


GUEST_REARM = r"""// After normal shutdown and a complete worker join, the reset owner may
// reopen OSThread creation. Never clear the stop flag while any old guest
// context remains live or its cleaner has not joined.
bool ultramodern::jp_rearm_guest_after_verified_exit() {
    std::lock_guard<std::mutex> lock(jp_guest_context_mutex);
    if (!jp_guest_stop_requested.load(std::memory_order_acquire) ||
        jp_guest_creations_in_flight.load(std::memory_order_acquire) != 0 ||
        !jp_guest_contexts.empty() ||
        jp_guest_threads_created.load(std::memory_order_acquire) !=
            jp_guest_threads_joined.load(std::memory_order_acquire)) {
        return false;
    }
    jp_guest_stop_requested.store(false, std::memory_order_release);
    return true;
}

"""


def threads(src: str) -> str:
    if "jp_rearm_guest_after_verified_exit" in src:
        raise ValueError("Guest rearm already installed")
    src = once(src,
        "void ultramodern::request_guest_shutdown_for_future_reset() {\n",
        GUEST_REARM + "void ultramodern::request_guest_shutdown_for_future_reset() {\n",
        "guest join-based rearm owner")
    return "// Experimental integrated reset OSThread rearm.\n" + src


TIMER_REARM = r"""// Called only after the old guest, timer worker, publishers, and other
// native workers have fully joined. The clock and publication gate move to
// the same next generation or the whole restart fails closed.
bool ultramodern::jp_rearm_timer_after_verified_exit(std::uint64_t old_generation) {
    if (!ultramodern::jp_timer_exit_joined_stage17()) {
        return false;
    }
    const goemon_jp::reset::TimerEpochClock::StopProof proofs{
        true, true, true, true
    };
    if (!jp_timer_epoch_clock.rebase_after_verified_exit(old_generation, proofs)) {
        return false;
    }
    if (!jp_timer_publisher_gate.rearm_after_verified_exit(old_generation, true)) {
        return false;
    }
    jp_timer_exit_gate_drained.store(false, std::memory_order_release);
    jp_timer_exit_worker_joined.store(false, std::memory_order_release);
    return true;
}

"""


def timer(src: str) -> str:
    if "jp_rearm_timer_after_verified_exit" in src:
        raise ValueError("Timer rearm already installed")
    src = once(src,
        "    void jp_report_timer_epoch_stage18();\n",
        "    void jp_report_timer_epoch_stage18();\n"
        "    bool jp_rearm_timer_after_verified_exit(std::uint64_t);\n",
        "timer restart declaration")
    src = once(src,
        "void ultramodern::jp_report_timer_epoch_stage18() {\n",
        TIMER_REARM + "void ultramodern::jp_report_timer_epoch_stage18() {\n",
        "timer rearm implementation")
    return "// Experimental integrated reset timer clock, queue and gate rearm.\n" + src


EVENT_REARM = r"""// Only invoked after ALL guest/native event threads have joined and the
// Stage10 action queue is empty. No RT64 worker can still read these values.
bool ultramodern::jp_rearm_events_after_verified_exit(std::uint64_t old_generation) {
    if (!ultramodern::jp_event_workers_joined_for_future_reset() ||
        !ultramodern::jp_graphics_queue_settled_for_future_reset() ||
        events_context.action_queue.size_approx() != 0 ||
        events_context.sp_task_queue.size_approx() != 0) {
        return false;
    }
    {
        std::lock_guard<std::mutex> lock(events_context.message_mutex);
        events_context.vi.cur_state = 0;
        events_context.vi.field = 0;
        events_context.vi.states[0] = ViState{};
        events_context.vi.states[1] = ViState{};
        events_context.vi.regs = {};
        events_context.vi.update_screen_regs = {};
        events_context.sp.mq = NULLPTR;
        events_context.dp.mq = NULLPTR;
        events_context.ai.mq = NULLPTR;
        events_context.si.mq = NULLPTR;
    }
    total_vis = 0;
    if (!jp_config_publisher_gate.rearm_after_verified_exit(
            old_generation, true)) {
        return false;
    }
    return true;
}

"""


def events(src: str) -> str:
    if "jp_rearm_events_after_verified_exit" in src:
        raise ValueError("Events rearm already installed")
    src = once(src,
        "    void jp_report_config_action_producer_gate();\n",
        "    void jp_report_config_action_producer_gate();\n"
        "    bool jp_rearm_events_after_verified_exit(std::uint64_t);\n",
        "events rearm declaration")
    src = once(src,
        "void ultramodern::jp_report_config_action_producer_gate() {\n",
        EVENT_REARM + "void ultramodern::jp_report_config_action_producer_gate() {\n",
        "events state/queue/gate rearm")
    return "// Experimental integrated reset VI, message targets and action queue rearm.\n" + src


SAVE_REARM = r"""// A reset never discards dirty save bytes. Stage16 must have finalized
// every previous mutation and joined the worker before this is called.
bool ultramodern::jp_rearm_saving_after_verified_exit() {
    if (!ultramodern::jp_save_worker_joined_for_future_reset()) {
        return false;
    }
    // The stopped worker may have left notifications after the final
    // synchronous Stage16 flush. They must not leak into a fresh save.
    while (save_context.write_sempahore.tryWait()) {}
    while (save_context.swap_file_pending_sempahore.tryWait()) {}
    while (save_context.swap_file_ready_sempahore.tryWait()) {}
    jp_save_mutation_epoch.store(0, std::memory_order_release);
    jp_save_finalized_epoch.store(0, std::memory_order_release);
    jp_save_exit_finalized.store(false, std::memory_order_release);
    return true;
}

"""


def saving(src: str) -> str:
    if "jp_rearm_saving_after_verified_exit" in src:
        raise ValueError("Saving rearm already installed")
    src = once(src,
        "void ultramodern::init_saving(RDRAM_ARG1) {\n",
        SAVE_REARM + "void ultramodern::init_saving(RDRAM_ARG1) {\n",
        "safe save epoch and notification rearm")
    return "// Experimental integrated reset finalized saving worker rearm.\n" + src


RESET_OWNER = r"""// Experimental reset ownership: F8 requests are handled by the existing
// normal-exit join path, then a new guest generation is created inside the
// SAME recomp::start() invocation (without a new PID or SDL_Window).
static std::atomic_bool jp_integrated_restart_requested{false};
static std::u8string jp_integrated_restart_game_id;
static std::atomic_uint64_t jp_integrated_generation{1};
static bool jp_integrated_autostart_next = false;

bool recomp::jp_request_integrated_reset() {
    bool expected = false;
    if (!jp_integrated_restart_requested.compare_exchange_strong(
            expected, true, std::memory_order_acq_rel)) {
        return false;
    }
    {
        std::lock_guard<std::mutex> lock(current_game_mutex);
        if (game_status.load(std::memory_order_acquire) != GameStatus::Running ||
            !current_game.has_value()) {
            jp_integrated_restart_requested.store(false, std::memory_order_release);
            return false;
        }
        jp_integrated_restart_game_id = *current_game;
    }
    std::fprintf(stderr,
        "[Goemon JP integrated reset] request=1 generation=%llu "
        "stopping=1 pid=unchanged; entering verified teardown.\\n",
        static_cast<unsigned long long>(
            jp_integrated_generation.load(std::memory_order_acquire)));
    // This ends the current runtime GENERATION. The outer runtime function
    // remains on the stack, and its SDL window is never destroyed.
    ultramodern::quit();
    return true;
}

"""


def recomp(src: str) -> str:
    if "jp_request_integrated_reset" in src:
        raise ValueError("Integrated reset already installed in recomp source")
    if "[Goemon JP exit barrier stage12]" not in src or \
       "jp_timer_exit_joined_stage17()" not in src:
        raise ValueError("Reset requires generated Stage12 + Stage17 complete exit proof")
    src = once(src,
        "namespace ultramodern { bool jp_timer_exit_joined_stage17(); }\n",
        "namespace ultramodern { bool jp_timer_exit_joined_stage17(); }\n"
        "namespace ultramodern {\n"
        "    bool jp_rearm_guest_after_verified_exit();\n"
        "    bool jp_rearm_timer_after_verified_exit(std::uint64_t);\n"
        "    bool jp_rearm_events_after_verified_exit(std::uint64_t);\n"
        "    bool jp_rearm_saving_after_verified_exit();\n"
        "}\n"
        "namespace recomp { bool jp_reset_audio_buffer_after_join(); }\n",
        "integrated ownership declarations")
    src = once(src,
        "void ultramodern::quit() {\n",
        RESET_OWNER + "void ultramodern::quit() {\n",
        "integrated F8 request ownership")
    src = once(src,
        "    // Allocate rdram without comitting it. Use a platform-specific virtual allocation function\n",
        "    // One app process and window; each loop body owns one fresh RDRAM.\n"
        "    for (;;) {\n"
        "    // Allocate rdram without comitting it. Use a platform-specific virtual allocation function\n",
        "generation-scoped allocation loop")
    src = once(src,
        "    }, window_handle, rdram};\n",
        "    }, window_handle, rdram};\n"
        "    if (jp_integrated_autostart_next) {\n"
        "        jp_integrated_autostart_next = false;\n"
        "        recomp::start_game(jp_integrated_restart_game_id);\n"
        "    }\n",
        "replay registered JP game selection after new preinit starts")
    src = once(src,
        "    if (jp_guest_exit_drained &&\n"
        "        ultramodern::jp_timer_exit_joined_stage17()) {\n"
        "    // Free rdram.\n",
        "    bool jp_integrated_rdram_released = false;\n"
        "    if (jp_guest_exit_drained &&\n"
        "        ultramodern::jp_timer_exit_joined_stage17() &&\n"
        "        (!jp_integrated_restart_requested.load(std::memory_order_acquire) ||\n"
        "         jp_exit_known_joined)) {\n"
        "    // Free rdram.\n",
        "never release RDRAM on failed integrated shutdown barrier")

    src = once(src,
        '    if (free_failed) {\n'
        '        printf("Failed to free rdram\\n");\n'
        '    }\n'
        '    } else {\n',
        '    if (free_failed) {\n'
        '        printf("Failed to free rdram\\n");\n'
        '    } else {\n'
        '        jp_integrated_rdram_released = true;\n'
        '    }\n'
        '    } else {\n',
        "record successful verified RDRAM unmap for restart")

    # The original pinned file ends with recomp::start(), and Stage17 only
    # prefixes instrumentation. Insert BEFORE its final closing brace.
    if not src.endswith("}\n"):
        raise ValueError("Generated recomp.cpp no longer ends in recomp::start()")
    tail = r"""
    // This is the only point where the same-process restart may proceed:
    // game, guests, VI/GFX/SP, cleaner, timer, save and action producers
    // have ALREADY joined; RDRAM was actually unmapped successfully.
    if (jp_integrated_restart_requested.load(std::memory_order_acquire)) {
        const auto old_generation =
            jp_integrated_generation.load(std::memory_order_acquire);
        const bool joined = jp_exit_known_joined && jp_guest_exit_drained &&
            ultramodern::jp_timer_exit_joined_stage17() &&\n            jp_integrated_rdram_released;
        if (!joined) {
            std::fprintf(stderr,
                "[Goemon JP integrated reset] generation=%llu result=ABORT "
                "reason=unproven-shutdown-or-memory-release; no memory reuse.\\n",
                static_cast<unsigned long long>(old_generation));
            break; // Normal process exit; never re-enter half-joined state.
        }
        // Each rearm is legal only when its own old-generation proof passes.
        // Failure at any point ends the process safely, not an unsafe reset.
        const bool guest_ready =
            ultramodern::jp_rearm_guest_after_verified_exit();
        const bool event_ready = guest_ready &&
            ultramodern::jp_rearm_events_after_verified_exit(old_generation);
        const bool timer_ready = event_ready &&
            ultramodern::jp_rearm_timer_after_verified_exit(old_generation);
        const bool save_ready = timer_ready &&
            ultramodern::jp_rearm_saving_after_verified_exit();
        const bool audio_ready = save_ready &&
            recomp::jp_reset_audio_buffer_after_join();
        if (!audio_ready) {
            std::fprintf(stderr,
                "[Goemon JP integrated reset] generation=%llu result=ABORT "
                "reason=failed-generation-rearm; no new RDRAM allocated.\\n",
                static_cast<unsigned long long>(old_generation));
            break;
        }
        {
            std::lock_guard<std::mutex> lock(current_game_mutex);
            current_game.reset();
        }
        // A previously signalled renderer shutdown semaphore has been
        // consumed by the old gfx worker before its real thread join.
        game_status.store(GameStatus::None, std::memory_order_release);
        exited.store(false, std::memory_order_release);
        jp_integrated_autostart_next = true;
        jp_integrated_generation.fetch_add(1, std::memory_order_acq_rel);
        jp_integrated_restart_requested.store(false, std::memory_order_release);
        std::fprintf(stderr,
            "[Goemon JP integrated reset] generation=%llu result=REARMED "
            "pid=unchanged window=preserved next_boot=1.\\n",
            static_cast<unsigned long long>(old_generation + 1));
        continue;
    }
    break;
    } // Per-generation RDRAM allocation and verified teardown loop.
"""
    return "// Experimental integrated same-process reset loop.\n" + src[:-2] + tail + "}\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--generated-dir", type=Path, required=True)
    a = p.parse_args()
    d = a.generated_dir
    changes = [
        ("threads.cpp", "threads_reset.cpp", threads),
        ("timer_stage18.cpp", "timer_integrated.cpp", timer),
        ("events.cpp", "events_integrated.cpp", events),
        ("pi_stage16.cpp", "pi_integrated.cpp", saving),
        ("recomp_stage17.cpp", "recomp_integrated.cpp", recomp),
    ]
    for source, target, transform in changes:
        path = d / source
        original = path.read_text(encoding="utf-8")
        result = transform(original)
        output = d / target
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(result, encoding="utf-8")
        temp.replace(output)
        print(f"[JP integrated reset] {source} -> {target}")


if __name__ == "__main__":
    main()
