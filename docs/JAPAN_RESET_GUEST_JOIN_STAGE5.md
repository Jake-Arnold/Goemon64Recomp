# Japanese native port — v0.2.10-dev guest join readiness (stage 5)

## Proven baseline

- v0.2.8-dev fixes file-80 data pointers and the user confirms scene 129 loads.
- v0.2.9-dev passes native Ubuntu gameplay/F8/exit logging:
  \`created=5 finished=0 joined=0 active=5\`,
  \`blocked_recv=3\`, \`blocked_send=0\`, timer joined.
  Normal app exit showed an empty cleaner queue but **none of the five
  guest host threads had finished**. Empty cleanup queues are not a reset
  safety signal.

## Stage 5 scope

This version does **not** perform a live N64 reset.

It introduces the first explicit **guest-host-thread join predicate**,
with a bounded wait. The predicate is intentionally **not invoked** from
any live gameplay/UI code. It returns true only after:

1. Guest stop is explicitly requested by a future orchestrator.
2. There are no in-flight host thread creations.
3. The guest thread-context registry is empty.
4. All created guest host threads have been joined (created == joined).

It refuses calls from a guest OSThread (a thread must never wait for
itself). The guest context registry is updated only after the existing
cleaner joins a completed worker. A condition variable notifies a future
waiting orchestrator after both creation paths and completed-worker
joining. These are *preconditions*, **not a proven complete
application reset barrier**.

A generated \`scheduling.cpp\` gates the scheduling/priority paths once
a future guest-stop request is active. A generated \`threads.cpp\` also
gates \`osStartThread\`. The original pinned N64ModernRuntime submodule
is never written to.

All three guest runtime source files are produced under
\`build-generated/japan-native-game/jp_reset_timer_runtime/\` from
their pinned submodule inputs.

### Safety boundary

Neither F8 nor any production call path in this version invokes the
stop request, the guarded join wait, RDRAM clear, a game entrypoint
restart, or \`execv\`. The F8 key only prints a **read-only diagnostic**
of the join barrier state.

The guest registry still **does not track**:
- the initial native boot/start thread;
- VI, RSP, RT64 graphics and audio;
- timer, saving and game/event workers;
- pending DMA, external message, or overlay state.

Even if the guest predicate were true, resetting RDRAM would still be
unsafe until all such workers are proven quiescent and statics/queues
are reset. Active guest code that never reaches a checkpoint may also
block termination indefinitely.

## Ubuntu test commands

\`\`\`bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP

git fetch origin feature/japan-reset-guest-join-barrier-stage5
git switch feature/japan-reset-guest-join-barrier-stage5 2>/dev/null ||
  git switch --track origin/feature/japan-reset-guest-join-barrier-stage5
git pull --ff-only

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py
python3 tools/japan_port/test_guest_quiescence_stage3.py
python3 tools/japan_port/test_queue_cleaner_stage4.py
python3 tools/japan_port/test_guest_join_stage5.py
python3 tools/japan_port/test_jp_file80_data_fixups.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON \
  -DGOEMON_JP_JOIN_STAGE5=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
SH
\`\`\`

Expected version and enabled stages:
\`v0.2.10-dev (<Git SHA>) [timer-stage1] [threads-audit]
[guest-prep] [queue-audit] [join-prep]\`.

Then run:
\`\`\`bash
cd ~/Goemon64Recomp-JP
./build-generated/japan-native-game/Goemon64RecompiledJP
\`\`\`

Test normal gameplay and entry to scene 129, press F8 once, then exit.
F8 should print the previously validated audit lines **plus**:

\`\`\`text
[Goemon JP join barrier] tracked=N spawning=N finished=N joined=N stop=not-armed; guest-only barrier not armed, RDRAM reset disabled.
\`\`\`

On normal exit, expect both the cleaner and timer logs. F8 must **not**
actually terminate the N64 guest, return to title or relaunch the process.

## Acceptance

- All seven Python suites pass without changing the pinned submodule.
- JP executable compiles and displays exact v0.2.10 commit.
- Scene 129 still works; F8 remains one-shot and diagnostic only.
- No hang or crash on application exit.
- Original file 56 route and saved data remain intact.

These tests validate diagnostics and regression compatibility only; they
cannot exercise the inactive join predicate's true path. This PR should
remain draft until native Ubuntu tests complete.

**Next stage**: coordinate native boot, timer, event, RSP, rendering, audio
and save shutdown; ensure guest termination/joins complete, then
reinitialize scheduler and global guest state in a strictly sequenced
same-PID reset transaction.
