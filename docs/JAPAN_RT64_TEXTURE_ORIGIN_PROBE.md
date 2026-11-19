# Japanese native RT64: v10 texture-origin probe (RESEARCH_ONLY)

## Proven prior evidence

The user's **real** RenderDoc capture of an expected-opaque, missing region of the
pink robot shows `EID 1755` in Colour Pass #4 executing
`vkCmdDrawIndexed(54,1)` (18 triangles), then **fragment shader discard** at a
sample whose texture colour is `(0,0,0,0)` and vertex alpha is `1`.
`_5608=false`: framebuffer alpha-as-coverage conversion is **not** the cause
for this fragment. RenderDoc's dynamic descriptor array access selects
`_set1_bind0[89]`, `Texture Cache RGBA32 #112003`, 32×64,
`R8G8B8A8_UNORM`, whose RGBA and alpha views show zero values.
Its Resource Inspector says `No static usage observed`; this is not evidence
that the texture is unused (the debugger has established dynamic access).

The original Japan and USA robot geometry asset 0x0197 is identical. Both
sampled original JP robot-model display-list sets account for **104/104**
unique triangles through host draw-command recording. No GPU pixel-output
claim follows from CPU counts. The native 4× rendering pass is visible as
scissor scale `8,16,312,224` vs `32,64,1248,896`, not separately established
to be a duplicate render bug.

## Why the v10 trace is useful

Pinned RT64 `klorfmorf/rt64@abb3d7ad...` has this pathway:

1. `TextureManager::uploadTexture` hashes RDP TMEM and enqueues a 4096-byte
   snapshot for decode; `uploadEmpty` enqueues `decodeTMEM=false` and does **not**
   directly create a `Texture Cache RGBA32 #...` resource.
2. `TextureCache::queueGPUUploadTMEM` contains the TMEM bytes and tile decode
   metadata (`fmt`, `siz`, `tmem`, `line`, `tlut`, `palette`).
3. `TextureCache::uploadThreadLoop` creates `Texture Cache RGBA32 #N`, dispatches
   the 8×8 `TextureDecodeCS.hlsl`, then commits the decoded resource to the
   cache. This GPU compute-output resource is always RGBA32, regardless of the
   original N64 format.
4. `TextureMap::add` stores the hash→cache-index mapping.
5. `FramebufferRenderer::createGPUTiles` looks up that hash, and binds the
   resulting cache index or a fallback if the lookup fails.

**Four read-only log events**:

- `TEX_QUEUE`: hash, dimensions, `decode`, number of source TMEM bytes,
  **nonzero byte count of the entire snapshot**, 64-bit FNV-1a fingerprint,
  input tile format/size/address/stride/palette/TLUT.
- `TEX_CREATE`: hash, `Texture Cache RGBA32 #N` **resource serial**, decode
  metadata. This number is **not** the GPU descriptor array index.
- `TEX_ADD`: hash, **cache-index slot**, decoded status.
- `TEX_BIND`: hash, cache index, cache hit/miss, dimension and tile properties
  at the actual renderer binding, if the tile size is 32×64.

Only **32×64** inputs/decoded textures are logged, bounded independently to
30,000 entries at each stage and gated by `GOEMON_JP_RT64_TEX_TRACE=1`.
No actual TMEM bytes, ROM assets, decoded texture pixels or RenderDoc capture
are logged. These identifiers are only stable **within the same execution**:
`#112003` and `[89]` from a previous capture cannot be assumed to recur.
A nonzero count across 4096 source TMEM bytes does **not** imply the relevant
32×64 tile region has nonzero data. GPU readback is not performed by v10.

## Installation and capture (on user's Ubuntu)

Working directory: `~/Goemon64Recomp-JP`; existing pinned v9 private RT64
source and backup chain are prerequisites. Do **not** merge research probes
into production. All source edits remain local/private under `lib/rt64`.

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
for name in jp_rt64_robot_probe jp_rt64_triangle_gate_probe jp_rt64_face_index_probe jp_rt64_drawcall_account_probe jp_rt64_raster_handoff_probe jp_rt64_target_state_probe jp_rt64_texture_origin_probe analyze_jp_rt64_texture_origin_v10; do
  git show "FETCH_HEAD:tools/japan_port/${name}.py" > "/tmp/${name}.py"
done
python3 /tmp/jp_rt64_texture_origin_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --dry-run
```

**Only after `validated only`**, run:

```bash
python3 /tmp/jp_rt64_texture_origin_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --confirm-modify-private-rt64
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 \
  ./build-generated/japan-native-game/Goemon64RecompiledJP 2>&1 \
  | tee ~/goemon-jp-rt64-texture-origin-v10.log
```

Get near the robot, then exit game. Analyze:

```bash
python3 /tmp/analyze_jp_rt64_texture_origin_v10.py \
  ~/goemon-jp-rt64-texture-origin-v10.log
# A cache index in the *same run* may be used to narrow matches:
python3 /tmp/analyze_jp_rt64_texture_origin_v10.py \
  ~/goemon-jp-rt64-texture-origin-v10.log --cache-index 89
# Warning: index 89 is from one prior RenderDoc run, not guaranteed in a new process.
```

An unfiltered report prints the 25 hashes with the most 32×64 binds; use
`--limit 0` for all. Individual source-event grep:

```bash
grep -E '^\[JP-RT64\] TEX_(QUEUE|CREATE|ADD|BIND)' \
  ~/goemon-jp-rt64-texture-origin-v10.log | tail -n 50
```

## Interpretation and next step

- `TEX_BIND hit=0` for the suspect hash: cache-miss/fallback is an
  immediate lead; inspect why `TextureMap::use` cannot find it.
- `TEX_QUEUE decode=1 nonzero=0`: entire input snapshot empty before GPU
  decode. Trace original JP load commands and RDP TMEM population.
- `decode=1 nonzero>0` with matching `TEX_CREATE`/`TEX_ADD` and `hit=1`:
  upload had some nonzero raw data but may still be empty in relevant tile.
  Next map tile offsets and inspect the GPU compute decoder/actual decoded
  pixels. No assertion that GPU decode succeeded or failed from these logs.
- `TEX_BIND` without observed queue: upload may have occurred outside current
  logging window/cap, or the binding may be to a tile copy/other path.
- Serial/slot changes across launches must not be treated as cache corruption.

A negative v10 result is still useful; preserve captured log locally and do
not change shader alpha/culling settings to mask symptoms.

## Source pinning and rollback

ROM decompressed Japan SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`.
Exact original RT64 Git blobs: renderer
`46289b1961b88f82f7d8437402e96881080bee96`, texture cache
`0848f3eda2b9577b54b4549ee8b168957a07545e`.
The tool verifies original renderer, v8 backup, exact installed v9 renderer,
v8 interpreter, v7 State, original texture-cache Git blob, and rejects
existing v10 backups. It adds only diagnostic statements; **no ROM/game,
texture-cache algorithm, GPU shader or upload behaviour changes**.

Rollback **both** files, then rebuild:

```bash
for name in src/render/rt64_framebuffer_renderer.cpp src/render/rt64_texture_cache.cpp; do
  cp "lib/rt64/${name}.pre-jp-texture-origin-v10" "lib/rt64/$name"
done
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

**Tests:** local Python source/guard/synthetic-C++ fixture and log-analyzer tests
only. Real user source patching, native JP CMake build and gameplay v10 trace
have not been run in the authoring environment. `RESEARCH_ONLY`.