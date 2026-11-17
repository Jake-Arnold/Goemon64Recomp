#pragma once

// Japanese recomp Stage18: synchronized timer timebase per guest generation.
// Production exposes time reads and osSetTime only. A generation transition
// is deliberately test-only until the full guest/native reset backend exists.
#include <chrono>
#include <cstdint>
#include <limits>
#include <mutex>

namespace goemon_jp::reset {

class TimerEpochClock final {
public:
    using Clock = std::chrono::high_resolution_clock;
    using TimePoint = Clock::time_point;
    using Duration = Clock::duration;

    struct Snapshot {
        std::uint64_t generation;
        std::uint64_t ticks;
        std::uint64_t guest_time;
        TimePoint start;
    };

    explicit TimerEpochClock(std::uint64_t counter_per_ms = 46875,
                             std::uint64_t initial_generation = 1) noexcept
        : counter_per_ms_(counter_per_ms), generation_(initial_generation),
          start_(Clock::now()) {}
    TimerEpochClock(const TimerEpochClock&) = delete;
    TimerEpochClock& operator=(const TimerEpochClock&) = delete;

    [[nodiscard]] std::uint64_t ticks_now() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return ticks_at(Clock::now());
    }

    [[nodiscard]] std::uint64_t guest_time() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return ticks_at(Clock::now()) - guest_time_offset_;
    }

    void set_guest_time(std::uint64_t requested_ticks) noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        guest_time_offset_ = ticks_at(Clock::now()) - requested_ticks;
    }

    [[nodiscard]] TimePoint start() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return start_;
    }

    [[nodiscard]] Duration since_start() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return Clock::now() - start_;
    }

    [[nodiscard]] Snapshot snapshot() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        auto current = ticks_at(Clock::now());
        return {generation_, current, current - guest_time_offset_, start_};
    }

    // A rebase is only legal after the old guest memory has no owners.
    // The host reset controller supplies these predicates from real joins.
    struct StopProof {
        bool worker_joined;
        bool producers_closed;
        bool permits_drained;
        bool guest_refs_released;
    };

#ifdef GOEMON_JP_EXPERIMENTAL_RESET_BACKEND_ACTIVE
    [[nodiscard]] bool rebase_after_verified_exit(
        std::uint64_t expected_generation, StopProof proof) noexcept {
        return try_rebase(expected_generation, proof);
    }
#endif

#ifdef GOEMON_JP_STAGE18_TEST_REBASE
    using TestStopProof = StopProof;
    // Host-test-only. No production build can change generation here;
    // a real rearm will need validated worker, publisher and memory proofs.
    struct TestStopProof {
        bool worker_joined;
        bool producers_closed;
        bool permits_drained;
        bool guest_refs_released;
    };
    [[nodiscard]] bool rebase_for_test(std::uint64_t expected_generation,
                                       TestStopProof proof) noexcept {
        return try_rebase(expected_generation, proof);
    }
#endif

private:
    [[nodiscard]] bool try_rebase(std::uint64_t expected_generation,
                                  StopProof proof) noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        if (generation_ != expected_generation ||
            generation_ == std::numeric_limits<std::uint64_t>::max() ||
            !proof.worker_joined || !proof.producers_closed ||
            !proof.permits_drained || !proof.guest_refs_released) {
            return false;
        }
        start_ = Clock::now();
        guest_time_offset_ = 0;
        ++generation_;
        return true;
    }

    [[nodiscard]] std::uint64_t ticks_at(TimePoint t) const noexcept {
        const std::uint64_t micros = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(t - start_).count());
        return (micros * counter_per_ms_) / 1000;
    }

    mutable std::mutex mutex_;
    const std::uint64_t counter_per_ms_;
    std::uint64_t generation_;
    TimePoint start_;
    std::uint64_t guest_time_offset_ = 0;
};

}  // namespace goemon_jp::reset
