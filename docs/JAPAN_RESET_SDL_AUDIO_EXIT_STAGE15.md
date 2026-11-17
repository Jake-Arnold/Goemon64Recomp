# Japanese native v0.2.22-dev — Stage15 SDL audio shutdown fence

## Verified prerequisite: Stage12 + Stage14 Ubuntu normal exit

The user's 17 November 2026 Ubuntu capture proves:

```text
[Goemon JP guest exit stage9] joined=1; PC exit only; F8 not armed.
[Goemon JP runtime] Timer worker joined cleanly.
[Goemon JP cleaner] created=5 finished=5 joined=5 active=0 unjoined=0; queue drained, guest shutdown NOT proven.
[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 pending_gfx=0 pending_sp=0; event-only shutdown.
[Goemon JP gfx queue] submitted=465 started=465 completed=465 pending=0 action_queue_approx=1 joined=1; no generation stop or queue reset.
[Goemon JP config fence stage14] drained=1 closed=1; normal PC exit only.
[Goemon JP action exit stage10] skipped=0 screen=1 config=0 unexpected_graphics=0 pending_gfx=0 remaining_approx=0 expected_only=1; PC exit only, no F8 reset.
[Goemon JP save exit] joined=1 worker=0 file_io=0 write_signals=0 flush_ok=0; save-only shutdown, durability unproven.
[Goemon JP exit barrier stage12] guest=1 boot=1 native=1 graphics=1 action=1 save=1 audio_dispatch=1 known_joined=1 timer_epoch=unproven sdl_audio=unproven producer_fences=unproven restart=0; PC exit only, F8 disabled.
```

And during F8: `generation=1 request=1 phase=0 admitted=0`; graphics
233/233 completed, config producer gate `open=1 inflight=0 accepted=1`;
SDL device 2 had 4,792 queued bytes. These observations prove known
normal-exit predicates and active buffered SDL audio, **not reset**.

## Stage15 implementation

The frontend's actual `src/main/main.cpp` uses `SDL_OpenAudioDevice`
and `SDL_QueueAudio`. Stage7 could only observe queued bytes. Stage15
installs an actual counted callback fence and device close:

- Reuses Stage14's tested `PublisherGate` as a separate
  `jp_sdl_audio_gate{1}`, scoped to the Japanese executable.
- Every `queue_samples()`, `get_frames_remaining()`, and
  `set_frequency()` callback obtains a RAII permit before touching
  audio/converter state. Denied late callbacks do not access SDL.
- **Only after `recomp::start(...)` returns on ordinary PC exit**,
  the gate closes admissions and waits up to 1000 ms for active callbacks
  to return. On timeout, it **does not clear or close** the device.
- When permits are drained, the frontend samples queued bytes,
  pauses the device, clears queued audio, samples again, closes the SDL
  audio device and sets its ID to zero. Reports `confirmed=1` only
  when leases drained, the device closed, and post-clear size is zero.
- F8 remains diagnostic only; Stage13 rejects all reset requests.
  There is **no** mid-game SDL close, new audio device creation,
  memory reset or boot replay.

The SDL teardown is located after `recomp::start()` returns and
therefore after Stage9–14's normal-exit worker/queue path. Its log
will occur **after** the Stage12 `known_joined` line, not inside
Stage12's predicate. A Stage12 result of 1 still does **not** mean
that all audio and save/timer rearm proofs hold.

This stage is **not a live generation-rearm protocol**. It closes one
audio device for normal app exit, with no reopen API in the gate.
Even a confirmed Stage15 exit cannot be reused to restart gameplay
without restoring timers, save ownership, SDL audio and the guest state.

## Expected output on normal exit

```text
[Goemon JP SDL audio exit stage15] permit_drained=1 accepted=N rejected=N inflight=0 queued_before=N queued_after=0 device_closed=1 confirmed=1; PC exit only, no live reset or generation rearm.
```

A timeout yields `permit_drained=0 device_closed=0 confirmed=0`;
the queue/device is intentionally not touched.

## Ubuntu build and regression

Existing build-generated Japanese directory must contain the pinned
runtime and all enabled Stage1–14 options. This branch adds only Stage15.

```bash
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-sdl-audio-exit-stage15
git switch feature/japan-reset-sdl-audio-exit-stage15 2>/dev/null ||
  git switch --track origin/feature/japan-reset-sdl-audio-exit-stage15
git pull --ff-only

python3 tools/japan_port/test_sdl_audio_exit_stage15.py
python3 tools/japan_port/test_config_publisher_fence_stage14.py
python3 tools/japan_port/test_generation_coordinator_stage13.py
python3 tools/japan_port/test_exit_barrier_stage12.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_JP_SDL_AUDIO_STAGE15=ON
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
```

Expect JP v0.2.22-dev, `[sdl-audio-exit]`, and the prior Stage14
`[config-publisher-fence]` build tag. Press/release F8 during gameplay:
the game must continue unchanged and the Stage13 request is rejected.
Then use normal Exit. The new audio line must follow the verified
Stage12 exit line. Record `confirmed`, `inflight`, `queued_before`,
`queued_after`, and `device_closed` explicitly.

## Verification status

- Stage12 normal PC-exit barrier and Stage14 config gate: **actually
  verified** in user-supplied Ubuntu runtime output.
- Stage15: 12 ROM-free source contract tests authored; 16 inherited
  version contracts updated to JP v0.2.22-dev.
- Stage15 standalone CMake/gameplay and SDL teardown: **NOT YET RUN**
  or verified on Ubuntu. Source shape checks cannot substitute.
- No ROM files, assets, generated binaries, or pinned runtime edits
  are included.

## Remaining F8 blockers

Backend admission, live guest worker interruption, new generation
producer ownership/rearm, VI/GFX/SP restart, timer epoch reset, save
flush/durability, SDL audio **reopen per generation**, and RDRAM/
scheduler/overlay/renderer-state reinitialization. This is an
incremental device-closure prerequisite, not a working reset.
