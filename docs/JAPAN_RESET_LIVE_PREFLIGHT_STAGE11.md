# JP v0.2.18-dev — Stage 11: live-generation producer preflight (diagnostic only)

## Stage10 Ubuntu evidence, 17 November 2026

The user successfully ran v0.2.17-dev on Ubuntu. During live play F8
continued reporting five active guest OSThreads and did not reset memory.
After normal PC exit:

```text
[Goemon JP guest exit stage9] joined=1; PC exit only; F8 not armed.
[Goemon JP cleaner] created=5 finished=5 joined=5 active=0 unjoined=0; queue drained, guest shutdown NOT proven.
[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 pending_gfx=0 pending_sp=0; event-only shutdown.
[Goemon JP gfx queue] submitted=320 started=320 completed=320 pending=0 action_queue_approx=1 joined=1; no generation stop or queue reset.
[Goemon JP action exit stage10] skipped=0 screen=1 config=0 unexpected_graphics=0 pending_gfx=0 remaining_approx=0 expected_only=1; PC exit only, no F8 reset.
```

The residual action was a ScreenUpdateAction and the exit-only drain
removed it without dropping a graphics task. This does NOT prove that
the same drain is legal during live gameplay.

## Why no live stop is armed yet

The stage9 guest stop is executed *after* normal PC application exit
and native game-entry thread join. Native event loops still use the
application-level exit state; reusing that state to implement F8 would
conflate stopping a guest generation with quitting the SDL application.

Stage11 provides an independent read-only inventory while gameplay
is actually live. It does not modify exit state or pause workers.

## Implementation

- Opt-in `GOEMON_JP_LIVE_STAGE11=ON`, default OFF. Requires Stage10,
  which already requires Stages1–9.
- Compose the stage10 runtime source generation in a new
  `patch_live_preflight_stage11.py`; pinned submodule untouched.
- On the existing remappable one-shot Reset Game input, print one
  `[Goemon JP live preflight stage11]` line after the previous audits.
- Report VI/GFX/SP active flags; pending GFX/SP tasks; submitted and
  completed graphics counts; approximate action-queue depth; whether
  the configuration action producer is open. Reading config state
  acquires its shared mutex briefly.
- Emit an eight-bit **known blocker** mask: bit0 VI, bit1 GFX, bit2 SP,
  bit3 pending GFX, bit4 pending SP, bit5 submitted!=completed,
  bit6 action queue nonempty, bit7 config publisher open.
- Always print `ready=0` because guest/boot/timer/audio/save/input
  generation fences are not implemented. No bitmap value can arm reset.
- Version `v0.2.18-dev` with exact Git SHA and `[live-preflight]`.
  USA version remains `v0.2.3-dev`.

No guest stop request, producer gate, destructive queue drain, SDL
window teardown, audio cancellation, save file change, ROM alteration,
RDRAM reset or game-entrypoint relaunch is performed by F8.

## Ubuntu build and live test

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-live-preflight-stage11
git switch feature/japan-reset-live-preflight-stage11 2>/dev/null ||
  git switch --track origin/feature/japan-reset-live-preflight-stage11
git pull --ff-only

for test in \
  test_reset_preflight \
  test_timer_runtime_stage1 \
  test_guest_threads_stage2 \
  test_guest_quiescence_stage3 \
  test_queue_cleaner_stage4 \
  test_guest_join_stage5 \
  test_native_events_stage6 \
  test_native_boot_save_audio_stage7 \
  test_graphics_queue_stage8 \
  test_guest_exit_stage9 \
  test_action_drain_stage10 \
  test_live_preflight_stage11 \
  test_persistent_session_logs \
  test_jp_file80_data_fixups \
  test_jp_sasuke_bomb_camera_fix
do
  python3 "tools/japan_port/${test}.py"
done

python3 tools/japan_port/jp_sasuke_bomb_camera_fix.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --source build-generated/japan/RecompiledFuncs/funcs_32.c \
  --output build-generated/japan/RecompiledFuncs/funcs_32.c --in-place

cmake --build build-generated/japan-native-lib --parallel 4
cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_BUILD_JAPAN=ON \
  -DGOEMON_JP_TIMER_STAGE1=ON \
  -DGOEMON_JP_THREAD_STAGE2=ON \
  -DGOEMON_JP_GUEST_STAGE3=ON \
  -DGOEMON_JP_QUEUE_STAGE4=ON \
  -DGOEMON_JP_JOIN_STAGE5=ON \
  -DGOEMON_JP_EVENTS_STAGE6=ON \
  -DGOEMON_JP_BOOT_STAGE7=ON \
  -DGOEMON_JP_GRAPHICS_STAGE8=ON \
  -DGOEMON_JP_EXIT_STAGE9=ON \
  -DGOEMON_JP_ACTION_STAGE10=ON \
  -DGOEMON_JP_LIVE_STAGE11=ON
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
```

Expect `v0.2.18-dev` and `[live-preflight]`. Enter overworld,
press F8 **once**, and verify the new live-preflight line describes
active producers. Continue playing, then close the PC app normally
and verify Stage9/10 still complete and drain cleanly.

## Next barrier (not implemented in Stage11)

A true F8 reset will require an independent generation stop state
distinct from the app-wide `exited` flag, plus a producer fence for
VI/GFX/SP/config, guest creation and blocking receives, scheduler,
timer, audio, save, and input. After producer fencing, join all guest
and native workers, account for every outstanding task, snapshot save
durability and only then reconstruct per-generation runtime state.
Recreating event worker threads, mutexes and message queues must be
proven before a same-process second boot. Leave F8 non-destructive
until that can be demonstrated on Ubuntu.

Validation status: structural tests authored; Ubuntu native compile
and gameplay execution are pending.
