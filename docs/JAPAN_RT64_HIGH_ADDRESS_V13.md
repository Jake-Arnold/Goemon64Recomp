# Japanese robot source address investigation — v13

**Status:** RESEARCH_ONLY. Source-only, read-only diagnostic for a private Japan native RT64 checkout. No ROM bytes, game assets, output textures, shader logic, guest addresses or TMEM loads are changed.

## Why v13 exists

The user's real v12 trace identifies two `LoadOperation::Type::Block` operations that empty all 4,096 RDP TMEM bytes just before the known robot texture hash `0x8042C12B60EC2B4E` is uploaded:

| source_start | before → after whole TMEM nonzero | another previously sampled source | exact difference |
| --- | ---: | --- | --- |
| `0x0078B6E0` | 3812 → 0 | `0x003C76E0` | `0x003C4000` |
| `0x007953D0` | 4096 → 0 | `0x003D13D0` | `0x003C4000` |

v12's `RDRAM_nz64=UNREAD_OUT_OF_RANGE` is only a 4 MiB probe **sampling restriction**. The pinned `klorfmorf/N64ModernRuntime@fc4592a` explicitly reports `8 * 1024 * 1024` in both `osGetMemSize_recomp` and initialization of `osMemSize`. Both high source addresses are **inside 8 MiB** and must not be described as out of N64 RAM. Pinned `klorfmorf/rt64@abb3d7ad` uses direct RDRAM indexed reads in `RDP::loadBlockOperation` / `loadToTMEMCommon`, without a 4 MiB wrap in that path.

v13 expands **read-only first-64-byte samples** to the 8 MiB limit and adds a second 64-byte count from `source - 0x003C4000` ONLY for those two observed exact high source addresses. It reports `candidate_minus_3c4000_nz64`, which is not an automatic remapping or a proposed rendering fix. The uniform additive difference suggests, but does not prove, a duplicated base/address relocation. No game memory or source bytes are logged.

## Prerequisites and install

Requires exact private, instrumented v12 State source and its `.pre-jp-tmem-replay-v12` backup, v11 renderer, v10 texture cache, v8 interpreter and original JP ROM SHA1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`. The installer verifies the source chain byte-for-byte and refuses any mismatch or reinstallation. Does not import proprietary game source or binaries into version control.

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
for name in jp_rt64_robot_probe jp_rt64_triangle_gate_probe jp_rt64_face_index_probe jp_rt64_drawcall_account_probe jp_rt64_raster_handoff_probe jp_rt64_target_state_probe jp_rt64_texture_origin_probe jp_rt64_robot_texture_link_v11 jp_rt64_tmem_replay_v12 jp_rt64_tmem_high_address_v13 analyze_jp_rt64_high_address_v13; do
  git show "FETCH_HEAD:tools/japan_port/${name}.py" > "/tmp/${name}.py"
done
python3 /tmp/jp_rt64_tmem_high_address_v13.py \
  --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 --dry-run
```

**Only after `v13: validated only`:**

```bash
python3 /tmp/jp_rt64_tmem_high_address_v13.py \
  --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 \
  --confirm-modify-private-rt64
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 \
  ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee ~/goemon-jp-rt64-high-v13.log
python3 /tmp/analyze_jp_rt64_high_address_v13.py ~/goemon-jp-rt64-high-v13.log
```

Reach the affected pink robot during capture. The existing v12 logger still records up to 16 qualifying target hashes (32 recent loads each); v13 does not raise trace limits or increase the sampled byte count. 

## Interpret the new observations

- `high_RDRAM_nz64=0/64` and `minus_0x003C4000_nz64>0/64`: 64 high source bytes are zero; corresponding lower address has data. Strong evidence for wrong source address/double base; still confirm where the image address was constructed.
- Both first64 nonzero: the cause may be the load's broader byte range/parameters, address-swizzle, late overwrites or different data outside those samples.
- Both first64 zero: cannot distinguish incorrect addressing from an uninitialized source without deeper source-provenance evidence.
- `4294967295` means **not sampled**, not zero. The generated analyzer prints `UNREAD`.

**No host GPU execution claim:** these are guest memory and CPU RDP replay observations. A 64-byte sample does not establish entire 4-KiB texture contents, and a valid source-address offset pattern does not establish the particular recompiled instruction responsible.

## Rollback

Restore the exact v12 State file backup and rebuild:

```bash
cp lib/rt64/src/hle/rt64_state.cpp.pre-jp-tmem-high-address-v13 \
   lib/rt64/src/hle/rt64_state.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

Before install, `--dry-run` makes no changes. A failed source verification also makes no changes. v13 is a **research diagnostic** and must not merge into production game code without native verification and a confirmed fix.

## Local validation

- 10 new unittest cases: 6 transform/guard tests, 3 analyzer tests, 1 compiled-and-executed C++ hook test, **PASS**.
- Python `py_compile` of both tools, **PASS**.
- The actual native game build, the original full RT64 State compilation and the user's gameplay capture were **not run locally**.