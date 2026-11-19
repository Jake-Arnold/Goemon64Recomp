# Japanese native robot: v6 RT64 workload face-index accounting

**Status: RESEARCH_ONLY.** This is an opt-in, read-only diagnostic upgrade for the already instrumented v5 local RT64 interpreter. It is not a rendering fix, ROM patch, matching-C promotion, or GPU-visibility proof. Do not merge production rendering modifications based solely on this trace.

## Live v5 evidence from user

The user ran the native Japanese Goemon64Recomp with v5 RT64 instrumentation on the Small Pink Robot scene. Each of the seven original model-file `0x0197` nested F3DEX lists executed twice. Per sample:

- 264 instructions mapped; zero unmapped.
- 104 encoded triangle calls: `8,8,10,2,10,2,64` by roots `0x12F0,0x1420,0x1538,0x1640,0x1708,0x1810,0x1938`.
- `gate_pass=104`, `gate_skip=0`. The exact early `RSP::drawIndexedTri()` both-face culling gate is not discarding these calls.
- The old `tri_queued` sums to only 72 and reports 11 ambiguous delta measurements. This is **not** evidence of 32 rejected GPU triangles.
- Nine texture-source resolution checks match in each sample, including segments B and C mapping to physical RDRAM `0x007CA950`.

The pinned RT64 source `klorfmorf/rt64@abb3d7ad0ed60a8a74aa839222d4c107e828b7f5`, `src/hle/rt64_state.cpp`, demonstrates why `tri_queued` is unreliable: `State::flush()` records a draw call with the current `triangleCount`, then resets `state->drawCall.triangleCount = 0`. It can be triggered inside `RSP::drawIndexedTri()` as framebuffers or draw status change. A pre/post counter delta therefore undercounts triangles that were flushed mid-command.

In the same pinned RT64 source, `src/hle/rt64_rsp.cpp`, the surviving triangle call appends exactly three indices to `workload.drawData.faceIndices` before it increments the resettable `drawCall.triangleCount`. The per-workload face-index vector is the next more reliable measurement of *CPU-side geometry preparation*.

## v6 diagnostic

New script: `tools/japan_port/jp_rt64_face_index_probe.py`.

- Requires the exact original Japanese **decompressed 32 MiB** ROM SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`, the intact pinned original RT64 interpreter backup, the byte-for-byte deterministic v4 source from that original, and the precise v5 source generated from v4. The v5 backup must match deterministic v4. Any mismatch aborts.
- Modifies only the private `lib/rt64/src/hle/rt64_interpreter.cpp`, and only after explicit confirmation. Creates `.pre-jp-face-index-v6` backup; reinstallation fails.
- At each sampled original model-file list's F3DEX `0xB1` (TRI2) or `0xBF` (TRI1) command, measures `workload.drawData.faceIndices.size()` immediately before and after the **unaltered handler**. Requires unchanged workload cursor and a nonnegative, aligned growth of zero/three/six indices as appropriate. Other cases increment `face_ambiguous`.
- Appends `face_index_tri` and `face_ambiguous` to existing `[JP-RT64] END` records, leaving the earlier fields unchanged. Disabled unless `GOEMON_JP_RT64_TRACE=1`. No user data, raw ROM contents, vertex positions, or index contents are logged.
- `face_index_tri=104, face_ambiguous=0` across seven roots would establish 104 triangle calls reached the CPU workload face-index buffer for this sample. It still would **not** establish that all were rasterized, visible, non-degenerate or textured correctly. If lower, inspect per-root results and ambiguous cursors before interpreting a loss.

## Execute in the same Ubuntu checkout

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
git rev-parse FETCH_HEAD

git show FETCH_HEAD:tools/japan_port/jp_rt64_robot_probe.py > /tmp/jp_rt64_robot_probe.py
git show FETCH_HEAD:tools/japan_port/jp_rt64_triangle_gate_probe.py > /tmp/jp_rt64_triangle_gate_probe.py
git show FETCH_HEAD:tools/japan_port/jp_rt64_face_index_probe.py > /tmp/jp_rt64_face_index_probe.py

python3 /tmp/jp_rt64_face_index_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 \
  --dry-run
```

Only after `validated only`:

```bash
python3 /tmp/jp_rt64_face_index_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 \
  --confirm-modify-private-rt64

cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee ~/goemon-jp-rt64-face-v6.log

grep -F '[JP-RT64] END' ~/goemon-jp-rt64-face-v6.log
```

If v6 causes a build or gameplay regression, restore exactly the backed up v5 source and relink:

```bash
cp lib/rt64/src/hle/rt64_interpreter.cpp.pre-jp-face-index-v6 \
   lib/rt64/src/hle/rt64_interpreter.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

**Verification gates actually executed in this research environment:** 7 Python unit/synthetic checks including a compiled C++ test of workload vector growth, simulated internal counter resets, no-op handler, malformed index growth, and workload cursor changes; Python `py_compile`; ROM and private user CMake executable **not** run in this environment. Source precision is checked at application time against the user's private checkout.

No source ROM, binary assets, extracted Gfx content, or user logs should be committed.