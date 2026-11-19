# Japanese robot: v12 CPU RDP TMEM load replay provenance

## Established evidence, not assumptions

v11 robot root `0x1938`, two independent sampled display-list executions, showed:

- Call **140** and **144** use 32×64 original **RGBA16** (`fmt=0`, `siz=2`, `tmem=0`, `line=8`) hash `0x8042c12b60ec2b4e`. `TEX_QUEUE`: **0 nonzero bytes out of 4,096** copied from **CPU RDP TMEM** before GPU decoding. The same hash was independently created and inserted into RT64's texture cache in that game run.
- Call **143** uses a distinct 32×64 hash `0x4263ca7ef085e861`, whose entire TMEM snapshot contains **3,550 nonzero bytes**. Not all pink-robot textures are zero.
- Existing RenderDoc fragment for missing expected-opaque shell at EID 1755 (different run) reported **54 indices / 18 triangles**, matching call 144's 18 triangles. This is supporting evidence, **not a unique EID→GameCall proof** without same-frame identity mapping. Other draw calls may have 18 triangles.
- Earlier RenderDoc resource `Texture Cache RGBA32 #112003` was blank; **the resource serial/cache index from that process does not transfer to a new run**.
- v10 `TEX_BIND` capped after 30,000 events; absence of a bind log **is not a cache miss**.

**Conclusion:** For hash `0x8042c12b60ec2b4e`, its data is already zero on the CPU before the decoder receives it. No evidence yet establishes why it was zero at TMEM upload time or proves the other body textures are healthy. No production fix is appropriate yet.

## Read-only v12 probe

The source-only installer `tools/japan_port/jp_rt64_tmem_replay_v12.py` instruments only **`src/hle/rt64_state.cpp`** at pinned `State::fullSyncFramebufferPairTiles` operations. It does not modify texture copy/decoding, shaders, rendering, ROM, or game code. Runtime gate: `GOEMON_JP_RT64_TEX_TRACE=1`.

At a 32×64 upload matching the two **exact v11 hashes** above, records at most **16** `TEX_REPLAY_TARGET` snapshots per process and the **32 most recent RDP LoadTile/LoadBlock/LoadTLUT operations** preceding that upload within that framebuffer-pair replay. Logs:

- frame, GameCall, texture hash, assigned tile, CPU TMEM nonzero byte count;
- each replayed load operation's index, type (`0` tile, `1` block, `2` TLUT), source texture address/dimensions/format/size, computed source start, tile destination TMEM offset/stride, and entire CPU TMEM nonzero count **before and after**;
- nonzero byte count of the **first 64 bytes** of source guest RDRAM only if safely within the conservative lower 4 MiB. `source_nonzero64=4294967295` means **UNREAD/OUT_OF_RANGE**, not zero or an invalid texture. **No source bytes are emitted.**

**Important limitations:** RDRAM sample covers only **64 bytes**, not the full texture; full-TMEM byte counts cover **4,096 bytes**, not the source tile alone; the operation ring covers the most recent 32 loads within a replay invocation. A load may have been performed earlier in another framebuffer pair; absence from this ring is not proof no load occurred. A load from RDRAM whose first 64 bytes are zero may contain later nonzero source bytes. Rendering proof still needs same-frame GPU evidence.

## Prerequisites and installation

Requires user private checkout with authenticated v11 renderer, v10 texture-cache source, v8 interpreter, **v7 State source**, intact `.pre-jp-*` backups, and decompressed original Japanese 32 MiB ROM (SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`). All three source chains are compared against deterministic pinned transformations before any modification. A backup of the exact v7 State source is made at `.pre-jp-tmem-replay-v12`; reapplication is refused. No ROM bytes are published.

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
for name in jp_rt64_robot_probe jp_rt64_triangle_gate_probe jp_rt64_face_index_probe jp_rt64_drawcall_account_probe jp_rt64_raster_handoff_probe jp_rt64_target_state_probe jp_rt64_texture_origin_probe jp_rt64_robot_texture_link_v11 jp_rt64_tmem_replay_v12 analyze_jp_rt64_tmem_replay_v12; do
    git show "FETCH_HEAD:tools/japan_port/${name}.py" > "/tmp/${name}.py"
done
python3 /tmp/jp_rt64_tmem_replay_v12.py --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 --dry-run
```

Only after `PASS`/`validated only`, opt-in install and compile:

```bash
python3 /tmp/jp_rt64_tmem_replay_v12.py --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 --confirm-modify-private-rt64
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 ./build-generated/japan-native-game/Goemon64RecompiledJP 2>&1 | tee ~/goemon-jp-rt64-tmem-replay-v12.log
python3 /tmp/analyze_jp_rt64_tmem_replay_v12.py ~/goemon-jp-rt64-tmem-replay-v12.log
```

Ensure the affected pink robot appeared, then stop the game. If the analyzer reports no events, check the raw `grep -F '[JP-RT64] TEX_REPLAY_'` output; hashes may differ or the cap may be consumed before the robot is encountered.

## Interpretation

- Target **all-zero TMEM** with a preceding load showing **first64 RDRAM bytes zero** and TMEM unchanged ⇒ upstream guest RDRAM/source readiness or address selection is a strong hypothesis; further source probing required (first64 cannot prove full texture zero).
- **Nonzero source64** but TMEM remains zero after the corresponding load ⇒ examine `LoadTile` dimensions, destination `tmem`, source address and `RDP::loadTileOperation` / `loadBlockOperation` implementation. The load might intentionally write another region; same-TMEM region comparison still needed.
- TMEM becomes nonzero after a load, then **all-zero at target upload** ⇒ look for later clearing/overwriting load operations or framebuffer-pair replay reset.
- A single zero texture hash shared by multiple model components can explain repeated losses without any GPU cache misses; do not patch texture decoding until the source path is verified.

## Restore the v7 State patch (v11 renderer and v10 cache remain installed)

```bash
cp lib/rt64/src/hle/rt64_state.cpp.pre-jp-tmem-replay-v12 lib/rt64/src/hle/rt64_state.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

Rollback requires a successful actual backup. Do not delete the backup while v12 is installed.

## Verification boundary

Source-pin checks against `klorfmorf/rt64@abb3d7ad0ed60a8a74aa839222d4c107e828b7f5`; synthetic transforms and isolated C++ hook compilation tested on the assistant's host. **Not tested**: complete user-side private build, live gameplay, actual source-address values, or renderer correctness. Research-only. No matching-C promotion.