# Japanese native RT64 — v11 robot-GameCall → texture-hash link (RESEARCH_ONLY)

## Current observed facts

- The robot model's seven original nested display lists produced **104 unique triangles** per captured sample; CPU-side face recording, build and host GPU draw-command recording all accounted for them.
- Actual RenderDoc GPU pixel history for the missing expected-opaque pink shell at draw **EID 1755 / Colour Pass #4** showed shader alpha-threshold discard; sampled texture-path RGBA was **(0,0,0,0)** while vertex alpha was `1` and framebuffer alpha-as-coverage conversion was **off**.
- Dynamically accessed GPU descriptor array slot `89` (in that **different process**) resolved to **Texture Cache RGBA32 #112003**, a blank 32×64 decoded RGBA8 output. Its name/slot are **not stable across processes**, and static resource-usage listing is not conclusive for descriptor indexing.
- v10 instrumentation succeeded in the user's live game. The pasted analyzer output was **30,606 events across 90 hashes**, with many complete queue/create/add/bind chains and no shown bind misses. All reported nonzero counts measure the *entire 4,096-byte TMEM snapshot*, not an individual tile or decoded output.
- The v10 per-stage **30,000 `TEX_BIND` log cap** can hide robot texture bindings late in the session; frequency ranking is not an adequate way to identify the suspect model texture. Repeated cache creation serials/indexes under one hash are not proof of corruption (eviction/recreation can occur).

## What v11 adds

A **single renderer-only** read-only patch to an already authenticated **exact v10** private RT64 source, logging only GameCalls that overlap the previously authenticated robot 0x0197 face-index ranges (seven roots, two samples). At the source `RASTER BUILT` loop, `call.callDesc.tileIndex/tileCount` index `drawData.callTiles`, the same tiles used by the cache-binding stage. The bounded v11 hook (`<=1,024` matched GameCalls, up to eight tile slots each) emits:

- `TEX_ROBOT_CALL`: source frame/root/sample, GameCall identity/triangle count, tile index/count and texture-on indicator.
- `TEX_ROBOT_TILE`: each tile's original `tmemHashOrID`, requested dimensions, valid/tile-copy flags, fmt/siz/tmem/line/TLUT/palette/raw flag.

A new offline analyzer joins the **exact observed robot tile hash** to the same-run v10 `TEX_QUEUE`, `TEX_CREATE`, `TEX_ADD`, and `TEX_BIND` lines. It reports the 30,000 binding-row ceiling explicitly and does not misclassify an absent capped binding record as a cache miss. This avoids the unstable former RenderDoc resource index and avoids logging tens of thousands of irrelevant environmental bindings. The v10 trace remains enabled; no ROM contents, GPU readbacks, actual TMEM bytes or pixels are logged.

## Ubuntu runbook

From `~/Goemon64Recomp-JP` with the pinned original v10 installation already successfully built and the private `.pre-jp-*` backups intact:

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
for name in jp_rt64_robot_probe jp_rt64_triangle_gate_probe jp_rt64_face_index_probe jp_rt64_drawcall_account_probe jp_rt64_raster_handoff_probe jp_rt64_target_state_probe jp_rt64_texture_origin_probe jp_rt64_robot_texture_link_v11 analyze_jp_rt64_texture_origin_v10 analyze_jp_rt64_robot_tile_v11; do
  git show "FETCH_HEAD:tools/japan_port/${name}.py" > "/tmp/${name}.py"
done
python3 /tmp/jp_rt64_robot_texture_link_v11.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --dry-run
```

**Only** if the dry run prints `validated only`:

```bash
python3 /tmp/jp_rt64_robot_texture_link_v11.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --confirm-modify-private-rt64
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 \
 ./build-generated/japan-native-game/Goemon64RecompiledJP 2>&1 | tee ~/goemon-jp-rt64-robot-texture-v11.log
```

Navigate to the affected robot, then exit:

```bash
python3 /tmp/analyze_jp_rt64_robot_tile_v11.py ~/goemon-jp-rt64-robot-texture-v11.log --root 0x1938
# For all seven original roots:
python3 /tmp/analyze_jp_rt64_robot_tile_v11.py ~/goemon-jp-rt64-robot-texture-v11.log
```

If the robot is **not** captured by the prior v8 bounded registry because the game scene never reached those display lists, no v11 records will appear; the analyzer will report this instead of inventing a match. If no 32×64 tile is associated with the robot's GameCalls, revisit the per-draw fragment texture indexing: an `EID` by itself is not an authenticated source-GameCall mapping, and texture selection may be through a different tile or a draw outside the current face ranges.

## Interpreting results and next diagnostic

1. For robot-matched regular tiles (`valid=1`, `copy=0`), identify hashes whose `requested=32x64` and `TEX_QUEUE`/`TEX_CREATE`/`TEX_ADD` reports.
2. If a hash has queued TMEM and correct cache insertion but a later RenderDoc snapshot of the *same process* shows its decoded `RGBA32` output blank, focus on tile region, TMEM decode constants and shader dispatch. All-TMEM nonzero is not evidence that this individual tile is nonzero.
3. If a robot-associated hash is absent from `TEX_BIND` but the log has 30,000 bindings, the cap is a sufficient explanation: do **not** report a cache miss.
4. A `copy=1` tile is a framebuffer/tile-copy ID, not a normal texture-cache hash; the analyzer flags it rather than joining to ordinary TMEM uploads.
5. If multiple robot 32×64 hashes exist, inspect the exact per-call tile and the new same-run decoded GPU serial; do not infer the body hash from general popularity.

No rendering fix, shader alpha/cull changes, matching-C promotion or ROM changes follow from this tool.

## Source guard and rollback

v11's installer is fail-closed: it hashes the authenticated Japanese decompressed ROM, reconstructs the pinned v8→v9→v10 renderer via original backup, checks the v10 renderer and original-cache backups and deterministic modified v10 cache, revalidates v8 interpreter/v7 State, checks exact unique injection anchors, and rejects an already applied v11. It edits **only** `lib/rt64/src/render/rt64_framebuffer_renderer.cpp` when explicitly confirmed, backing it up as `.pre-jp-robot-texture-v11`. No standalone v10/cache reinstall needed.

```bash
cp lib/rt64/src/render/rt64_framebuffer_renderer.cpp.pre-jp-robot-texture-v11 \
   lib/rt64/src/render/rt64_framebuffer_renderer.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

Synthetic Python and C++ hook tests have run locally. The user's full native Ubuntu game CMake build and actual v11 gameplay log have **not** been run here. Research branch and PR only.