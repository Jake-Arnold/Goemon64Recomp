# Japanese native v0.2.25-dev — Stage18 synchronized timer epoch state

## Ubuntu evidence: Stage17 verified on 17 November 2026

The latest user-supplied F8 capture during live Japanese gameplay shows:

```text
[Goemon JP timer producer stage17] generation=1 open=1 inflight=0 accepted=0 rejected=0 f8_close=0 epoch_rearm=unproven; no live reset.
```

Normal PC exit then reports:

```text
[Goemon JP timer exit stage17] producers_drained=1 worker_joined=1 open=0 inflight=0 accepted=0 rejected=0 timer_safe=1 epoch_rearm=unproven; normal PC exit only.
[Goemon JP runtime] Timer worker joined cleanly.
[Goemon JP cleaner] created=5 finished=5 joined=5 active=0 unjoined=0; queue drained, guest shutdown NOT proven.
[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 pending_gfx=0 pending_sp=0; event-only shutdown.
[Goemon JP save finalize stage16] mutated=0 finalized_epoch=0 final_attempt=0 finalized=1 durable=unproven; PC exit only, F8 disabled.
[Goemon JP exit barrier stage12] guest=1 boot=1 native=1 graphics=1 action=1 save=1 audio_dispatch=1 known_joined=1 timer_epoch=unproven sdl_audio=unproven producer_fences=unproven restart=0; PC exit only, F8 disabled.
[Goemon JP SDL audio exit stage15] permit_drained=1 accepted=2454 rejected=0 inflight=0 queued_before=0 queued_after=0 device_closed=1 confirmed=1; PC exit only, no live reset or generation rearm.
```

Stage17's timer fence and combined exit check passed. **No osSetTimer/osStopTimer publications were observed** (accepted=0); this does not exercise timer API calls or new-generation start. Stage16 saw no dirty save writes.

## New Stage18 implementation

JP-only, **default-off** `GOEMON_JP_TIMER_EPOCH_STAGE18=ON` requires Stage17. The CMake build tree generates `timer_stage18.cpp` from the already generated Stage17 timer source; pinned N64ModernRuntime and ROM are unchanged. USA stays v0.2.3-dev.

Stage18 replaces the two unguarded global timer fields:

```cpp
static high_resolution_clock::time_point start_time;
static int64_t ostime_offset;
```

with a mutex-protected `goemon_jp::reset::TimerEpochClock`, whose generation identity begins at **1**. Timebase operations are now synchronized across caller threads, including:

- `time_now()`, `osGetCount()`, `osGetTime()` and `osSetTime()`.
- `ticks_to_timepoint()`, `ultramodern::get_start()` and `ultramodern::time_since_start()`.
- Timer-worker wake deadlines and `osSetTimer` timestamp creation continue using the same `46,875` counter ticks per millisecond.

The clock preserves the original tick arithmetic and unsigned subtraction semantics for guest `osGetTime`. It serializes clock origin and offset changes under a single mutex so a future epoch reset can avoid torn state.

### No production rebase yet

`TimerEpochClock::rebase_for_test()` **only exists behind**
`GOEMON_JP_STAGE18_TEST_REBASE`, defined in the standalone C++ host test and **not** in the JP game CMake target. That host-only function:

1. Rejects the wrong expected generation, overflow and missing worker/producer/guest-reference stop proofs.
2. Resets clock origin and guest offset together.
3. Advances generation from 1 to 2.
4. Rejects a second request against obsolete generation 1.

This is a proof of the *clock-state algorithm*, **not** a promise that the live guest timer worker, queue, scheduler, input producer, saving worker, SDL device or ROM entrypoint can be safely restarted. Production never changes timer generation in Stage18.

F8 is read-only and still uses Stage13 `admitted=0 backend=0`. New line:

```text
[Goemon JP timer clock stage18] generation=1 ticks=N guest_time=N synchronized=1 rearm_enabled=0 f8_no_change=1; native reset unavailable.
```

## Verification performed

The new standalone host C++ test was **actually compiled and executed** locally with:

```bash
g++ -std=c++20 -O2 -Wall -Wextra -Werror -pthread \
  -I src/game \
  tools/japan_port/test_timer_epoch_clock_stage18.cpp \
  -o /tmp/jp_timer_epoch_stage18
/tmp/jp_timer_epoch_stage18
```

It passed **three consecutive runs**, including a synthetic generation 1→2 handoff and **6 concurrent threads × 10,000 clock operations** on each run. It also passed a separate `-fsanitize=address,undefined` run with ASan leak detection and UBSan halt-on-error enabled.

New `test_timer_epoch_stage18.py` authors **13 ROM-free regression tests** for exact Stage17 source composition, synchronized timing calls, test-only rebase isolation, no F8 stop, build flag/version and compile/run of the native host test. **The full Python tests and Ubuntu native game/CMake build have not yet been run by the assistant**.

## Ubuntu verification

Retain the prior Japanese build directory with Stage1–17 options enabled:

```bash
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-timer-epoch-state-stage18
git switch feature/japan-reset-timer-epoch-state-stage18 2>/dev/null ||
  git switch --track origin/feature/japan-reset-timer-epoch-state-stage18
git pull --ff-only

python3 tools/japan_port/test_timer_epoch_stage18.py
python3 tools/japan_port/test_timer_producer_fence_stage17.py
python3 tools/japan_port/test_timer_runtime_stage1.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_JP_TIMER_EPOCH_STAGE18=ON
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
```

Expect v0.2.25-dev and `[timer-epoch-clock]`. Press/release F8 during normal gameplay; it should print Stage18 `generation=1 synchronized=1 rearm_enabled=0` and game continues. On normal PC exit, Stage17 `timer_safe=1`, Stage12 `known_joined=1` and Stage15 audio `confirmed=1` should remain unchanged.

## Outstanding real F8 reset prerequisites

A real reset must stop and join live guest OSThread creation/scheduling, VI/GFX/SP worker activity, timer publishers, input/config actions and saving writes *without* toggling process-wide `exited`; prove all old generation owners released guest memory; then initialize a fresh timer **worker/queue**, synchronized epoch, guest RDRAM and overlays, runtime scheduler, audio device and renderer-facing state inside the **same process and SDL window**. Stage18 changes the clock representation, **not** the timer-worker lifetime or reset admission.
