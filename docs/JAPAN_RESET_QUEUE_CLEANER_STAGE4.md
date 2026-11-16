# Japanese native reset v0.2.9-dev: message-queue and cleaner stage 4

## Scope and baseline

This work continues from the **user-confirmed** scene 129/file-80 data-pointer
fix in v0.2.8-dev, and the earlier stage-1/2/3 timer and guest-thread
instrumentation. No toolkit files are changed.

This release does **not** implement in-process reset. F8 remains
read-only; there are no guest-thread stop requests, RDRAM clearing,
native process re-execution, or boot-entry re-invocations.

## What stage 4 adds

Opt-in CMake flag `GOEMON_JP_QUEUE_STAGE4=ON`, requiring
`GOEMON_JP_GUEST_STAGE3=ON` (which itself requires guest audit and
joinable timer). The pinned N64ModernRuntime source tree remains untouched:
two build-local source overlays are generated.

### N64 message-queue observability

A generated `mesgqueue.cpp` counts:

- `send_waits` and `recv_waits`: cumulative guest context-switch waits
  because a queue was full or empty.
- `blocked_send` and `blocked_recv`: current guest host threads
  suspended within those queue-wait scopes. Their counters unwind even
  when a future cooperative shutdown throws.
- `external_timeouts`: 10 ms timeouts awaiting asynchronous external
  messages. This is a count of polls, **not** a count of queued messages.

The original indefinite `external_messages.wait_dequeue` is replaced
with a 10 ms timed wait. Each timeout and successful dequeue checks the
existing stage-3 cooperative cancellation flag. **That flag is never set
from F8 in this stage.** Existing blocking send/receive paths already
yield through `run_next_thread_and_wait`, which stage 3 instruments.

This is **not** a complete cancellation design. In particular,
`guest_shutdown_checkpoint()` only throws for guest `OSThread` host
trampolines. The native boot/start thread, non-yielding recompiled code,
and external game workers remain potential blockers.

### Cleaner normal-exit drain

The thread cleaner now continues to join contexts that have **already
completed** and entered `deleted_threads`. After application exit is
requested and the queue stays empty for one 10 ms poll, it stops.

An exit log reports `created`, `finished`, `joined`, `active`, and
`unjoined`. An empty deletion queue **does not mean all guest threads
have stopped**; a still-running or paused guest may enqueue later. It
must not be used as a reset barrier. Stage 4 does not join live/blocked
guest threads and does not allow RDRAM reuse.

## Version and diagnostics

The Japanese CLI `--version`, title and launcher include:

```text
v0.2.9-dev (<git commit>) [timer-stage1] [threads-audit] [guest-prep] [queue-audit]
```

USA remains at `v0.2.3-dev`. The scene 129 file-80 fix remains
inherited, and F8 continues to print the existing preflight,
guest-thread and guest-stop reports. Additionally, it prints:

```text
[Goemon JP queue audit] send_waits=N recv_waits=N blocked_send=N blocked_recv=N external_timeouts=N; reset not armed.
```

Normal exit should print a **cleaner audit** and the known **timer joined**
message. Audit numbers are dynamic; there is no expectation that active
guest workers equal zero during normal gameplay or even at normal exit.

## Ubuntu validation

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-queue-cleaner-stage4
git switch feature/japan-reset-queue-cleaner-stage4 2>/dev/null ||
    git switch --track origin/feature/japan-reset-queue-cleaner-stage4
git pull --ff-only

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py
python3 tools/japan_port/test_guest_quiescence_stage3.py
python3 tools/japan_port/test_queue_cleaner_stage4.py
python3 tools/japan_port/test_jp_file80_data_fixups.py

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

Test at least one known-working gameplay area and scene 129. Trigger F8
once. Confirm F8 does not interrupt gameplay. Exit normally and inspect
`[Goemon JP cleaner]` and `[Goemon JP runtime] Timer worker joined cleanly.`
A full native build and gameplay verification are pending until Ubuntu
results are reported. Do not merge as fully tested on source checks alone.

## Blocking work before a real F8 reset

A later version must establish a **generation-scoped shutdown barrier**
that joins all guest OSThreads, and quiesces the native start thread,
VI/RSP/audio/event, save, timer, graphics and DMA workers before
touching RDRAM or other game state. It must reset running/blocked queues,
external event backlog, overlay/code maps, CPU and OS boot state,
and ensure that the renderer remains alive across the boot.

Only then can the original boot entrypoint be reinvoked without
relaunching the Linux process. Multiple same-PID resets and save
integrity need dedicated regression tests.
