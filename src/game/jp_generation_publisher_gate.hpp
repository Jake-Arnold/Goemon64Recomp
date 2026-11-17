#pragma once

// JP stage14: generation-tagged, admission-closed producer fence.
// This header is also exercised by a standalone ROM-free host test.
// IMPORTANT: no rearm/reopen API is provided until all generation-reset
// proofs exist. Close is currently valid ONLY for normal PC app exit.

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <utility>

namespace goemon_jp::reset {

class PublisherGate final {
public:
    struct Snapshot {
        std::uint64_t generation;
        std::uint64_t accepted;
        std::uint64_t rejected;
        std::uint64_t in_flight;
        bool open;
    };

    class Permit final {
        friend class PublisherGate;

        explicit Permit(PublisherGate* gate) noexcept : gate_(gate) {}

    public:
        Permit() = default;
        ~Permit() { release(); }
        Permit(const Permit&) = delete;
        Permit& operator=(const Permit&) = delete;

        Permit(Permit&& other) noexcept : gate_(std::exchange(other.gate_, nullptr)) {}
        Permit& operator=(Permit&& other) noexcept {
            if (this != &other) {
                release();
                gate_ = std::exchange(other.gate_, nullptr);
            }
            return *this;
        }
        [[nodiscard]] explicit operator bool() const noexcept {
            return gate_ != nullptr;
        }

        void release() noexcept {
            if (auto* gate = std::exchange(gate_, nullptr)) {
                gate->release_one();
            }
        }

    private:
        PublisherGate* gate_ = nullptr;
    };

    explicit PublisherGate(std::uint64_t generation = 1) noexcept :
        generation_(generation) {}
    PublisherGate(const PublisherGate&) = delete;
    PublisherGate& operator=(const PublisherGate&) = delete;

    // A permit covers the COMPLETE enqueue, not just a momentary check.
    // Publishing must not begin after the close operation acquires mutex_.
    [[nodiscard]] Permit try_acquire() noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        if (!open_) {
            ++rejected_;
            return {};
        }
        ++in_flight_;
        ++accepted_;
        return Permit{this};
    }

    // Fails closed on timeout: never reopens, even when a late producer exits.
    // Must be called after native/guest producers have joined on PC exit.
    [[nodiscard]] bool close_for_pc_exit(
        std::chrono::milliseconds timeout) noexcept {
        std::unique_lock<std::mutex> lock(mutex_);
        open_ = false;
        return idle_.wait_for(lock, timeout, [this] {
            return in_flight_ == 0;
        });
    }

    [[nodiscard]] Snapshot snapshot() const noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        return {generation_, accepted_, rejected_, in_flight_, open_};
    }

private:
    void release_one() noexcept {
        std::lock_guard<std::mutex> lock(mutex_);
        // Every non-empty Permit owns exactly one counted lease.
        --in_flight_;
        if (in_flight_ == 0) {
            idle_.notify_all();
        }
    }

    mutable std::mutex mutex_;
    std::condition_variable idle_;
    const std::uint64_t generation_;
    std::uint64_t accepted_ = 0;
    std::uint64_t rejected_ = 0;
    std::uint64_t in_flight_ = 0;
    bool open_ = true;
};

} // namespace goemon_jp::reset
