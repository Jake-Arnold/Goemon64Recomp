# JP v0.2.16-dev — Stage 9: bounded guest shutdown on normal PC exit

## Purpose

Previous Ubuntu exit logs showed five active, unjoined guest OSThreads. The old
cleaner gave up after 10 ms of an empty deletion queue, even though other guest
threads were still alive. No in-process F8 reset is currently possible.

Stage 9 introduces an opt-in, **normal-application-exit-only** stop/join
experiment. It does NOT call the stop API when F8 is pressed.

## Changes

- CMake `GOEMON_JP_EXIT_STAGE9=ON` (default OFF; requires stage 8 and all older stages).
- Generated `threads.cpp` retains the cleaner up to 1500 ms after application
  exit, or until the stop request is armed and all created guests have joined.
- Generated `recomp_stage9.cpp` invokes the cooperative guest stop request
  **after joining the native boot thread**, and waits up to 900 ms for all
  guest host threads to finish and join.
- All existing timer, event and save joins remain in their original order.
- `munmap(rdram)` is conditional on a *successful* guest join proof. If even
  one guest remains, RDRAM stays mapped until OS process termination.
- No ROM/submodule/USA/Goemon Toolkit changes; the Sasuke bomb fix is inherited.

## Expected diagnostics

```text
[Goemon JP guest exit stage9] joined=1; PC exit only; F8 not armed.
[Goemon JP cleaner] created=5 finished=5 joined=5 active=0 unjoined=0
```

If stopping fails, this is a **safe failure** and the log must instead contain:

```text
[Goemon JP guest exit stage9] joined=0; PC exit only; F8 not armed.
[Goemon JP guest exit stage9] RDRAM retained: guest join proof failed; OS process exit will reclaim it.
```

### Ubuntu tests and build

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-guest-exit-drain-stage9
git switch feature/japan-reset-guest-exit-drain-stage9 2>/dev/null || \
  git switch --track origin/feature/japan-reset-guest-exit-drain-stage9
git pull --ff-only

python3 tools/japan_port/test_guest_exit_stage9.py
python3 tools/japan_port/test_jp_sasuke_bomb_camera_fix.py
python3 tools/japan_port/test_jp_file80_data_fixups.py
python3 tools/japan_port/test_persistent_session_logs.py

for test in \
  test_reset_preflight \
  test_timer_runtime_stage1 \
  test_guest_threads_stage2 \
  test_guest_quiescence_stage3 \
  test_queue_cleaner_stage4 \
  test_guest_join_stage5 \
  test_native_events_stage6 \
  test_native_boot_save_audio_stage7 \
  test_graphics_queue_stage8
do
  python3 "tools/japan_port/$test.py"
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
  -DGOEMON_JP_EXIT_STAGE9=ON
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
```

Expected `v0.2.16-dev`, Git SHA and `[guest-exit-drain]`.

## Runtime acceptance

Play normally, test Sasuke bomb explosions in scene 307 and scene 129 loading.
Press F8 to verify that it remains diagnostic-only, then exit normally.
Inspect `~/.local/state/goemon64recomp-jp/logs/latest.log` for guest exit
and cleaner lines plus timer, event and save exit reports. A failed join
must retain mapped memory and still allow the process to exit.

## Not yet a real F8 reset

Live worker-generation stop, graphics/SP/VI task settling, save/audio
barrier, scheduler and memory reinitialization, and same-PID N64 boot
reentry remain unimplemented. The 13 stage-9 source regression tests
are authored; native Ubuntu compile and gameplay verification are pending.
