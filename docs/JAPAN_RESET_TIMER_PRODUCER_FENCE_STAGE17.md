# Japanese native v0.2.24-dev — Stage17 timer producer fence

## Verified preceding stages

On 17 November 2026, the user's Japanese Ubuntu run confirmed:

```text
[Goemon JP generation stage13] generation=1 request=1 phase=0 admitted=0 backend=0 verified_fences=0x000 required_fences=0x3FF reason=backend-not-installed; no guest stop, no RDRAM reset.
[Goemon JP guest exit stage9] joined=1; PC exit only; F8 not armed.
[Goemon JP runtime] Timer worker joined cleanly.
[Goemon JP cleaner] created=5 finished=5 joined=5 active=0 unjoined=0; queue drained, guest shutdown NOT proven.
[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 pending_gfx=0 pending_sp=0; event-only shutdown.
[Goemon JP config fence stage14] drained=1 closed=1; normal PC exit only.
[Goemon JP save finalize stage16] mutated=0 finalized_epoch=0 final_attempt=0 finalized=1 durable=unproven; PC exit only, F8 disabled.
[Goemon JP exit barrier stage12] guest=1 boot=1 native=1 graphics=1 action=1 save=1 audio_dispatch=1 known_joined=1 timer_epoch=unproven sdl_audio=unproven producer_fences=unproven restart=0; PC exit only, F8 disabled.
[Goemon JP SDL audio exit stage15] permit_drained=1 accepted=741 rejected=0 inflight=0 queued_before=0 queued_after=0 device_closed=1 confirmed=1; PC exit only, no live reset or generation rearm.
```

Stage16 was verified for **zero save mutations** (`mutated=0`). The dirty save
path remains untested. The timer Stage1 worker was joined, but Stage1
did not prevent late timer producers from calling `osSetTimer` or
`osStopTimer` after that join. Those calls can enqueue work into a
queue no longer serviced and `osSetTimer` also writes a guest timer
object in RDRAM before enqueue.

## Stage17 implementation

New JP-only, default-off flag `GOEMON_JP_TIMER_PUBLISH_STAGE17=ON`
requires Stage16. The generated build-tree `timer_stage17.cpp`
replaces Stage1's generated timer, while `recomp_stage17.cpp`
replaces Stage12's generated normal-exit recomp. Neither the pinned
N64ModernRuntime submodule nor the game ROM is modified.

1. The existing `PublisherGate` from Stage14 is instantiated
   separately for timer producers. It is generation-tagged at 1,
   counts accepted/rejected/in-flight permits, and provides move-only
   RAII leases across the **actual** timer enqueue.
2. `osSetTimer` acquires its lease **before accessing the guest
   OSTimer memory** or enqueueing `AddTimerAction`.
   `osStopTimer` acquires before enqueueing `RemoveTimerAction`.
   Both return `-1` without mutation or queue access when admission
   has closed. Existing behaviour during normal gameplay is unchanged.
3. At **normal application exit only**, `shutdown_timers()`
   closes producer admission first and waits up to 500 ms for all
   outstanding permitted calls to return. It then enqueues the
   Stage1 `ShutdownTimerAction`, joins the real timer thread and
   drains leftover actions. Exit status includes a strict conjunction
   of gate drained, worker joined, queue admission closed, and zero
   in-flight permits.
4. Stage17 adds that timer-exit proof to **both** the Stage9 RDRAM
   `munmap` guard and the Stage12 `known_joined` conjunction.
   If the permit wait times out, `known_joined` is false, and the
   RDRAM mapping is retained until OS process termination. The timer
   worker is still joined for normal PC shutdown. A failed permit
   proof must not be mistaken for guest-memory safety.
5. F8 only reports a read-only `jp_timer_publisher_gate.snapshot()`.
   No generation stop, timers cleared on F8, RDRAM reset, or
   worker/device rearm is implemented.

This is a **real timer producer fence on normal exit**, not proof that
the worker is restartable. The Stage12 string
`timer_epoch=unproven` deliberately remains accurate.

## Expected new live F8 diagnostic

```text
[Goemon JP timer producer stage17] generation=1 open=1 inflight=N accepted=N rejected=N f8_close=0 epoch_rearm=unproven; no live reset.
```

## Expected normal-exit diagnostic

```text
[Goemon JP timer exit stage17] producers_drained=1 worker_joined=1 open=0 inflight=0 accepted=N rejected=N timer_safe=1 epoch_rearm=unproven; normal PC exit only.
```

This should precede the existing
`[Goemon JP runtime] Timer worker joined cleanly.`, Stage12
`known_joined=1`, and the Stage15 SDL closure.
`timer_safe=1` proves **only the timer producer/worker part**,
not the entire RDRAM generation reset.

If this stage fails, the RDRAM must not be unmapped based solely on
the old Stage9 guest join check.

## Ubuntu test procedure

This uses the same `build-generated/japan-native-game` cache that
previously enabled Stages1–16.

```bash
cd ~/Goemon64Recomp-JP

git fetch origin feature/japan-reset-timer-producer-fence-stage17
git switch feature/japan-reset-timer-producer-fence-stage17 2>/dev/null ||
  git switch --track origin/feature/japan-reset-timer-producer-fence-stage17
git pull --ff-only

python3 tools/japan_port/test_timer_producer_fence_stage17.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_exit_barrier_stage12.py
python3 tools/japan_port/test_save_finalize_stage16.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_JP_TIMER_PUBLISH_STAGE17=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
```

During play, press F8 once. Confirm Stage17 `open=1 f8_close=0`
and normal gameplay proceeds. Exit normally. Confirm Stage17
`producers_drained=1 worker_joined=1 timer_safe=1`, Stage12
`known_joined=1`, and Stage15 `confirmed=1`.

## Verification limits

- Stages 12, 14, 15 and the zero-mutation path of Stage16:
  **Ubuntu run verified by supplied logs**.
- Stage17: 12 ROM-free Python tests authored, 18 inherited version
  assertions updated. Native full CMake build and Ubuntu gameplay
  have **not yet been run/verified**.
- No claim of an actual F8 reset, timer epoch rearm, save durability,
  SDL audio reopen, RDRAM memory reset, or in-process game reentry.

## Remaining live-reset barriers

A real generational lifecycle must coordinate a **live** stop of
guest creation, guest schedulers and message queues, VI/GFX/SP event
workers, input/config producers, timers and saving; prove each
worker joined; initialize a fresh timer epoch and queue; reload
recompiled guest state and overlays without dangling native pointers;
reopen SDL audio inside the existing window; and replay the entrypoint
only with all fences proven. Stage17 does not arm this backend.
