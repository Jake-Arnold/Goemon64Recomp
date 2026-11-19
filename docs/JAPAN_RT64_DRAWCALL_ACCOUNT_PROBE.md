# Japanese RT64 robot — v7 framebuffer GameCall conservation probe

**Status: `RESEARCH_ONLY`.** This is source-only, read-only, opt-in instrumentation for a private Japanese native recompilation. It does not repair the model, change culling/texture/matrix logic, force a renderer flush, or prove GPU rasterization.

## Confirmed live v6 checkpoint — 19 November 2026

The user captured two real RT64 executions of every one of the seven original JP robot file-`0x0197` F3DEX nested lists. **Per set of seven lists:**

- Exactly seven list roots executed; 264/264 opcodes mapped; zero unmapped.
- 104 encoded triangle calls, 104 passed the RT64 early both-face cull gate, none skipped.
- Exactly **104 triangles / 312 face indices** appended to RT64's CPU workload `drawData.faceIndices` (roots 8, 8, 10, 2, 10, 2, 64); **zero ambiguous** samples.
- Texture image operand resolution matched 9/9 observations, including segments B and C resolving to physical RDRAM `0x007CA950`.
- The old v4/v5 `tri_queued` tally of 72 undercounts 104 because it relies on a resettable field. The later face-index tally is stronger evidence of CPU geometry preparation; this is **not** evidence of pixel output or of the cause of the visually missing geometry.

## Pinned RT64 source checkpoint

The `klorfmorf/rt64@abb3d7ad0ed60a8a74aa839222d4c107e828b7f5` code in `src/hle/rt64_state.cpp` (Git blob `f9f0ad8cdc7104f50ca0efd1a9750798e0aec094`) has the following sequence inside `State::flush()`:

1. Return if pending triangle count is zero.
2. Copy `drawCall` into `gameCall.callDesc`.
3. Append `gameCall` with `fbPair.addGameCall(gameCall)`.
4. Later reset `drawCall.triangleCount` to zero.

`RSP::drawIndexedTri` may invoke `State::flush` as projection or draw status changes; therefore the old triangle-counter delta is not a cumulative metric.

## What v7 measures

`tools/japan_port/jp_rt64_drawcall_account_probe.py` extends the exact v6 RT64 interpreter, and additionally instruments the exact pinned `State::flush()` **after** actual framebuffer-pair insertion. The opt-in log (`GOEMON_JP_RT64_TRACE=1`) appends:

```
[JP-RT64] DRAWCALL root=... sample=... flush_calls=... flush_tri=... pending_in=... pending_out=... conserved_tri=... face_index_tri=... cursor_ok=... ambiguous=... match=...
```

For each bounded robot list, the diagnostic checks:

`conserved_tri = sum(triangles copied into real FB GameCalls during that list) + pending_out - pending_in`.

`pending_in` matters: the first flush in a list may include triangles created in a **prior** list. If the workload cursor is stable, `ambiguous=0`, and `conserved_tri == face_index_tri`, it establishes accounting consistency between the accepted face-index growth and RT64's pending/recorded GameCall triangles. Some triangles may still be pending at list end; this is not proof all were flushed within that list or presented to a GPU.

The tool leaves the previous v6 `[JP-RT64] BEGIN/TEX/END` records unchanged and caps output to two executions of each of the seven verified original list roots. The `DRAWCALL` report appears immediately after each corresponding `END`. Other games or rooms are not targeted unless they coincidentally share the exact ROM-root mapping, so this remains a research diagnostic, not a universal per-actor correlator.

## Fail-closed source gate and safety

The script checks all of the following **before either private source is modified**:

- Exact decompressed 32-MiB Japanese rev-0 ROM SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`.
- Original RT64 interpreter backup Git blob `dccaa871f42671fad4dc65439155db5b4bbac27c`.
- Exact deterministic v4, v5, v6 interpreter transformations, and their original backups.
- The original pristine pinned `rt64_state.cpp` Git blob `f9f0ad8cdc7104f50ca0efd1a9750798e0aec094`.
- Exactly one source anchor for every injected hook; no existing v7 backup.

The upgrader modifies **two ignored local RT64 sources only**: `lib/rt64/src/hle/rt64_interpreter.cpp` and `lib/rt64/src/hle/rt64_state.cpp`. It creates `.pre-jp-drawcall-v7` backups for both, refuses repeat installation and restores sources on write failure. The original ROM, original private generated C, RT64 graphics algorithms, and repository/submodule pins are unchanged. Do not override guards on failure. No unapproved submodule commit or upstream rendering change is made.

## Execute in the existing Ubuntu JP checkout

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118

git show FETCH_HEAD:tools/japan_port/jp_rt64_robot_probe.py > /tmp/jp_rt64_robot_probe.py
git show FETCH_HEAD:tools/japan_port/jp_rt64_triangle_gate_probe.py > /tmp/jp_rt64_triangle_gate_probe.py
git show FETCH_HEAD:tools/japan_port/jp_rt64_face_index_probe.py > /tmp/jp_rt64_face_index_probe.py
git show FETCH_HEAD:tools/japan_port/jp_rt64_drawcall_account_probe.py > /tmp/jp_rt64_drawcall_account_probe.py

python3 /tmp/jp_rt64_drawcall_account_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --dry-run
```

Only after **`validated only`**:

```bash
python3 /tmp/jp_rt64_drawcall_account_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --confirm-modify-private-rt64

cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-rt64-drawcall-v7.log"

grep -F '[JP-RT64] DRAWCALL' "$HOME/goemon-jp-rt64-drawcall-v7.log"
```

If the tool rejects a mismatch, keep the files untouched and investigate the differing source/revision. If a native build fails after installation, restore **both** v7 backups and relink:

```bash
cp lib/rt64/src/hle/rt64_interpreter.cpp.pre-jp-drawcall-v7 \
   lib/rt64/src/hle/rt64_interpreter.cpp
cp lib/rt64/src/hle/rt64_state.cpp.pre-jp-drawcall-v7 \
   lib/rt64/src/hle/rt64_state.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

## Verification and limits

Locally executed **4** synthetic Python/C++ tests: deterministic v4–v7 source transformation, repeat/missing-anchor failure, backup and exact-source gates, and compiled C++ mock exercising carry-in triangles, an actual GameCall flush/reset, pending triangles and workload-cursor ambiguity. Python syntax compilation passes. **Not executed in this research environment:** modification of the user's private v6 RT64 sources, actual JP relink, live v7 observations, GPU draw packet, vertex shader invocation, visibility, texture appearance or a rendering fix.

All outputs remain `RESEARCH_ONLY` and should stay on the draft PR/issue, not be merged into production. Do not commit the original ROM, extracted model data or raw private gameplay logs.