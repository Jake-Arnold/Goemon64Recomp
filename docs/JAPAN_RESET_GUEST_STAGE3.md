# Japanese native recomp v0.2.7-dev: guest shutdown preparation

## Verified foundation

- v0.2.5-dev: joinable timer worker; Ubuntu normal exit prints
  `[Goemon JP runtime] Timer worker joined cleanly.`
- v0.2.6-dev: five observed guest OSThread host workers were active
  during gameplay, with zero completed or joined; F8 is safe and logs
  audit data. A subsequent normal exit also joined the timer.

## Stage 3 implementation

Version `v0.2.7-dev` adds opt-in
`GOEMON_JP_GUEST_STAGE3=ON` guest-thread shutdown preparation.
Both previous stages must be enabled.

The private generated `threads.cpp` now contains:

1. A mutex-protected registry of every guest `UltraThreadContext*`,
   registered before launching its host thread and erased only after
   the cleaner successfully joins it.
2. An atomic in-flight-creation count, so a future shutdown coordinator
   can identify host threads still being created.
3. A stop-request primitive that sets the atomic stop state, then wakes
   registered guest host-thread semaphores.
4. Cooperative cancellation checks after a scheduler semaphore wake
   and at two scheduling-yield helpers. Once stop is requested, a
   waking guest skips its MIPS entrypoint and its successor scheduling.
5. A **read-only readiness report** on F8.

**The stop-request primitive is NOT called in this build.**
The live F8 handler does not invoke it; it only prints diagnostics.
This is deliberate: guest workers blocked outside scheduler semaphores
and the native game-start thread are not fully handled, nor are
VI/RSP/audio, the thread cleaner, queued messages and overlay state.
A genuine reset is still unsafe and unavailable.

No code clears RDRAM or invokes the JP game entrypoint again.
The original N64ModernRuntime submodule is unchanged.

## Ubuntu testing

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP

git fetch origin feature/japan-reset-guest-quiescence-stage3
git switch feature/japan-reset-guest-quiescence-stage3 2>/dev/null ||
  git switch --track origin/feature/japan-reset-guest-quiescence-stage3
git pull --ff-only

python3 tools/japan_port/test_reset_preflight.py
python3 tools/japan_port/test_timer_runtime_stage1.py
python3 tools/japan_port/test_guest_threads_stage2.py
python3 tools/japan_port/test_guest_quiescence_stage3.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
SH
```

Expected version: `v0.2.7-dev (<commit>) [timer-stage1] [threads-audit] [guest-prep]`.

After a successful build, run the game normally.
Press F8 during gameplay. Alongside the existing preflight and
thread-count logs, expect an additional diagnostic:

```text
[Goemon JP guest stop] tracked=N spawning=N stop=not-armed; guest stop and memory reset disabled.
```

The N values depend on the running game and should be treated only as
diagnostic snapshots. F8 must **not** actually stop guest threads or
restart the game. Test a normal area transition and exit the PC app.
The timer worker should still join cleanly and the terminal should
return to a prompt.

**Do not run the old executable after a failed compilation.** The
suggested script uses `bash -e` so version output only runs after
successful CMake compilation/linking.

## Remaining prerequisites before F8 can perform N64 reset

The runtime still needs:

- A reset coordinator that exclusively owns guest lifecycle transitions.
- Cancellation checkpoints for threads blocked in N64 message queues
  and for guest code that does not yield through instrumented scheduler
  helpers.
- A guaranteed finish/join protocol for the existing thread cleaner;
  the current cleaner exits on application shutdown without proving
  that every guest host worker has joined.
- Quiescence of external VI, RSP, event, DMA, save and audio workers.
- Reinitialisation of guest RDRAM, scheduler queues, overlay maps, CPU
  state and boot sequence without restarting SDL/RT64.
- Multiple-reset regression testing with the same PID and intact saves.

The **next planned development version is v0.2.8-dev**. No version or
build label indicates that reset is working until those conditions
are satisfied and native Ubuntu gameplay tests succeed.
