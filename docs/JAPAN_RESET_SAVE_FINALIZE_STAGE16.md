# Japanese native v0.2.23-dev — Stage16 final pending-save write on normal PC exit

## Confirmed Stage15 runtime baseline

On 17 November 2026 the Japanese native game passed the complete
normal-application exit sequence:

```text
[Goemon JP guest exit stage9] joined=1; PC exit only; F8 not armed.
[Goemon JP cleaner] created=5 finished=5 joined=5 active=0 unjoined=0; queue drained, guest shutdown NOT proven.
[Goemon JP event exit] vi_joined=1 gfx_joined=1 sp_joined=1 pending_gfx=0 pending_sp=0; event-only shutdown.
[Goemon JP gfx queue] submitted=225 started=225 completed=225 pending=0 action_queue_approx=1 joined=1; no generation stop or queue reset.
[Goemon JP config fence stage14] drained=1 closed=1; normal PC exit only.
[Goemon JP action exit stage10] skipped=0 screen=1 config=0 unexpected_graphics=0 pending_gfx=0 remaining_approx=0 expected_only=1; PC exit only, no F8 reset.
[Goemon JP save exit] joined=1 worker=0 file_io=0 write_signals=0 flush_ok=0; save-only shutdown, durability unproven.
[Goemon JP exit barrier stage12] guest=1 boot=1 native=1 graphics=1 action=1 save=1 audio_dispatch=1 known_joined=1 timer_epoch=unproven sdl_audio=unproven producer_fences=unproven restart=0; PC exit only, F8 disabled.
[Goemon JP SDL audio exit stage15] permit_drained=1 accepted=702 rejected=0 inflight=0 queued_before=0 queued_after=0 device_closed=1 confirmed=1; PC exit only, no live reset or generation rearm.
```

The above confirms Stage15 callback leases and SDL device close on
**normal process exit**, not live F8 reset. `queued_before=0` means
this specific run did not prove clearing a nonempty SDL audio queue.

## Problem identified in the pinned runtime

The real pinned N64ModernRuntime `librecomp/src/pi.cpp` save worker
loops on `while (!exited)`. Saving is asynchronous: each SRAM save
mutation signals `write_sempahore`, and `saving_thread_func` coalesces
writes into a call to `update_save_file()`. If `exited` changes before
a pending signal is processed, the worker may leave its last write
unfinalized. Stage7 already counts signals and successful calls to
`finalize_output_file_with_backup`, but Stage15's user log has
`write_signals=0 flush_ok=0`, meaning no real save mutation was
exercised during that run.

## Stage16 actual implementation

**Default-off JP-only:** `GOEMON_JP_SAVE_STAGE16=ON` requires Stage15
and all preceding stages. Generated `pi_stage16.cpp` replaces only
`pi_stage7.cpp` in `librecomp`; the runtime submodule remains pinned
and unmodified.

A new `patch_save_finalize_stage16.py` composes the Stage7 source
generator and retains all existing save audit instrumentation.

1. Under the existing `save_buffer_mutex`, increment an atomic
   `jp_save_mutation_epoch` at all **three** save mutation sites:
   `save_write_ptr`, `save_write`, and `save_clear`. These
   writes retain their existing semaphore notifications.
2. When `update_save_file()` writes the save buffer under the same
   mutex, capture that buffer's mutation epoch. Treat a failed
   `ofstream.write` as a save failure.
3. Advance `jp_save_finalized_epoch` **only** after the current
   `finalize_output_file_with_backup` returns success. Backup
   finalization failure never marks the snapshot finalized.
4. At **normal app exit, after `join_saving_thread()` returns**,
   compare the current mutation epoch with its last successfully
   finalized epoch. If any mutation is outstanding, call the same
   `update_save_file()` synchronously once. Capture and report
   an exception as failure rather than unwinding process shutdown.
5. The existing `jp_save_worker_joined_for_future_reset` predicate
   now additionally requires that Stage16 exit finalization succeeded.
   Stage12 `known_joined=1` must be **withheld** on a known
   pending-save finalization failure.

The Stage16 exit log:

```text
[Goemon JP save finalize stage16] mutated=N finalized_epoch=N final_attempt=N finalized=N durable=unproven; PC exit only, F8 disabled.
```

A clean exit with no save mutations may report `mutated=0`,
`finalized_epoch=0`, `final_attempt=0`, `finalized=1`.
This means **no dirty writes remained to finalize**; it is not proof
that an actual save operation succeeded.

To validate a real save path, perform an in-game save on a disposable
save profile before using normal Exit. A save mutation should cause
`mutated>0`; `finalized_epoch==mutated` and `finalized=1` indicate
that the existing backup-file finalization API reported success.
Separately verify save contents persist when the game is relaunched.
Avoid overwriting irreplaceable saves.

### Durability limitations

`finalize_output_file_with_backup` is the existing runtime save
persistence API; its success does **not** establish OS-level
`fsync` of file and parent directory or survival of sudden power loss.
Stage16 deliberately logs `durable=unproven`. It also does not
establish a generation-scoped write-producer fence, support live save
worker rearm, or admit a reboot request. F8 never invokes a save
finalization action.

## Ubuntu regression and build

The existing JP native build cache must retain Stage1–15 opt-ins.

```bash
cd ~/Goemon64Recomp-JP
git fetch origin feature/japan-reset-save-finalize-stage16
git switch feature/japan-reset-save-finalize-stage16 2>/dev/null ||
  git switch --track origin/feature/japan-reset-save-finalize-stage16
git pull --ff-only

python3 tools/japan_port/test_save_finalize_stage16.py
python3 tools/japan_port/test_native_boot_save_audio_stage7.py
python3 tools/japan_port/test_exit_barrier_stage12.py
python3 tools/japan_port/test_sdl_audio_exit_stage15.py

cmake -S . -B build-generated/japan-native-game \
  -DGOEMON_JP_SAVE_STAGE16=ON
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
```

Expect JP `v0.2.23-dev` with `[save-finalize]`. During gameplay,
F8 must remain diagnostic only and show Stage13 `admitted=0`.
The Stage16 line appears **after the save worker join and before**
the existing Stage7 `[Goemon JP save exit]` and Stage12 combined
barrier line. The Stage15 SDL device close remains last.

## Verification scope

The user's Stage15 full Ubuntu normal-exit pass is **confirmed**.
Stage16 has **14 new ROM-free regression checks authored**; inherited
Stage1–15 version assertions have been updated. Native Stage16
CMake compilation, tests against the checked-out pinned runtime and
real-game save durability **have not yet been verified**; draft only.

## Remaining real F8 work

Live generation-stop ownership, producer fences for guest creation,
VI/GFX/SP, timer and save writes, bounded join and abort logic,
reinitializing guest memory, scheduler, overlays, RT64 state and SDL
audio device **within the existing SDL window/process**, plus proof
that the new game entry can be invoked safely. Successful PC exit is
necessary but not sufficient.
