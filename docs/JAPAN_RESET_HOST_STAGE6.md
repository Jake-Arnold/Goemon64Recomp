# Japanese native v0.2.11-dev — native VI, RSP and RT64 worker audit (stage 6)

## Scope

The successful scene-129 file-80 fix from v0.2.8-dev and all
v0.2.9–0.2.10 reset work are inherited. This build changes only the
Japanese native recompilation project. It does **not** modify the
Goemon Toolkit, original ROM, USA executable or existing game saves.

The last Ubuntu run of v0.2.10 found five guest OSThreads active and
three blocked in receive queues, with none finished or joined.
This stage investigates the **native event workers** that may access
the same memory while a future reset takes place.

## Pinned-runtime findings

The pinned N64ModernRuntime `fc4592a31414daf0040c19907e0b1976b2e48a67`
creates three native event-worker threads in
`ultramodern/src/events.cpp`:

| Bit | Native worker | Responsibility |
| --- | --- | --- |
| `0x1` | VI thread | Produces retrace and AI events and screen updates |
| `0x2` | Graphics thread | RT64 rendering and RDP display lists |
| `0x4` | RSP task thread | Executes non-graphics RSP tasks |

All three threads are **joined on normal process exit** via
`ultramodern::join_event_threads()`. The RSP worker receives a
null task before join. The graphics worker waits for the existing
`graphics_shutdown_ready` handshake before closing RT64.

Those process-lifetime shutdown paths are **not** a same-window,
in-process N64 reset. A genuine reset must preserve the renderer
while halting new VI/RSP submissions and in-flight RDRAM accessors.

## Implementation

The new CMake flag `GOEMON_JP_HOST_STAGE6=ON` defaults OFF
and requires all earlier stages, including
`GOEMON_JP_JOIN_STAGE5=ON`. It generates a build-local
`events.cpp` without modifying the pinned submodule.

- Separate `started`, `active`, and `joined`
  masks for VI, graphics and RSP host workers.
- RAII scopes track when gfx display lists or RSP tasks are in flight.
- Joined bits change **only after** actual host `join()` returns.
- The original RSP sentinel, renderer shutdown handshake, and worker
  join order are preserved.
- F8 prints a **read-only** snapshot. Normal PC exit prints which
  event threads joined. Neither report proves guest/boot/save safety.

This snapshot is not a synchronization barrier. All-zero busy bits
would not prove that task queues are empty or new tasks inhibited.

## Version

`v0.2.11-dev (<git SHA>) [timer-stage1] [threads-audit] [guest-prep] [queue-audit] [join-prep] [host-audit]`

The native window title, launcher and `--version` show the
version and exact commit. USA stays at v0.2.3-dev.

## Ubuntu validation

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP

git fetch origin feature/japan-reset-host-worker-stage6
git switch feature/japan-reset-host-worker-stage6 2>/dev/null ||
  git switch --track origin/feature/japan-reset-host-worker-stage6
git pull --ff-only

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py
python3 tools/japan_port/test_guest_quiescence_stage3.py
python3 tools/japan_port/test_queue_cleaner_stage4.py
python3 tools/japan_port/test_guest_join_stage5.py
python3 tools/japan_port/test_native_events_stage6.py
python3 tools/japan_port/test_jp_file80_data_fixups.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON \
  -DGOEMON_JP_JOIN_STAGE5=ON \
  -DGOEMON_JP_HOST_STAGE6=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
SH
```

Launch the executable, load a known-working save and enter scene 129.
Press F8 during gameplay and exit normally.

Illustrative diagnostics:

```text
[Goemon JP native workers] started=0x7 active=0x7 busy=0x0 joined=0x0; VI=1 gfx=2 RSP=4; reset disabled.
[Goemon JP native exit] events_joined=yes started=0x7 active=0x0 busy=0x0 joined=0x7; guest/start/save quiescence NOT proven.
```

Numbers can differ during tasks. The event-workers exit report should
follow the timer join; the cleaner report can appear afterward.

## Safety and remaining work

**F8 remains diagnostic-only.** This stage does not stop guest threads,
suspend the renderer, clear RDRAM, restart the process, reinvoke the
game entrypoint or alter saves.

The next stage must coordinate VI production, RSP and RT64 task
draining while preserving the renderer, guest OSThread stop/join,
and native boot, timers, DMA/event queues, audio and saving. Only
then can N64 RAM, scheduler and overlay state be reinitialized.

Keep the PR draft until Ubuntu compilation, F8 diagnostics, scene 129
and normal exit are tested. Actor-specific rendering defects remain
a separate issue (#13).
