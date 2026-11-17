#pragma once

// Japanese native recomp: Stage13 generation-request admission foundation.
// No runtime shutdown capability is installed in this stage. In particular,
// an F8 observation cannot change the active generation or issue a stop.
// All data here is host-side and independent of guest RDRAM and app `exited`.

#include <atomic>
#include <cstdint>

namespace goemon_jp::reset {

enum class Phase : std::uint8_t {
    Running = 0,
    StopRequested,
    Quiescing,
    Stopped,
    Reinitializing,
    FailedClosed,
};

enum class Rejection : std::uint8_t {
    BackendNotInstalled = 1,
};

// Future generation transitions require independent proofs. These flags
// are a specification, not claims that any proof is currently available.
enum class Fence : std::uint32_t {
    GuestCreation = 1u << 0,
    GuestJoined = 1u << 1,
    NativeBootJoined = 1u << 2,
    ViGfxSpJoined = 1u << 3,
    GraphicsAndActionsSettled = 1u << 4,
    TimerEpochRearmable = 1u << 5,
    AudioDispatchAndSdlSettled = 1u << 6,
    SaveWorkerDurability = 1u << 7,
    InputAndConfigPublishers = 1u << 8,
    SchedulerMemoryAndOverlayReinit = 1u << 9,
};

inline constexpr std::uint32_t kFutureRequiredFenceMask = (1u << 10) - 1u;

struct Attempt {
    std::uint64_t ticket;
    std::uint64_t generation;
    Phase phase;
    Rejection rejection;
};

// This class cannot issue stop or reset: it intentionally has no methods to
// set phase, clear RDRAM, mark fences, advance generation, or install a backend.
class Coordinator final {
public:
    Coordinator() = default;
    Coordinator(const Coordinator&) = delete;
    Coordinator& operator=(const Coordinator&) = delete;

    [[nodiscard]] Attempt record_unarmed_request() noexcept {
        const std::uint64_t ticket =
            attempts_.fetch_add(1, std::memory_order_relaxed) + 1;
        return {ticket, generation_.load(std::memory_order_acquire),
                phase_.load(std::memory_order_acquire),
                Rejection::BackendNotInstalled};
    }

    [[nodiscard]] std::uint64_t attempt_count() const noexcept {
        return attempts_.load(std::memory_order_acquire);
    }

    [[nodiscard]] std::uint64_t generation() const noexcept {
        return generation_.load(std::memory_order_acquire);
    }

    [[nodiscard]] Phase phase() const noexcept {
        return phase_.load(std::memory_order_acquire);
    }

private:
    std::atomic<std::uint64_t> generation_{1};
    std::atomic<std::uint64_t> attempts_{0};
    std::atomic<Phase> phase_{Phase::Running};
};

inline Coordinator& coordinator() noexcept {
    static Coordinator instance;
    return instance;
}

} // namespace goemon_jp::reset
