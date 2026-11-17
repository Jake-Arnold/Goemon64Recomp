# JP v0.2.19-dev — Stage12 post-join cross-subsystem exit audit

## Ubuntu Stage11 evidence, 17 November 2026

User pressed remappable F8 during Japanese native gameplay. The game
continued unchanged and Stage11 emitted:

```text
[Goemon JP live preflight stage11] initialized=1 vi=1 gfx=1 sp=1 pending_gfx=0 pending_sp=1 gfx_submitted=357 gfx_completed=357 actions_approx=0 config_open=1 blockers=0x97 ready=0; guest/boot/timer/audio/save/input fences unproven; F8 diagnostic only, no generation stop or RDRAM reset.
```

`0x97` corresponds to VI, GFX, SP (0x07), one pending SP task
(0x10), and an open config action producer (0x80). Graphics completion
was settled at the observation instant, but guest receives were still
blocked three deep. No live generation-stop, timer epoch reset or
reboot can be inferred. Stage11 preflight passes its intended
diagnostic behaviour, not an operational F8 reset.

## Stage12 scope — normal PC exit ONLY

Stage9 already coordinates guest OSThread cleanup after the native
game entry worker joins on regular app exit. Stage10 then classifies
and drains residual screen/config actions only after VI/GFX/SP joins.
Stage7 saves close later. Stage12 adds a **single post-join snapshot**
after `join_saving_thread()` and before the existing conditional
`munmap`. It consults only previously implemented read-only
predicates:

- Guest join proven by Stage9.
- Native boot worker joined and inactive.
- VI/GFX/SP event workers joined with no pending SP/GFX tasks.
- Graphics submissions and completions equal, action queue empty.
- Stage10 abandoned action audit `expected_only`.
- Save worker joined and no active file I/O.
- No synchronous audio dispatch in flight.

The log reports `known_joined=1` only if all **seven known** conditions
are true. It does NOT mean the game can reset. There is no verified
SDL queued-audio shutdown, generation-relative timer reset, complete
producer fence, durable save transaction protocol, or native-worker
restart proof. The line always prints `restart=0` and explicitly
identifies these unproven components.

```text
[Goemon JP exit barrier stage12] guest=N boot=N native=N graphics=N action=N save=N audio_dispatch=N known_joined=N timer_epoch=unproven sdl_audio=unproven producer_fences=unproven restart=0; PC exit only, F8 disabled.
```

This observer cannot request guest stop, drain queues, unmap RDRAM,
pause audio, write a save or re-enter a native boot routine. It leaves
all existing normal-exit shutdown and cleanup decisions intact.

## Build and validation on Ubuntu

The normal JP native build directory must already contain the
region's generated ROM-derived files and the exact Stage1–11 setup.
The change is scoped to a draft feature branch:

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-exit-barrier-stage12
git switch feature/japan-reset-exit-barrier-stage12 2>/dev/null ||
  git switch --track origin/feature/japan-reset-exit-barrier-stage12
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
  test_exit_barrier_stage12 \
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
  -DGOEMON_JP_LIVE_STAGE11=ON \
  -DGOEMON_JP_BARRIER_STAGE12=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
```

Expect Japanese v0.2.19-dev and `[exit-barrier-audit]` tag.
F8 must still emit the Stage11 snapshot without stopping gameplay.
After **normal application exit**, look for the new Stage12 log line
after save exit and before RDRAM unmap. A pass for known worker
settlement is `known_joined=1`; regardless of that value, no
in-process reset is armed.

## Next implementation

Introduce an app-independent JP generation coordinator and producer
fencing with explicit live-stop request, bounded guest/native joins
and fail-closed refusal to reuse old RDRAM if any worker remains.
Timer/audio/save state must be owned per generation or explicitly
recreated, rather than simply reusing app-wide `exited`.
The Stage12 exit census is supporting evidence only.

Test status: 10 contract tests authored. Linux native build and
real gameplay exit remain untested until user runtime results.
