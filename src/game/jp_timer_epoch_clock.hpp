#pragma once

// Japanese recomp Stage18: synchronized timer timebase per guest generation.
// Normal builds expose time reads and osSetTime only. Experimental builds
// expose a guarded rebase after the complete old-generation exit barrier.
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
        return ticks_at(effective_now());
    }

    [[nodiscard]] std::uint64_t guest_time() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return ticks_at(effective_now()) - guest_time_offset_;
    }

    void set_guest_time(std::uint64_t requested_ticks) noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        guest_time_offset_ = ticks_at(effective_now()) - requested_ticks;
    }

    [[nodiscard]] TimePoint start() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return start_;
    }

    [[nodiscard]] Duration since_start() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return effective_now() - start_;
    }

    [[nodiscard]] Snapshot snapshot() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        auto current = ticks_at(effective_now());
        return {generation_, current, current - guest_time_offset_, start_};
    }

    // Freeze N64 logical time, not wall time. Resume shifts the origin so
    // pending VI and timer deadlines cannot catch up for the paused period.
    [[nodiscard]] bool set_paused(bool pause) noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        if (paused_ == pause) {
            return false;
        }
        const auto now = Clock::now();
        if (pause) {
            paused_at_ = now;
            paused_ = true;
        } else {
            start_ += now - paused_at_;
            paused_ = false;
        }
        return true;
    }

    [[nodiscard]] bool is_paused() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return paused_;
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
    // Test-only alias to the same proof shape used by the experimental
    // runtime rearm. Unstable gameplay feature is separately opt-in.
    using TestStopProof = StopProof;
    [[nodiscard]] bool rebase_for_test(std::uint64_t expected_generation,
                                       TestStopProof proof) noexcept {
        return try_rebase(expected_generation, proof);
    }
#endif

private:
    [[nodiscard]] TimePoint effective_now() const noexcept {
        return paused_ ? paused_at_ : Clock::now();
    }

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
        paused_at_ = start_;
        paused_ = false;
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
    TimePoint paused_at_{};
    bool paused_ = false;
    std::uint64_t guest_time_offset_ = 0;
};

}  // namespace goemon_jp::reset
