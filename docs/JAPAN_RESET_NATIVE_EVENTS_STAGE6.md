# Japanese native PC port: v0.2.11-dev native event worker census (stage 6)

## Verified baseline

- JP v0.2.8-dev's file-80 pointer relocation allows scene 129 to load.
- JP v0.2.9-dev and v0.2.10-dev compile and run on Ubuntu; F8 is
  diagnostic-only and the application exits normally.
- In the last user trace: five N64 guest host workers are active; three
  guest workers are waiting on N64 message receives; none has finished or
  joined. The timer joins on normal process exit.
- Stage 5's join predicate is **inactive**. It cannot prove an in-process
  reset is safe.

## What this stage adds

The pinned N64ModernRuntime launches **three other native workers**:

1. **VI thread:** drives frame pacing and VI/AI messages, under `exited`.
2. **Graphics thread:** consumes RSP graphics and screen update actions,
   creates and owns the RT64 context, and waits on the graphics shutdown
   semaphore before destroying it.
3. **SP task thread:** executes non-graphics RSP tasks until
   `join_event_threads` enqueues a null task sentinel.

Stage 6 instruments these threads in a private, build-generated
`events.cpp`. Atomic activity flags are set via RAII scopes, so early
returns as well as normal exits clear the flags. Two atomic counters track
submitted-but-not-completed graphics and SP tasks (including the task
currently executing). Only graphics RSP tasks are counted in the graphics
task counter; VI screen updates and config events are not included.

When the native application exits, the original join order is
**retained**: graphics joins, VI joins, null SP task is enqueued, then
the SP task thread joins. Each completed join sets a corresponding
atomic flag. The new exit diagnostic reports joined workers and
remaining tracked tasks.

An internal, **uninvoked** event-only join-readiness predicate requires
all three join flags, all three inactive flags, zero pending graphics/RSP
tasks and a completed event-worker initialization. The predicate is
*not* permission to clear guest RAM: guest host threads, the game-start
thread, the timer, save, DMA, audio and various other workers are outside
its scope, and graphics action queues may still hold entries.

No original submodule source file, ROM, USA version or toolkit code is
modified by this feature branch. The prior file-56 and file-80 fixes
remain intact.

## F8 behaviour

F8 is still strictly diagnostic-only. It adds:

```text
[Goemon JP native workers] vi=1 gfx=1 sp=1 pending_gfx=N pending_sp=N joined=0/0/0; event-only audit, RDRAM reset unavailable.
```

The flags and task counts are dynamic: a 0 can be legitimate before
startup has finished or if a worker exits unexpectedly. A 1 only
confirms the worker is executing, not that it is stopped safely.

At normal application exit, expect:

```text
[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 pending_gfx=N pending_sp=N; event-only shutdown.
```

Along with earlier `[Goemon JP cleaner]` and
`[Goemon JP runtime] Timer worker joined cleanly.` logs.

No guest shutdown is requested and no RAM clearing, title-screen reboot,
window teardown or process re-execution is attempted.

## Ubuntu test commands

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-native-event-preflight-stage6
git switch feature/japan-reset-native-event-preflight-stage6 2>/dev/null ||
  git switch --track origin/feature/japan-reset-native-event-preflight-stage6
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
  -DGOEMON_JP_EVENTS_STAGE6=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
SH
```

Expected semantic version and labels:

```text
v0.2.11-dev (<commit>) [timer-stage1] [threads-audit] [guest-prep] [queue-audit] [join-prep] [native-events-audit]
```

Then launch the game:

```bash
cd ~/Goemon64Recomp-JP
./build-generated/japan-native-game/Goemon64RecompiledJP
```

Enter and leave normal rooms, and confirm scene 129 works. Press F8;
the game must continue without modification. Exit normally, and inspect
the event exit, timer join and guest cleaner diagnostics. Any compiler
errors or worker join hangs are blockers for this stage.

## Outstanding shutdown work

The native boot/start thread and save/audio/timer workers still need a
generation-scoped coordinator. The graphics context cannot simply be
destroyed and recreated mid-frame without coordinating frontend state.
The N64 scheduler, queues, overlay memory, RSP/VI state, ROM pointers,
RT64 texture caches and save ownership must be established safe for
reinitialization before a same-process title-screen reboot is allowed.

This is an **instrumentation milestone, not a reset implementation**.
Keep the PR draft until Ubuntu testing completes.
