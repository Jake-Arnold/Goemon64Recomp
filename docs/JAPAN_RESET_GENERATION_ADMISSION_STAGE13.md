# Japanese native v0.2.20-dev — Stage13: independent reset-request admission

## Evidence from Ubuntu and remaining Stage12 gate

The most recent live Ubuntu F8 run still shows:
```text
[Goemon JP live preflight stage11] initialized=1 vi=1 gfx=1 sp=1 pending_gfx=0 pending_sp=1 gfx_submitted=92 gfx_completed=92 actions_approx=0 config_open=1 blockers=0x97 ready=0; guest/boot/timer/audio/save/input fences unproven; F8 diagnostic only, no generation stop or RDRAM reset.
```
The native game-entry routine had returned, but its worker was not joined;
five guest threads and three blocked receives remained. Stage11 is behaving
as designed. The **Stage12 normal PC exit audit has not yet been supplied**
and is not claimed as Ubuntu-verified.

## The first generation coordinator

Unlike the current runtime-wide `exited` application-shutdown flag, the new
host-only `goemon_jp::reset::Coordinator` is independent of application
exit, guest memory and the renderer. It has:

- A monotonically increasing *request ticket* for each one-shot F8 event.
- A dedicated generation identity (currently permanently `1`).
- A lifecycle phase enum: Running, StopRequested, Quiescing, Stopped,
  Reinitializing, FailedClosed.
- Explicitly named future proof requirements for guest creation and joins,
  native boot, VI/GFX/SP, host action queue, timer epoch, SDL/audio callback,
  save durability, input/config publishing and scheduler/overlay/RDRAM.
- A deliberately **non-admitting** entrypoint
  `record_unarmed_request()`: it increments the ticket counter and returns
  `BackendNotInstalled` without retaining a pending stop, changing phase,
  advancing generation, touching RDRAM, or publishing shutdown work.

There is **no** method to install a live backend, update phase, mark
proofs or change generation. The state declarations define a boundary
for the next implementation; they are not yet a live stop controller.

The coordinator is header-only in `src/game/jp_generation_coordinator.hpp`.
This avoids altering the pinned N64ModernRuntime, USA native executable,
linker inputs or generated Japan ROM sources.

## Opt-in native build

`GOEMON_JP_GENERATION_STAGE13=ON` defaults OFF and requires Stages1–12.
The standalone Japanese executable reports `v0.2.20-dev` with exact
Git fingerprint and `[generation-admission]` build tag. USA remains
`v0.2.3-dev`.

F8 remains remappable, one-shot and disabled while remapping input. The
existing Stage11 live census still runs. After that, Stage13 prints:

```text
[Goemon JP generation stage13] generation=1 request=N phase=0 admitted=0 backend=0 verified_fences=0x000 required_fences=0x3FF reason=backend-not-installed; no guest stop, no RDRAM reset.
```

`phase=0` is Running. Repeated distinct F8 press/release cycles should
produce tickets 1,2,3 without altering game state or quitting the window.

## Verification

Local independent host C++ test **actually executed** before pushing:
```text
g++ -std=c++20 -Wall -Wextra -Werror -O2 -pthread \
  tools/japan_port/test_generation_coordinator_stage13.cpp \
  -o /tmp/jp_stage13_test
/tmp/jp_stage13_test
Stage13 host-only coordinator tests passed: 4001 unique rejected requests, generation=1, phase=running
```

This exercised 8 concurrent threads generating 500 requests each, plus an
initial request; checked unique contiguous tickets, immutable generation,
Running phase and no admitted request. It does **not** prove compiled
integration with the Japanese native game.

The new `test_generation_coordinator_stage13.py` adds source/flag/one-shot
contracts and recompiles/runs the concurrency test with the local C++
compiler. Existing Stage1–12 version assertions now expect `0.2.20-dev`.
The full Python test suite, CMake native build and live gameplay run are
**not yet verified**.

## Ubuntu build and test procedure

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-generation-coordinator-stage13
git switch feature/japan-reset-generation-coordinator-stage13 2>/dev/null ||
  git switch --track origin/feature/japan-reset-generation-coordinator-stage13
git pull --ff-only

for test in \
  test_reset_preflight \
  test_timer_runtime_stage1 \
  test_guest_threads_stage2 \
  test_guest_quiescence_stage3 \
  test_queue_cleaner_stage4 \
  test_guest_join_stage5 \
  test_native_events_stage6 \
  test_native_boot_save_audio_stage7 \
  test_graphics_queue_stage8 \
  test_guest_exit_stage9 \
  test_action_drain_stage10 \
  test_live_preflight_stage11 \
  test_exit_barrier_stage12 \
  test_generation_coordinator_stage13 \
  test_persistent_session_logs \
  test_jp_file80_data_fixups \
  test_jp_sasuke_bomb_camera_fix
do
  python3 "tools/japan_port/${test}.py"
done

python3 tools/japan_port/jp_sasuke_bomb_camera_fix.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --source build-generated/japan/RecompiledFuncs/funcs_32.c \
  --output build-generated/japan/RecompiledFuncs/funcs_32.c --in-place

cmake --build build-generated/japan-native-lib --parallel 4
cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON \
  -DGOEMON_JP_JOIN_STAGE5=ON \
  -DGOEMON_JP_EVENTS_STAGE6=ON \
  -DGOEMON_JP_BOOT_STAGE7=ON \
  -DGOEMON_JP_GRAPHICS_STAGE8=ON \
  -DGOEMON_JP_EXIT_STAGE9=ON \
  -DGOEMON_JP_ACTION_STAGE10=ON \
  -DGOEMON_JP_LIVE_STAGE11=ON \
  -DGOEMON_JP_BARRIER_STAGE12=ON \
  -DGOEMON_JP_GENERATION_STAGE13=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
```

With gameplay running, press and release F8 twice. Confirm ticket
increments, `admitted=0` both times, and the game continues normally.
Quit through the normal Exit path and confirm the Stage12 **exit barrier**
line after the save worker exits. This last check is still outstanding.

## Next stage: make stop possible without enabling it blindly

Future actual F8 reset work requires a separate, backend-owned
generation-stop operation and publish fences for each subsystem.
The first live stop must prove guest worker interruption with bounded
timeout and an irreversible **FailedClosed** state if unsafe to reuse RAM;
it cannot invoke process-wide `exited` or assume empty host queues prove
quiescence. Timer and VI/SP workers must be reconstructible per generation,
saves durable and SDL audio settled. No same-process reboot is enabled in
this stage.
