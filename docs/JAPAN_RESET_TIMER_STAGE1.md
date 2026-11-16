# Japanese native reset — v0.2.5-dev timer lifecycle experiment

## Background

Two F8 input events in **v0.2.4-dev** were confirmed by Ubuntu testing.
That proves the binding/edge detection work. It is not a game reset.

The original pinned N64ModernRuntime timer worker is detached and loops
indefinitely, retaining pointers into guest RDRAM. Clearing or remapping
guest memory while that thread runs would be unsafe.

## Changes in v0.2.5-dev

- Experimental `GOEMON_JP_TIMER_STAGE1` CMake option, default **OFF**.
- `tools/japan_port/patch_timer_runtime.py` generates private
  build-tree copies of the pinned timer and recomp startup sources.
- Timer shutdown uses a queue action and **join**, waking the worker
  whether its queue is empty or timers are scheduled.
- Shutdown is checked before dereferencing another guest OSTimer.
- `recomp::start` joins the timer on ordinary application
  exit, before unmapping RDRAM.
- The pinned `lib/N64ModernRuntime` submodule remains untouched.
- Japanese version increments to **v0.2.5-dev**, preserving exact
  Git commit identification in the launcher, window, and `--version`.
- The USA source version remains **v0.2.3-dev**.

**F8 does not yet reset gameplay.** Its preflight log remains unchanged.

The experimental CMake build uses runtime static libraries shared with
its USA target, so this timer stage is not production-validated for USA.

## Ubuntu test

```bash
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-runtime-timer
git switch --track origin/feature/japan-reset-runtime-timer

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON -DGOEMON_JP_TIMER_STAGE1=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
./build-generated/japan-native-game/Goemon64RecompiledJP
```

After testing F8 (no reset expected), quit normally. The console should show:

```text
[Goemon JP runtime] Timer worker joined cleanly.
```

Success criteria:

1. No crash or hang on normal exit.
2. F8 logs once per press, without closing game or restarting process.
3. Existing JP saving and overlay-56 transition behaviour still works.
4. Version and Git SHA identify the exact compiled build.
5. `git -C lib/N64ModernRuntime status --short` shows no modifications.

## Still required for genuine in-place reset

Join every guest OSThread and quiesce RSP/PI/VI/audio; drain stale
messages and task queues; reset the overlay/function map, guest RAM,
heap and CPU context; re-enter Japanese game from its boot sequence
while preserving the SDL window, process ID, stored ROM and save data.

The original v0.2.1-dev `execv` process-restart experiment
is permanently rejected.
