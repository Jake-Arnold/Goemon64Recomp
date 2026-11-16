# Japanese native PC port — v0.2.9-dev reset runtime, stage 4

## Scope and verified baseline

The earlier v0.2.8-dev file-80 pointer correction is included. The user
confirmed that the previously crashing **scene 129 now loads correctly**.
The earlier file-56 overlay pointer correction is also retained.

This experimental version works **only on the native Japanese PC port**.
F8 is **diagnostic-only**. No guest reset, process restart, ROM rebuild,
save modification, or RDRAM clearing is performed.

The pinned N64ModernRuntime submodule is not modified: private runtime
sources are generated into the existing native CMake build directory.

## New in stage 4

1. A counter of blocked N64 guest-message *send* and *receive* waits, with
   RAII cleanup so cancellation will not leave active counters inflated.
2. An indefinite external-message wait now polls every 10 ms and checks
   the stage-3 cooperative-stop flag. The timed external-message wait
   also checkpoints on both received-message and timeout paths.
3. A normal-exit thread cleaner continues consuming **already queued**
   completed guest contexts until its queue has remained empty for one
   polling interval after shutdown. Existing joining and registry
   removal semantics are retained.
4. A final cleaner diagnostic reports created, finished and joined
   guest-thread counts. This is **not proof that every live guest has
   terminated**, and must never be treated as permission to clear RAM.
5. The Japanese version is incremented from v0.2.8-dev to **v0.2.9-dev**,
   with its exact Git commit and an additional `[queue-audit]` label.
   The USA source version remains v0.2.3-dev.

Stage 4 requires all three earlier runtime stages enabled, but is OFF
by default. As these build experiments replace a shared runtime static
library within that CMake build directory, the resulting USA executable
is **not validated** under stage 4.

## Ubuntu compile and regression test

Run from the native JP source tree. Use `bash -e` so a failed test or
build cannot be mistaken for a new executable when an older binary
still exists.

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP

git fetch origin feature/japan-reset-queue-cleaner-stage4
git switch feature/japan-reset-queue-cleaner-stage4 2>/dev/null ||
  git switch --track origin/feature/japan-reset-queue-cleaner-stage4
git pull --ff-only

python3 tools/japan_port/test_jp_file80_data_fixups.py
python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py
python3 tools/japan_port/test_guest_quiescence_stage3.py
python3 tools/japan_port/test_queue_cleaner_stage4.py

# The already-validated scene-129 source fix must not be lost.
grep -q 'jp_relocate_file_80_data' \
  build-generated/japan/RecompiledFuncs/funcs_8.c

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
SH
```

Expected version line:

```text
Goemon 64: Recompiled JP v0.2.9-dev (<commit>) [timer-stage1] [threads-audit] [guest-prep] [queue-audit]
```

Launch the binary from the same root directory:

```bash
cd ~/Goemon64Recomp-JP
./build-generated/japan-native-game/Goemon64RecompiledJP
```

F8 during normal gameplay should still print the existing reset
preflight, thread-count audit and guest-stop-readiness diagnostics, plus:

```text
[Goemon JP queue audit] send_waits=N recv_waits=N blocked_send=N blocked_recv=N external_timeouts=N; reset not armed.
```

These numbers are observations, not targets. Confirm normal dialogue,
scene transitions, **scene 129**, and the previous file-56 route remain
playable. On normal Exit, the terminal should print both:

```text
[Goemon JP runtime] Timer worker joined cleanly.
[Goemon JP cleaner] created=N finished=N joined=N active=N unjoined=N; queue drained, guest shutdown NOT proven.
```

Those lines can appear in either order. The process must return to the
shell without a crash or hang. The exit-cleaner message does not imply
`active=0`, because live guest threads still require a coordinated
stop.

## Remaining conditions for actual F8 reset

- One reset coordinator must first stop game-era task submission and
  prevent creation of further guest threads.
- All guest host threads, including blocked ones and non-yielding code,
  must reach cancellation and be joined. A timeout must fail safely
  without clearing memory.
- RSP/VI/audio, graphics tasks and all other workers referencing the
  guest generation must be quiesced and joined.
- Stale external-message and OSThread queues need correct reset semantics.
- Reinitialise overlay maps, heap, guest RDRAM/CPU state, and the boot
  generation while keeping the same Linux PID/SDL window and save files.
- Validate repeated reset from gameplay and buildings and save
  persistence. Only then may F8 call the reset coordinator.

**Nothing in v0.2.9-dev yet exercises the stop-request primitive.**
