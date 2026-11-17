// Stage18: native host-only clock generation and concurrency proof.
// This test macro must NEVER be set on the Japanese native game target.
#define GOEMON_JP_STAGE18_TEST_REBASE
#include "../../src/game/jp_timer_epoch_clock.hpp"
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <thread>
#include <vector>

using namespace std::chrono_literals;
int main() {
    using goemon_jp::reset::TimerEpochClock;
    TimerEpochClock clock;
    assert(clock.snapshot().generation == 1);
    std::this_thread::sleep_for(3ms);
    const auto t0 = clock.ticks_now();
    std::this_thread::sleep_for(3ms);
    assert(clock.ticks_now() >= t0);
    clock.set_guest_time(1'000'000);
    auto adjusted = clock.guest_time();
    assert(adjusted >= 1'000'000);

    const TimerEpochClock::TestStopProof incomplete{true,true,true,false};
    const TimerEpochClock::TestStopProof proved{true,true,true,true};
    assert(!clock.rebase_for_test(1,incomplete));
    assert(!clock.rebase_for_test(2,proved));
    assert(clock.snapshot().generation == 1);
    assert(clock.rebase_for_test(1,proved));
    auto snap = clock.snapshot();
    assert(snap.generation == 2 && snap.guest_time == snap.ticks);
    assert(!clock.rebase_for_test(1,proved));
    clock.set_guest_time(42);
    assert(clock.guest_time() >= 42);

    constexpr int threads = 6;
    constexpr int loops = 10000;
    std::vector<std::thread> workers;
    std::atomic_bool wrong_epoch{false};
    for (int i=0; i<threads; ++i) {
        workers.emplace_back([&,i] {
            for (int j=0; j<loops; ++j) {
                if (i == 0 && j % 137 == 0) clock.set_guest_time(42);
                auto v = clock.snapshot();
                if (v.generation != 2 || v.ticks > 60ull*46875ull*1000ull) {
                    wrong_epoch.store(true);
                }
                (void)clock.start();
                (void)clock.since_start();
            }
        });
    }
    for (auto& w:workers) w.join();
    assert(!wrong_epoch.load());
    assert(clock.snapshot().generation == 2);
    std::printf("Stage18 timer epoch host test PASS: threads=%d samples=%d generation=2 atomic-epoch-and-offset=1\n", threads, threads*loops);
}
