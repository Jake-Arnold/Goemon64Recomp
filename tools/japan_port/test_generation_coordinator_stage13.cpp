// Host-only Stage13 concurrency/contract tests. No game assets or ROM needed.
#include "../../src/game/jp_generation_coordinator.hpp"

#include <algorithm>
#include <cassert>
#include <cstdio>
#include <thread>
#include <vector>

int main() {
    using namespace goemon_jp::reset;
    static_assert(kFutureRequiredFenceMask == 0x3FFu);
    static_assert(static_cast<std::uint32_t>(Fence::GuestCreation) == 1u);
    static_assert(static_cast<std::uint32_t>(Fence::SchedulerMemoryAndOverlayReinit) == 512u);

    Coordinator local;
    assert(local.generation() == 1);
    assert(local.phase() == Phase::Running);
    assert(local.attempt_count() == 0);
    const auto first = local.record_unarmed_request();
    assert(first.ticket == 1);
    assert(first.generation == 1);
    assert(first.phase == Phase::Running);
    assert(first.rejection == Rejection::BackendNotInstalled);

    constexpr unsigned kThreads = 8;
    constexpr unsigned kAttemptsPerThread = 500;
    std::vector<std::thread> workers;
    std::vector<std::vector<std::uint64_t>> tickets(kThreads);
    workers.reserve(kThreads);
    for (unsigned i = 0; i < kThreads; ++i) {
        workers.emplace_back([&, i] {
            auto& out = tickets[i];
            out.reserve(kAttemptsPerThread);
            for (unsigned j = 0; j < kAttemptsPerThread; ++j) {
                const Attempt a = local.record_unarmed_request();
                assert(a.generation == 1);
                assert(a.phase == Phase::Running);
                assert(a.rejection == Rejection::BackendNotInstalled);
                out.push_back(a.ticket);
            }
        });
    }
    for (auto& worker : workers) worker.join();
    std::vector<std::uint64_t> all{first.ticket};
    for (const auto& batch : tickets) all.insert(all.end(), batch.begin(), batch.end());
    std::sort(all.begin(), all.end());
    const std::uint64_t total = 1 + kThreads * kAttemptsPerThread;
    assert(all.size() == total);
    for (std::uint64_t i = 0; i < total; ++i) assert(all[i] == i + 1);
    assert(local.attempt_count() == total);
    assert(local.generation() == 1);
    assert(local.phase() == Phase::Running);
    std::printf("Stage13 host-only coordinator tests passed: %llu unique rejected requests, generation=1, phase=running\n",
                static_cast<unsigned long long>(total));
    return 0;
}
