# v0.2.6-dev: guest-thread reset blockers audit

## Scope

The verified **v0.2.5-dev** build (`timer-stage1`) successfully
joined its timer worker on normal Ubuntu game exit. That removed one
lifetime risk but did not make in-process N64 reset safe.

This stage adds an **observational guest-thread audit** to identify
what remains alive during gameplay. No reset or forced thread shutdown
is attempted. F8 must not touch guest RAM, free a context, terminate
a native thread or relaunch the process.

The audit uses a generated `threads.cpp` in the CMake build tree.
The pinned N64ModernRuntime Git submodule is unchanged.

## Counter semantics

During gameplay, F8 prints:

```text
[Goemon JP reset] Request received; native reset backend not installed. Game continues without modification.
[Goemon JP reset audit] created=N finished=N joined=N active=N unjoined=N; reset unavailable (guest teardown pending).
```

- `created`: guest OSThread host threads whose initialisation was acknowledged
- `finished`: guest threads reaching the end of the native trampoline
- `joined`: completed native threads joined by the existing cleaner
- `active`: created minus finished (minimum zero)
- `unjoined`: finished minus joined (minimum zero)

The counters are sampled concurrently and are only a diagnostic.
Even if active=0 and unjoined=0, **reset remains disabled**: VI/RSP,
audio, timer, message queue and overlay state still require quiescence.

Version output identifies both experimental stages:

```text
Goemon 64: Recompiled JP v0.2.6-dev (abc123def0) [timer-stage1] [threads-audit]
```

USA remains at source version v0.2.3-dev. Audit and timer stages are
OFF by default; the audit requires the timer stage.

## Ubuntu test

```bash
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-guest-thread-audit
git switch --track origin/feature/japan-reset-guest-thread-audit

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
./build-generated/japan-native-game/Goemon64RecompiledJP
```

Press F8, play normally, change areas, then press F8 again. Confirm
the counts are plausible; the game must **not** reset or crash.
Exit through the game's usual Exit option. Expected normal-exit log:

```text
[Goemon JP runtime] Timer worker joined cleanly.
```

Do not run the old executable after a failed compile. Use `set -e` or
`&&` chaining and check the version after a successful link.

## Still required for real N64 reset

The next stage must implement a cooperative guest-generation barrier
that stops and joins all guest OSThreads, including threads blocked
on the scheduler or N64 message queues. Then quiesce VI/RSP/audio,
drain external messages, reset overlays, RDRAM and CPU state, and
re-enter the Japanese boot sequence while preserving the same
process, SDL window, stored ROM and save files.

Passive counters do not themselves make resetting safe.
