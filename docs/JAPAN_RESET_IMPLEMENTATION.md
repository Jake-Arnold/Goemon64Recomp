# Japanese native PC port: hardware-style reset implementation

## Current state

**v0.2.4-dev (experimental, not merged into stable):** adds a remappable
**Reset Game** action under **Controls**, default keyboard **F8**, with
two available bindings on each device and no default controller binding.
It recognises one key/button-down transition while the game is active
and not while the settings/binding menu captures input. Currently the
action only logs that a request was received; **it does not reset**.
This intentionally avoids the broken process-restart experiment.

**v0.2.3-dev:** verified build identity, now merged into stable.
**v0.2.2-dev:** tested GNOME dock integration, previously merged.
**v0.2.1-dev:** failed process-restart experiment in draft PR #2;
**never merge**. That version called `ultramodern::quit()` and
`execv("/proc/self/exe")`. A real Ubuntu test reproduced a SIGSEGV
immediately after the relaunched process initialised its recomp heap.

## Required semantics

The desired operation is like pressing N64 RESET, not quitting the PC
application and re-running the binary:

1. **Keep the same SDL window, RT64 renderer and process ID.**
2. Stop all currently executing N64 guest threads and block new guest
   work while the reset transaction is in progress.
3. Quiesce the RSP task runner, PI/SI, VI and audio output.
4. Drain/reset game-era external messages and event queues.
5. Stop and **join** the timer thread, clear its timers and osGetTime
   epoch, then restart it for the new guest generation.
6. Join guest host threads and clear their scheduler queues and
   `UltraThreadContext` references. Never free RDRAM while a host thread
   retains a pointer to it.
7. Reset the game-era overlay map, ROM mapping state, RDRAM/heap and
   recompiled CPU context. Reinstall entry overlay registrations and
   boot parameters.
8. Restart the Japanese game's entrypoint with an N64 reset state.
9. Preserve persistent EEPROM/Controller Pak saves, existing control
   bindings, Linux app launcher and loaded ROM selection.
10. Prevent key-repeat and double-triggering. Do not accept resets
    from the Controls binding-scanning menu.

**No normal game-code function call is a substitute for steps 2–8.**

## Pinned runtime audit

Pinned `lib/N64ModernRuntime` commit:
`fc4592a31414daf0040c19907e0b1976b2e48a67`.

### librecomp/src/recomp.cpp

- `recomp::start_game` only transitions `game_status` from `None` to
  `Running`; there is no reset status or reset entrypoint.
- `ultramodern::quit` sets the process-wide `exited` flag and
  clears `current_game`; this is **not a reset API**.
- `recomp::start` allocates one RDRAM mapping and starts one N64 game
  starter thread, then pumps graphics until `exited`. Shutdown joins
  the N64 starter, event, cleaner and saving threads and frees RDRAM.
- `wait_for_game_started` calls `init`, registers the overlay map,
  loads the initial ROM section, initialises heap and save processing,
  and runs the guest entrypoint exactly once.
- `ultramodern::is_game_started()` reports whether `game_status`
  differs from `None`; it does not signal that runtime re-entry is safe.

### ultramodern/src/threads.cpp and scheduling.cpp

- `osCreateThread` starts an independent host thread, with an
  `UltraThreadContext` stored inside guest RDRAM.
- A guest OSThread commonly blocks on a semaphore while the native
  scheduler runs another guest thread.
- The global cleaner thread handles completed guest contexts, but
  no reset-aware barrier synchronises **all** outstanding guest threads.
- Never clear RDRAM while these threads can wake or dereference
  `OSThread::context`.

### ultramodern/src/timer.cpp

- `init_timers` launches a **detached** timer host thread which loops
  indefinitely over guest timer structures in RDRAM.
- There is no shutdown/join path for that timer thread.
- A guest reset that clears RAM while it runs would be a race and likely
  produce a crash or corrupt guest messages.

### ultramodern/src/events.cpp

- VI, graphics and RSP task threads start in `init_events`.
- The graphics thread creates the renderer context and owns its shutdown.
- There is no `reset_game_events` path that stops all guest DMA and VI
  submissions while preserving the native SDL/RT64 frontend.
- Actions and message queues may still contain guest addresses after
  any guest reinitialisation.

### librecomp/src/overlays.cpp

- `init_overlays` clears `func_map`, but allocates
  `section_addresses` anew and does not free the previous allocation.
- `loaded_sections`, ROM-to-section maps and game-generation state
  must be reset or reconstructed before a second boot.

## Implementation sequence

The following steps should be independent, testable changes. Do not
enable reset until *all* invariants are met.

1. Add a **guest-generation/ResetRequested/Quiescing/Reinitialising**
   state machine to a controlled fork or patch of N64ModernRuntime,
   keeping changes opt-in to JP.
2. Replace the detached timer with a lifetime-managed, stop/joinable
   timer thread; add tests proving timer queues are never dereferenced
   after RDRAM is cleared.
3. Add a cooperative per-guest-thread shutdown barrier. Count and join
   all guest threads before resetting memory. Time out and **abort
   reset safely without clearing RAM** if any thread fails to quiesce.
4. Separate the persistent graphics window/renderer from guest VI/RSP
   tasks; drain task submissions and rebuild guest queues on reset.
5. Add reset hooks for overlays, CPU context, memory, heap, save
   subsystem and game-entrypoint boot parameters.
6. Wire the existing `RESET_GAME` input action into the tested
   runtime reset API and display user confirmation as appropriate.
7. Test 3+ consecutive resets and save persistence on Ubuntu, with
   exact `--version` and commit fingerprint captured.

## Preflight test (v0.2.4-dev)

Run from the JP repository:

```bash
cmake --build build-generated/japan-native-game \
    --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
./build-generated/japan-native-game/Goemon64RecompiledJP
```

During live gameplay, F8 should print:

```text
[Goemon JP reset] Request received; native reset backend not installed. Game continues without modification.
```

The window, game and process must stay running; a true reset
is **not** expected in this experimental build. Test remapping in
**Controls → Reset Game**, and verify the remapped button logs exactly
one request per press. The branch must remain draft unless this safety
preflight passes.

v0.2.5-dev adds the opt-in, joinable timer lifecycle prerequisite; see
`docs/JAPAN_RESET_TIMER_STAGE1.md`. It still does not reset the game.
v0.2.6-dev adds an opt-in guest OSThread lifecycle audit. See
`docs/JAPAN_RESET_GUEST_THREADS_STAGE2.md`. It counts created, finished
and joined host workers on each F8 request without stopping them.
This does not enable reset. v0.2.7-dev adds an opt-in guest-context
registry, stop-request scaffolding and cooperative scheduler checkpoints,
without arming a shutdown in gameplay. See `docs/JAPAN_RESET_GUEST_STAGE3.md`.
It is not a complete quiescence/join barrier: native main-thread, RSP/VI,
message queues and the thread cleaner still require coordination. The
v0.2.8-dev file 80 compatibility fix is verified by the user to load scene 129.
v0.2.9-dev adds opt-in N64 message-queue wait instrumentation, bounded
external-message checkpoints, and a normal-exit guest-cleaner drain report.
See `docs/JAPAN_RESET_QUEUE_STAGE4.md`. F8 remains diagnostic-only.
v0.2.10-dev adds a guarded, inactive guest-host-thread join predicate,
a future-stop scheduling gate, join notifications, and F8-only readiness
diagnostics. See `docs/JAPAN_RESET_GUEST_JOIN_STAGE5.md`. The predicate
cannot be invoked by gameplay; no guest termination, full host-worker
quiescence, or RDRAM reinitialisation is implemented. v0.2.11-dev adds a read-only VI/graphics/SP native event-worker census,
pending RSP task counters, and a normal-exit report of the original event
join order. See `docs/JAPAN_RESET_NATIVE_EVENTS_STAGE6.md`. This only
accounts for three native event workers; it does not stop guest threads,
reinitialise RDRAM, or perform a same-PID reset.
v0.2.12-dev adds native Game Start Thread, asynchronous save worker,
synchronous runtime audio-dispatch and SDL queued-audio diagnostics. It
preserves file writes, playback, the existing event/timer shutdown order,
and the pinned runtime submodule. See
`docs/JAPAN_RESET_BOOT_SAVE_AUDIO_STAGE7.md`. All stage-7 shutdown
predicates are inactive; this is an ownership census, NOT a reset.
v0.2.13-dev adds read-only graphics-action settlement counters
(submitted/started/completed) and a best-effort action-queue depth
snapshot. It does not drop, replay or clear queued work. See
`docs/JAPAN_RESET_GRAPHICS_QUEUE_STAGE8.md`. The Ubuntu
`pending_gfx=1` normal-exit finding remains a blocker for any real
same-process reset. A future generation-scoped stop must quiesce all
guest and native workers and settle every queue before reinitialising
boot/RDRAM while preserving the PC process and window.

v0.2.14-dev adds Japanese Linux **automatic persistent session logging**,
including diagnostic stdout/stderr from desktop launches, per-launch
log files, a stable `latest.log` shortcut and fatal-signal breadcrumbs.
See `docs/JAPAN_PERSISTENT_SESSION_LOGS.md`. Logging is independent of
F8 reset and does not change shutdown or N64 memory semantics.

v0.2.15-dev resolves the separately verified Yamato scene307 Sasuke-bomb
camera pointer crash: the user confirmed the bomb now explodes. The change
is a strict ROM-gated Japanese generated-C fix and does not change reset
semantics. See `docs/JAPAN_SASUKE_BOMB_CAMERA_CRASH.md`.

v0.2.16-dev introduces opt-in **guest exit drain stage9**. On *normal PC
application exit only*, after the native game-start thread joins, stage9
requests cooperative guest shutdown and waits for all guest host workers
to join. If this bounded proof fails, it retains RDRAM mapping until the
OS exits rather than unmapping while guests remain live. F8 still prints
read-only diagnostics and cannot stop the game. See
`docs/JAPAN_RESET_GUEST_EXIT_STAGE9.md`. This is one prerequisite for a
future generation stop/restart coordinator, not a complete soft reset.
