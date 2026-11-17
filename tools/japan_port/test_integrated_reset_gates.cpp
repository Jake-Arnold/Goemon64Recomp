// Host-only reset gate regression: two generations and no unsafe rearm.
// Real guest/RT64 lifecycle acceptance requires the Ubuntu game binary.
#define GOEMON_JP_EXPERIMENTAL_RESET_BACKEND_ACTIVE
#include "../../src/game/jp_generation_publisher_gate.hpp"
#include "../../src/game/jp_timer_epoch_clock.hpp"
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <thread>

using goemon_jp::reset::PublisherGate;
using goemon_jp::reset::TimerEpochClock;
using namespace std::chrono_literals;

static void stop_and_rearm(PublisherGate& gate, TimerEpochClock& clock,
                           std::uint64_t generation) {
    assert(gate.snapshot().generation == generation);
    // Incomplete joins MUST NOT be enough even when the queue is empty.
    assert(!gate.rearm_after_verified_exit(generation, false));
    auto lease = gate.try_acquire();
    assert(static_cast<bool>(lease));
    assert(!gate.close_for_pc_exit(0ms)); // Outstanding publisher: fail closed.
    assert(!gate.rearm_after_verified_exit(generation, true));
    lease.release();
    assert(gate.close_for_pc_exit(500ms));
    assert(gate.snapshot().in_flight == 0);
    const TimerEpochClock::StopProof denied{true,true,true,false};
    const TimerEpochClock::StopProof verified{true,true,true,true};
    assert(!clock.rebase_after_verified_exit(generation, denied));
    assert(!clock.rebase_after_verified_exit(generation+1, verified));
    assert(clock.rebase_after_verified_exit(generation, verified));
    assert(gate.rearm_after_verified_exit(generation, true));
    assert(!gate.rearm_after_verified_exit(generation, true));
    assert(gate.snapshot().generation == generation+1);
    assert(clock.snapshot().generation == generation+1);
}

int main() {
    PublisherGate gate{1};
    TimerEpochClock clock{};
    stop_and_rearm(gate, clock, 1);
    assert(gate.try_acquire());
    stop_and_rearm(gate, clock, 2);
    assert(gate.snapshot().generation == 3);
    assert(clock.snapshot().generation == 3);
    std::printf("JP integrated reset host gates PASS: generation=3 repeated=2 failed_join_refused=1 pending_permit_refused=1\n");
}
