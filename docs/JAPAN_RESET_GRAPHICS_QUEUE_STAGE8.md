# Japanese native v0.2.13-dev — graphics queue settlement preflight (stage 8)

## Why this stage is needed

v0.2.12-dev on Ubuntu demonstrated that F8 reports all current
worker lifecycles, and a normal exit joined the native boot, VI,
graphics, SP, timer and saving workers. However:

- **5 N64 guest OSThreads remained active** (3 blocked on message receive).
- At exit, the graphics thread was joined but the prior counter reported
  **pending_gfx=1**.
- The pinned \`N64ModernRuntime/ultramodern/src/events.cpp\` graphics
  loop checks \`while (!exited)\` and can finish with a previously queued
  \`SpTaskAction\` unprocessed. One pending action is NOT automatically a
  GPU leak and was not proven to be the crash cause.
- No same-process F8 reset is currently available.

This is tracked in [issue #18](https://github.com/Jake-Arnold/Goemon64Recomp/issues/18);
the full reset remains [issue #11](https://github.com/Jake-Arnold/Goemon64Recomp/issues/11).

## Changes

Opt-in \`GOEMON_JP_GRAPHICS_STAGE8=ON\` (depends on boot stage 7, event
stage 6, join stage 5, queue stage 4, guest stage 3, thread stage 2,
timer stage 1).

The generated \`events.cpp\` adds three **atomic cumulative counters**:

- \`submitted\`: graphics RSP tasks counted before publication to the
  concurrent action queue;
- \`started\`: graphics actions taken from the queue and entered into
  the graphics processing branch;
- \`completed\`: graphics actions whose displaylist-completed callback
  has returned, before the existing pending counter is decremented.

The report also reads the concurrent action queue's \`size_approx()\`.
This includes other action variants (screen updates and config actions)
and is approximate. Individual atomic loads are **not a coherent
instantaneous snapshot** while producers and the consumer are active.

During live gameplay F8 only prints:
\`\`\`text
[Goemon JP gfx queue] submitted=N started=N completed=N pending=N action_queue_approx=N joined=0; no generation stop or queue reset.
\`\`\`

The same report prints **after the existing normal-exit joins**, when
joined=1. Because guest threads may still be live, that is not a proof
that nobody could enqueue another action after the snapshot.

An **inactive** guarded helper requires the graphics worker joined,
its activity flag false, no pending graphics RSP tasks, matching
submitted/completed counters, and an approximately empty action queue.
This is **only a necessary test**, not a sufficient full reset barrier.
There is no F8 call to this helper.

There is **NO queue dequeue, task discard, renderer restart, RDRAM
clear, guest stop, save flush, audio pause or process relaunch**.
Original pinned runtime sources and ROMs are unchanged. The USA binary
is unaffected. The v0.2.8 file 80/scene129 fix is inherited.

## Ubuntu test/build

\`\`\`bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-graphics-queue-stage8
git switch feature/japan-reset-graphics-queue-stage8 2>/dev/null ||
  git switch --track origin/feature/japan-reset-graphics-queue-stage8
git pull --ff-only

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py
python3 tools/japan_port/test_guest_quiescence_stage3.py
python3 tools/japan_port/test_queue_cleaner_stage4.py
python3 tools/japan_port/test_guest_join_stage5.py
python3 tools/japan_port/test_native_events_stage6.py
python3 tools/japan_port/test_native_boot_save_audio_stage7.py
python3 tools/japan_port/test_graphics_queue_stage8.py
python3 tools/japan_port/test_jp_file80_data_fixups.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON \
  -DGOEMON_JP_JOIN_STAGE5=ON \
  -DGOEMON_JP_EVENTS_STAGE6=ON \
  -DGOEMON_JP_BOOT_STAGE7=ON \
  -DGOEMON_JP_GRAPHICS_STAGE8=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
\`\`\`

Expected: \`v0.2.13-dev\` with exact Git SHA and
\`[graphics-queue-audit]\` appended to the earlier audit labels.

Open scene 129, play normally, press F8 once, inspect
\`[Goemon JP gfx queue]\` and all prior reports. Exit normally and
confirm the event exit and second graphics queue report, timer and
save worker joins. Preserve game and save data; no reset occurs.

## Route to real F8 reset

1. **Stop producers** and prevent any new guest OSThread, graphics
   or SP task from entering the old generation.
2. **Wake and join** all guest host workers. The current five stay alive
   on normal app exit; an empty cleaner deletion queue is not a barrier.
3. **Settle/discard with proof** all queued host actions, including
   graphics, VI, SP, timer, external messages, audio and save activity.
4. **Reset all generation-scoped state**, not merely RDRAM: scheduler
   ready/blocked lists, VM/overlay pointers, queues, timers and CPU
   context. Keep the PC frontend window alive.
5. **Re-enter the original N64 boot** from the same process; validate
   multiple consecutive resets, scene129 and saves.

A first experiment requires explicit failure/timeout handling. It must
not continue to memory reset if any worker is still live or any stale
pointer remains. No time-to-completion is guaranteed.
