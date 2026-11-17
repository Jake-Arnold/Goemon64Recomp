# JP v0.2.17-dev — Stage 10: abandoned action queue cleanup on PC exit

## Evidence prompting this stage

Ubuntu v0.2.16-dev (stage9) established successful bounded guest shutdown:
`created=5 finished=5 joined=5 active=0 unjoined=0`. Native VI,
graphics, SP and timer workers also joined. A read-only F8 press still
reported five active guest threads, as designed.

After normal shutdown the graphics action report showed:

```text
[Goemon JP gfx queue] submitted=235 started=235 completed=235 pending=0 action_queue_approx=1 joined=1; no generation stop or queue reset.
```

This is **not a pending graphics task**. The pinned events.cpp action
queue is a variant of graphics work, screen updates and config updates.
The VI producer can publish its last ScreenUpdateAction after the
graphics consumer observes `exited` and stops. The precise kind of
the leftover action was not proven by stage9's approximate depth.

## Implementation — normal PC process exit only

Opt-in flag `GOEMON_JP_ACTION_STAGE10=ON` (default OFF) requires stage9
and all prior JP reset prerequisites. Generated build-tree copies only;
pinned N64ModernRuntime, USA game and Goemon Toolkit are unchanged.

After the boot thread joins and stage9's **complete guest thread-join
predicate** succeeds, and after stage6's native VI, GFX and SP threads
all join, stage10:

1. Closes the frontend config action publication path under a mutex
   shared with the final drain, avoiding late config actions.
2. Reads and removes abandoned action records from the host queue,
   categorising them as `ScreenUpdateAction`, `UpdateConfigAction` or
   unexpected `SpTaskAction`.
3. Reports counts, existing pending graphics task counter and
   approximate queue depth after the drain.
4. Reports `expected_only=1` only if no graphics task was discarded,
   none was pending, queue depth is zero and cumulative submitted and
   completed graphics counts match.

If the guest join proof fails, or any native VI/GFX/SP worker did not
join, stage10 **skips the queue drain**. No stale RDRAM references are
purposely dereferenced or submitted to the renderer during cleanup.

Expected when the pending entry was a screen update:

```text
[Goemon JP action exit stage10] skipped=0 screen=1 config=0 unexpected_graphics=0 pending_gfx=0 remaining_approx=0 expected_only=1; PC exit only, no F8 reset.
```

The actual counts may differ; screen/config are unconfirmed hypotheses.
F8 still performs **read-only diagnostics** and never calls this drain.
Normal-exit cleanup is NOT a reusable same-process reset barrier.

## Ubuntu build and gameplay validation

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-action-drain-stage10
git switch feature/japan-reset-action-drain-stage10 2>/dev/null || \
  git switch --track origin/feature/japan-reset-action-drain-stage10
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
  test_persistent_session_logs \
  test_jp_file80_data_fixups \
  test_jp_sasuke_bomb_camera_fix
do
  python3 "tools/japan_port/$test.py"
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
  -DGOEMON_JP_ACTION_STAGE10=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
```

Expected: `v0.2.17-dev`, Git SHA and `[action-exit-drain]`.
Play normally, test Sasuke's bomb and scene129, press F8 (diagnostics
only), close the application and inspect the persistent session log.
Confirm stage9 guest join and new stage10 classification/queue drain.

## Still blocking real F8 reload

At PC exit, discarding stale screen/config actions is safe only because
gameplay and native event workers have already joined. A live reset
needs a generation stop that prevents **every producer** from publishing
after the barrier, plus guest, VI/RSP/graphics, audio, timer, save and
input quiescence. It must also reconstruct scheduler and message queues,
runtime/global flags, RAM and overlays, and start a new JP boot
entrypoint while retaining the same SDL window and Linux process.

Stage10 has source-contract tests but is not native-build or
gameplay verified until Ubuntu results arrive.
