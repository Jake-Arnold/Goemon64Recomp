# JP v0.2.21-dev — Stage14 config producer generation fence

## Source: Ubuntu Stage13 verified

User's live Japanese F8 log (17 November 2026):

```text
[Goemon JP generation stage13] generation=1 request=1 phase=0 admitted=0 backend=0 verified_fences=0x000 required_fences=0x3FF reason=backend-not-installed; no guest stop, no RDRAM reset.
[Goemon JP live preflight stage11] initialized=1 vi=1 gfx=1 sp=1 pending_gfx=0 pending_sp=1 gfx_submitted=109 gfx_completed=109 actions_approx=0 config_open=1 blockers=0x97 ready=0; guest/boot/timer/audio/save/input fences unproven; F8 diagnostic only, no generation stop or RDRAM reset.
```

This passes the **Stage13 one-shot request admission check**. It does not
establish Stage12 normal-exit worker joins, as the output ends while the
game is running.

## Stage14: first enforced native producer fence

Stage10 gated only UI config publishing with a mutex and a permanent
`jp_config_actions_closed_for_pc_exit` bool. Stage14 adds an independently
counted `goemon_jp::reset::PublisherGate` (header:
`src/game/jp_generation_publisher_gate.hpp`) around the *actual*
`ultramodern::trigger_config_action()` enqueue:

- Every accepted config action holds a move-only RAII permit during the
  actual enqueue. The global gate tracks accepted, rejected and
  in-flight permit counts, along with a generation label (currently 1).
- **Normal PC exit only:** after Stage9 guests and Stage6 native event
  workers have joined, Stage10's residual-action cleanup first closes
  admission under the gate mutex and waits up to 500ms for accepted
  permits to return. Only after all permits are released does it take
  the original Stage10 queue mutex, permanently mark config publishing
  closed and classify/drain abandoned actions.
- On timeout, admission **remains closed** and the action cleanup
  returns false without draining the host queue. The Stage12
  `known_joined` conjunction therefore cannot claim a completed
  action gate.
- There is **no reopen or generation-transition API**. Restoring a
  publisher for a new generation must be implemented with proof that
  its prior workers are quiescent and its queue has been rebuilt; do
  not assume that changing a generation number is safe.
- F8 never calls `close_for_pc_exit()` and never requests guest stop,
  RDRAM reset or PC exit. The new F8 snapshot reports the live
  publisher gate's open/inflight/accepted/rejected state.

Stage14 uses an opt-in build-tree `events.cpp` generator that composes
the pinned Stage1–11 instrumentation; the pinned N64ModernRuntime git
submodule is not changed. Stage12 exit and Stage13 admission remain in
place. Normal USA build/version remains unchanged.

## Expected new output

On one F8 press during active gameplay:

```text
[Goemon JP config producer stage14] generation=1 open=1 inflight=N accepted=N rejected=N f8_close=0; no reset or queue drain.
```

Normal clean exit, after all guest and VI/GFX/SP joins:

```text
[Goemon JP config fence stage14] drained=1 closed=1; normal PC exit only.
[Goemon JP action exit stage10] skipped=0 ...
[Goemon JP exit barrier stage12] guest=N boot=N native=N graphics=N action=N save=N audio_dispatch=N known_joined=N ...
```

The failed fence path explicitly prints
`[Goemon JP config fence stage14] drained=0; publisher permit timeout, skip action drain.`
Neither path is an F8 memory-reset backend.

## Local host test evidence

The exact C++ header and standalone host test were compiled locally
with `g++ -std=c++20 -Wall -Wextra -Werror -O2 -pthread` and the
binary completed **five consecutive runs**. Every run printed:

```text
Stage14 host publisher gate: PASS; concurrency=10, attempts=30000, generation=9, open=0, inflight=0
```

Tests include a held permit blocking close, terminal timeout remaining
closed, 10 threads racing with closure, exact accepted/rejected counts
and no outstanding in-flight permit after close. A separate
`-fsanitize=address,undefined` build/run also **passed** with
`ASAN_OPTIONS=detect_leaks=1:halt_on_error=1` and
`UBSAN_OPTIONS=halt_on_error=1`. These are host-only unit tests; they
**do not prove** the generated events.cpp compiles or behaves correctly
during native Japanese gameplay.

11 new ROM-free Python tests were authored to check the generated
source-splice contract, F8 read-only path, close-before-drain ordering,
CMake flag, version and host C++ test. The full Python suite and actual
Ubuntu native compile have **not yet been run** by the assistant.

## Ubuntu commands

Use the same Japanese build directory that previously compiled Stage13;
the CMake cache retains stages 1–13 enabled.

```bash
cd ~/Goemon64Recomp-JP

git fetch origin feature/japan-reset-config-publisher-fence-stage14
git switch feature/japan-reset-config-publisher-fence-stage14 2>/dev/null ||
  git switch --track origin/feature/japan-reset-config-publisher-fence-stage14
git pull --ff-only

python3 tools/japan_port/test_config_publisher_fence_stage14.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_JP_CONFIG_FENCE_STAGE14=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
```

During gameplay, press F8 once. It must print the Stage14 publisher
snapshot with `open=1` and continue normally. On normal application exit,
confirm the new `drained=1 closed=1` line and the Stage12
`known_joined` line. If either is missing, do **not** claim a reset
barrier has been established.

## Reset remains blocked

This is an enforced fence for only **one producer category** (UI
configuration actions). VI, GFX, SP, guest OSThreads, timers, save
durability, SDL output and input generation ownership still require
independent fences/reinitialization. No live worker stop or same-process
F8 re-entry is attempted.
