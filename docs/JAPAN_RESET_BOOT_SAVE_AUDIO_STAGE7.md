# Japanese native v0.2.12-dev — boot/save/audio lifecycle preflight (stage 7)

## Baseline

Ubuntu gameplay has verified the v0.2.11 native event worker census:
VI, RT64 graphics, and SP-task workers were active during gameplay and
joined normally on application exit. Five guest OSThread host workers
remained active, including three blocked receivers. The timer joined;
F8 remains diagnostic-only. The scene 129 file-80 fix is inherited.

## Native ownership facts from pinned N64ModernRuntime

- The native **Game Start Thread** originates in
  \`librecomp/src/recomp.cpp\`, calls \`ultramodern::preinit\`, then runs
  \`wait_for_game_started\`. The Japanese boot entrypoint executes
  synchronously inside this host thread. On ordinary application exit,
  it joins before the timer, event workers, cleaner, save worker and
  RDRAM unmap.
- The **saving thread** is in \`librecomp/src/pi.cpp\`, not
  \`ultramodern/src/events.cpp\`. Game calls queue updates through a
  semaphore and a save buffer. The saving thread coalesces updates,
  writes a temporary file, and finalizes the backup-based save file.
  Its normal-exit join occurs after the event workers and guest cleaner.
- The runtime's **audio.cpp** invokes synchronous sample-buffer callbacks.
  The PC frontend in \`src/main/main.cpp\` owns the SDL audio device
  and its queued playback. The native audio callback is **not** proof
  that the SDL audio device has drained or that audio is stopped.

## Added in v0.2.12-dev

Opt-in \`GOEMON_JP_BOOT_STAGE7=ON\`, depending on event stage 6 and
all earlier reset-stage flags. The original N64ModernRuntime submodule
remains unchanged. CMake generates separate build-tree sources:

- \`recomp_stage7.cpp\`: composes the existing stage-1 timer lifecycle
  patch, adds native Game Start Thread and guest-boot-entry RAII
  activity tracking, counts entrypoint calls, and reports the native
  thread join **only after its actual std::thread::join**.
- \`pi_stage7.cpp\`: tracks save-worker initialization/activity/join,
  actual backup-based save I/O activity, three save-write signal sites,
  flush attempts and successful finalizations. **It does not change
  save bytes, filenames, coalescing, timing or file operations.**
  A successful file finalization is not equivalent to fsync/durability,
  so reports explicitly deny proof of save durability.
- \`audio_stage7.cpp\`: counts synchronous runtime audio handoffs,
  submitted samples, initialization, and concurrent dispatch activity.
  The original callback and audio data remain unchanged.

The frontend's F8 handler reads SDL queued playback bytes using
\`SDL_GetQueuedAudioSize\` and does not pause/clear/reopen the device.

The generator fails closed on missing pinned source anchors and repeated
application. Outputs use content-addressed unchanged-file writing.
JP build identity becomes \`v0.2.12-dev\`, with an explicit
\`[boot-save-audio-audit]\` label; the USA semantic version remains
v0.2.3-dev.

## F8 and normal-exit diagnostics

F8 still logs all earlier guest and native event reports, followed by:

```text
[Goemon JP native boot] worker=1 entry_active=1 entries=1 joined=0; no coordinated stop or memory reset.
[Goemon JP save audit] initialized=1 worker=1 joined=0 file_io=0 write_signals=N flush_attempts=N flush_ok=N; pending/durable writes unproven.
[Goemon JP audio audit] initialized=1 callbacks=1 dispatch_inflight=N chunks=N samples=N; SDL device unverified.
[Goemon JP SDL audio] device=N queued_bytes=N; playback still active.
```

Values vary during gameplay. The entrypoint-active flag may differ if
the game is in another phase. On normal application exit expect:

```text
[Goemon JP boot exit] joined=1 entry_active=0; PC app shutdown only.
[Goemon JP runtime] Timer worker joined cleanly.
[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 pending_gfx=N pending_sp=N; event-only shutdown.
[Goemon JP save exit] joined=1 worker=0 file_io=0 write_signals=N flush_ok=N; save-only shutdown, durability unproven.
```

The thread cleaner also prints its existing guest-thread counts.
No diagnostic indicates that all guest threads terminated or that
reset is available.

## Ubuntu test and build

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-boot-save-audio-stage7
git switch feature/japan-reset-boot-save-audio-stage7 2>/dev/null ||
  git switch --track origin/feature/japan-reset-boot-save-audio-stage7
git pull --ff-only

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py
python3 tools/japan_port/test_guest_quiescence_stage3.py
python3 tools/japan_port/test_queue_cleaner_stage4.py
python3 tools/japan_port/test_guest_join_stage5.py
python3 tools/japan_port/test_native_events_stage6.py
python3 tools/japan_port/test_native_boot_save_audio_stage7.py
python3 tools/japan_port/test_jp_file80_data_fixups.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON \
  -DGOEMON_JP_JOIN_STAGE5=ON \
  -DGOEMON_JP_EVENTS_STAGE6=ON \
  -DGOEMON_JP_BOOT_STAGE7=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
SH
```

Expected version includes the exact Git build commit and all previous
build-mode labels followed by \`[boot-save-audio-audit]\`.
Because the script uses \`bash -e\`, it will not run an old executable
after a failed source test or build.

Launch the compiled game:

```bash
cd ~/Goemon64Recomp-JP
./build-generated/japan-native-game/Goemon64RecompiledJP
```

Play normally, re-enter scene 129, press F8 once, then exit normally.
Confirm no new crash, sound corruption or save-file regression. Logs
should include the four added F8 reports and new boot/save exit reports.

## Remaining true-reset requirements

Stage 7 adds **observability only**. A real N64 soft reset must still
establish a generation-scoped stop coordinator, handle guest threads
that may never yield, drain guest and event queues, preserve the SDL
window/RT64 context, account for in-flight SDL audio playback, flush
or retain save updates without loss, and reinitialize N64 boot/RDRAM
state. The existing five guest threads remain live until a future
coordinated stop. Neither stop request nor memory reset is invoked here.

Native compilation and gameplay proof are pending. This is a draft
preflight, not an implemented F8 reset.
