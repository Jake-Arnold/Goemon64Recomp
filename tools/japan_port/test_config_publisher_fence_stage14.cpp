// ROM-free host safety test for JP Stage14 config-action publication gate.
#include "../../src/game/jp_generation_publisher_gate.hpp"

#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <thread>
#include <utility>
#include <vector>

using namespace std::chrono_literals;

int main() {
    using goemon_jp::reset::PublisherGate;
    PublisherGate gate{1};
    auto initial = gate.snapshot();
    assert(initial.open && initial.generation == 1);
    assert(initial.accepted == 0 && initial.rejected == 0 &&
           initial.in_flight == 0);

    // Closing must WAIT for a previously granted permit even after it
    // has made the gate permanently unavailable to later callers.
    auto held = gate.try_acquire();
    assert(static_cast<bool>(held));
    std::atomic_bool close_finished{false};
    std::atomic_bool close_result{false};
    std::thread closer{[&] {
        close_result.store(gate.close_for_pc_exit(2000ms));
        close_finished.store(true);
    }};
    const auto deadline = std::chrono::steady_clock::now() + 1500ms;
    while (gate.snapshot().open &&
           std::chrono::steady_clock::now() < deadline) {
        std::this_thread::yield();
    }
    assert(!gate.snapshot().open);
    assert(!close_finished.load());
    assert(!static_cast<bool>(gate.try_acquire()));
    held.release();
    closer.join();
    assert(close_finished.load() && close_result.load());
    auto closed = gate.snapshot();
    assert(!closed.open && closed.in_flight == 0 &&
           closed.accepted == 1 && closed.rejected == 1);
    assert(!static_cast<bool>(gate.try_acquire()));

    // A timed-out close cannot accidentally reopen the gate when its
    // outstanding lease is released.
    PublisherGate timed{7};
    auto slow = timed.try_acquire();
    assert(!timed.close_for_pc_exit(0ms));
    assert(!timed.snapshot().open);
    slow.release();
    assert(timed.snapshot().in_flight == 0);
    assert(!static_cast<bool>(timed.try_acquire()));
    assert(timed.snapshot().generation == 7);

    // Admission/close interleaving: readers must see monotonic counts,
    // unique ownership, and zero outstanding leases after closing.
    PublisherGate racing{9};
    constexpr unsigned kWorkers = 10;
    constexpr unsigned kTries = 3000;
    std::vector<std::thread> workers;
    std::atomic_uint64_t admitted{0}, denied{0};
    for (unsigned i = 0; i < kWorkers; ++i) {
        workers.emplace_back([&] {
            for (unsigned j = 0; j < kTries; ++j) {
                auto permit = racing.try_acquire();
                if (permit) {
                    admitted.fetch_add(1, std::memory_order_relaxed);
                    std::this_thread::yield();
                } else {
                    denied.fetch_add(1, std::memory_order_relaxed);
                }
            }
        });
    }
    const bool drained = racing.close_for_pc_exit(2000ms);
    for (auto& thread : workers) thread.join();
    assert(drained);
    const auto end = racing.snapshot();
    assert(end.generation == 9 && !end.open && end.in_flight == 0);
    assert(end.accepted == admitted.load());
    assert(end.rejected == denied.load());
    assert(end.accepted + end.rejected == kWorkers * kTries);
    assert(!static_cast<bool>(racing.try_acquire()));
    assert(racing.snapshot().rejected == end.rejected + 1);

    std::printf("Stage14 host publisher gate: PASS; concurrency=%u, "
                "attempts=%u, generation=9, open=0, inflight=0\n",
                kWorkers, kWorkers * kTries);
    return 0;
}
