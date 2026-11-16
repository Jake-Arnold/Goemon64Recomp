# Japanese v0.2.15-dev — Yamato Sasuke bomb SIGSEGV fix

## Verified crash

In scene **307 decimal (0x133)** in Yamato, Sasuke's thrown bomb
explosion causes an Ubuntu SIGSEGV. GDB log
`goemon-yamato-sasuke-bomb-gdb.log` identifies:

```text
#0 func_8000FBDC_107DC at funcs_6.c:1390
   ctx->f6.u32l = MEM_W(ctx->r5, 0X0);
#1 func_8000F4A8_100A8 at funcs_5.c:5414
#2 func_8000F1E0_FDE0 at funcs_5.c:4841
#3 func_801F0FB0_5ACF80 at funcs_32.c:5170
#4 func_801F0F14_5ACEE4 at funcs_32.c:4534
```

Host registers include `rcx=0x202119e0`, `rax=0x7ffec9800000`
(RDRAM base); the invalid guest pointer is consistent with the
faulting load, though the raw `ctx->r5` member is not printed directly.

The USA `patches/sasuke_bomb_fix.s` already replaces the equivalent
indirect camera-argument load with the direct USA camera pointer
`0x8020CBF0`. The Japanese version has a different, independently
confirmed camera object: **`0x802119E0`**.

The exact verified 32 MiB Japanese decompressed ROM has SHA-1
`6f8745fecc3a5e7d4918c7a73353eb0726116ded`.
Its bomb function `func_801F0FB0_5ACF80`, ROM `0x5ACF80`,
calls `func_8000F1E0_FDE0` at ROM `0x5AD280` with delay-slot
`lw a1, 0x2C(t7)` at `0x5AD284`. ROM bytes:
`0C003C78 8DE5002C`.

Independent original JP uses of `D_802119E0_5CD9B0` at
`0x5ADE24` and `0x5D17B4` contain
`3C058021 24A519E0`. The first 56 bytes of the original JP and
USA Sasuke bomb functions are also identical.

## Fix scope

`tools/japan_port/jp_sasuke_bomb_camera_fix.py` performs a
**ROM-SHA/byte/source-anchor-gated transform** of only the private
`build-generated/japan/RecompiledFuncs/funcs_32.c`.
It keeps the original MIPS delay-slot load but overrides the
argument immediately before the uniquely verified camera callee:

```c
// jp_sasuke_bomb_camera_fix: JP direct camera object; USA equivalent D_8020CBF0.
ctx->r5 = (gpr)(int64_t)(int32_t)0x802119E0u;
func_8000F1E0_FDE0(rdram, ctx);
```

No ROM bytes, USA path, runtime source, graphics driver or toolkit
code is changed. The generator is idempotent and rejects altered or
ambiguous source layouts rather than guessing. Fresh
`prepare_japan_recomp.py --prepare-native-hooks` stages it
atomically alongside the existing verified scene129/file80 fix.

## Native Ubuntu build sequence

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin fix/japan-sasuke-bomb-camera
git switch fix/japan-sasuke-bomb-camera 2>/dev/null ||
  git switch --track origin/fix/japan-sasuke-bomb-camera
git pull --ff-only

python3 tools/japan_port/test_jp_sasuke_bomb_camera_fix.py
python3 tools/japan_port/test_jp_file80_data_fixups.py
python3 tools/japan_port/test_persistent_session_logs.py

for test in \
  test_reset_preflight \
  test_timer_runtime_stage1 \
  test_guest_threads_stage2 \
  test_guest_quiescence_stage3 \
  test_queue_cleaner_stage4 \
  test_guest_join_stage5 \
  test_native_events_stage6 \
  test_native_boot_save_audio_stage7 \
  test_graphics_queue_stage8
do
  python3 "tools/japan_port/$test.py"
done

python3 tools/japan_port/jp_sasuke_bomb_camera_fix.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --source build-generated/japan/RecompiledFuncs/funcs_32.c \
  --output build-generated/japan/RecompiledFuncs/funcs_32.c \
  --in-place

# Rebuild JP private archive BEFORE the native executable.
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
  -DGOEMON_JP_GRAPHICS_STAGE8=ON

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4
./build-generated/japan-native-game/Goemon64RecompiledJP --version
~/Desktop/rundecomp.sh
SH
```

Expect **v0.2.15-dev** with exact Git build commit and the existing
graphics, save, guest and F8 diagnostic build labels.

## Acceptance

After build, verify at least three Sasuke bomb explosions in Yamato
scene 307 (0x133), another scene with Sasuke bombs, scene 129
file80 loading, normal gameplay, save file persistence, launcher
log output and clean exit. F8 **must remain diagnostic-only**.

The GDB traceback proves the implicated camera-argument path;
the corrected build and actual gameplay have **not** been tested yet.
The PR remains draft pending Ubuntu verification.
