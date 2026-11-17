# Japanese native F6 pause/resume — experimental

## Scope and controls

This branch adds an **in-process F6 pause toggle** to the Japanese
native recompilation. This is **not F8 reset** and **not a save state**:
the guest's current RDRAM and OSThread execution remain allocated
and the same SDL/RT64 window and PID remain alive.

**F6:** pause; press F6 again to resume. The SDL window title adds
`[PAUSED — F6]`, and the existing SDL audio device is paused without
clearing its queued samples. The window remains responsive to SDL
events. **F8 during a pause** explicitly releases the paused worker
gates and audio before invoking the previously Ubuntu-verified
integrated reset. Normal PC quit likewise releases worker gates first.

The feature flag is default OFF:

```text
GOEMON_JP_NATIVE_F6_PAUSE=ON
```

It requires `GOEMON_JP_INTEGRATED_F8_RESET_EXPERIMENTAL=ON`
and the existing JP Stage1–18 prerequisites. USA does not install
the F6 handler; ROMs and the pinned N64ModernRuntime stay unchanged.

## What is frozen

- N64 counter and guest time share a synchronized paused clock. While
  paused, both return their saved logical timestamps; on resume,
  the timer origin shifts to remove the time spent paused. There
  should be **no VI/timer catch-up burst**.
- The native VI worker pauses before a new frame and after its
  host sleep. This prevents VI/AI notifications and screen updates
  while paused.
- Graphics action and RSP task dispatchers park at their safe
  boundaries, preserving the last completed image.
- The timer worker checks pause state before dispatching and
  revalidates the N64 timestamp after resume to avoid prematurely
  firing a timer whose host wall-clock timeout occurred during pause.
- Guest OSThread scheduler wakeups and external-message delivery
  park at existing shutdown-safe checkpoints; pending messages
  remain queued rather than being dropped.
- The SDL queued audio device is paused, then resumed.

**Limitation:** this is a *cooperative* host-runtime pause. It does
not forcibly suspend arbitrary native CPU execution or inspect/capture
host C++ stacks. A CPU-bound recompiled guest function that never
calls a host scheduling/timer/message API is not preempted in this
first implementation. Do not describe the current mechanism as
a quiescent arbitrary-instruction snapshot barrier suitable for
full save states. Implementing that requires explicit execution
checkpoints and verified barrier acknowledgements for **all**
guest and native workers.

## Ubuntu build and test

Use a disposable save profile while testing this stacked
experimental branch:

```bash
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-native-f6-pause-resume
git switch feature/japan-native-f6-pause-resume 2>/dev/null ||
  git switch --track origin/feature/japan-native-f6-pause-resume
git pull --ff-only

python3 tools/japan_port/test_integrated_reset_experiment.py -v
python3 tools/japan_port/test_native_pause_resume.py -v
cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_JP_INTEGRATED_F8_RESET_EXPERIMENTAL=ON \
  -DGOEMON_JP_NATIVE_F6_PAUSE=ON &&
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4 &&
~/Desktop/rundecomp.sh
```

Log lines on toggles:

```text
[Goemon JP pause] state=PAUSED generation=1 ticks=N guest_time=N pid=unchanged window=preserved; F6 toggles.
[Goemon JP pause] state=RUNNING generation=1 ticks=N guest_time=N pid=unchanged window=preserved; F6 toggles.
```

### Live acceptance

In active Japanese gameplay, trigger F6, confirm gameplay animation,
position/health/timers and music freeze while the SDL window remains
responsive; leave it paused for 10–30 seconds and confirm that F6
resumes normal graphics, controls, audio and game timing without
accumulated rapid-frame catch-up. Repeat at least ten cycles.

Also test normal window close while paused, plus **F8 while paused**
followed by the returning title and another F6 pause/resume in
generation 2 (then again in generation 3 if stable). The toolkit
should still see current RAM, without reconnecting.

The native source compiler/host tests confirm only checkpoint
plumbing and clock arithmetic; Ubuntu gameplay testing is required
to mark the feature operational. Save-state capture/restore is
outside this branch.

## Rollback

```bash
cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_JP_NATIVE_F6_PAUSE=OFF
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
```
