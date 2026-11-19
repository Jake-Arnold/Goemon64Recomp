# Goemon JP robot rendering: v8 CPU GameCall → RT64 raster handoff

**Status: RESEARCH_ONLY.** Strictly source-only, opt-in, fail-closed diagnostics for the original Japanese native build. Does **not** patch a ROM, change a draw/cull operation or claim a graphics fix. Does **not** establish completed GPU execution or on-screen visibility.

## Motivation and live evidence (19 Nov 2026)

The user's v7 capture of original JP resource file `0x0197` shows two identical full samples of seven original display lists. In each sample 264/264 commands mapped; 104/104 triangle calls passed the both-face cull gate; 104/104 triangles entered the CPU face-index workload; and all seven per-list framebuffer GameCall conservation checks returned `cursor_ok=1 ambiguous=0 match=1`. The old v4 `tri_queued=72` counter was reset by RT64's `State::flush` and is not missing geometry.

The next code path is pinned `klorfmorf/rt64@abb3d7ad0ed60a8a74aa839222d4c107e828b7f5`: `State::flush → fbPair.addGameCall → State::submitFramebufferPair → FramebufferRenderer::addFramebuffer → submitRasterScene → RenderWorker::commandList->drawIndexedInstanced/drawInstanced`. Source shows the raster builder skips projections where `proj.scissorRect.isNull()` and the raster command recorder skips instances when `triangles.scissor.isEmpty()`. A CPU GameCall alone therefore does not prove a GPU draw command is recorded.

## What v8 records

The existing v7 interpreter adds an immutable, bounded *trace-only* registry keyed by the original framebuffer workload's `submissionFrame` and each of the **14** observed (root, sample) pairs. One registry entry captures the exact face-index interval `[first,end)` generated within an original model list; it refuses intervals where the v6 counters disagree or the workload cursor moves. All registry reads and writes use a mutex; only `GOEMON_JP_RT64_TRACE=1` activates the probe.

The pinned, previously unmodified `src/render/rt64_framebuffer_renderer.cpp` then uses intersection of each authentic range and the current GameCall's own `meshDesc.faceIndicesStart + triangleCount * 3`. Adjacent lists can share a single GameCall; overlaps are accounted for separately rather than guessing which root owns the entire call.

- `[JP-RT64] FACE_RANGE`: source range registered, `frame`, `first`, `end`, `triangles`.
- `[JP-RT64] RASTER SKIP_PROJECTION`: matched GameCall omitted at the null projection-scissor check.
- `[JP-RT64] RASTER BUILT`: a matched GameCall became a renderer instance; includes original triangles, overlap triangles, raster call type, `scissor_empty` and `pipeline` boolean.
- `[JP-RT64] RASTER SKIP_SCISSOR`: an instance was excluded at the actual raster scissor check.
- `[JP-RT64] RASTER DRAW_RECORDED`: real host graphics `drawIndexedInstanced`/`drawInstanced` invocation returned. **This is command recording, not a GPU completion or pixel test.**

Per-frame instance tags are held in a second fixed-size, thread-local table (maximum 256) and cleared with `FramebufferRenderer::resetFramebuffers`. The original scene data, renderer states and GPU command arguments are not modified. No raw ROM, textures, or framebuffer content is logged.

Only perspective/orthographic paths (with `meshDesc.faceIndicesStart`) can be positively correlated via this face-index method. A missing match might reflect a different projection type, producer/consumer scheduling or workload layout; absence alone cannot prove GPU-side geometry loss. The two frame samples are intentionally limited by v4's existing maximum.

## Source gates

`jp_rt64_raster_handoff_probe.py` requires *all*:

1. Japanese 32 MiB decompressed ROM SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`.
2. Original RT64 interpreter `.pre-jp-robot-probe` matches pinned upstream Git blob `dccaa871f42671fad4dc65439155db5b4bbac27c`.
3. Current interpreter is **exactly** the deterministic v4→v5→v6→v7 result, with no local edits.
4. `rt64_state.cpp.pre-jp-drawcall-v7` matches pinned upstream Git blob `f9f0ad8cdc7104f50ca0efd1a9750798e0aec094` and current state is exactly the v7 source-only transformation.
5. Previously untouched RT64 framebuffer renderer matches pinned upstream Git blob `46289b1961b88f82f7d8437402e96881080bee96`.
6. No existing `.pre-jp-raster-v8` backups. The upgrader creates exact pre-v8 backups of both edited files before writing and aborts on drift.

The original source from any other RT64 revision MUST NOT be force-patched with this tool.

## Ubuntu commands

```bash
cd ~/Goemon64Recomp-JP

git fetch origin research/japan-native-actor-model-trace-20261118
for name in jp_rt64_robot_probe jp_rt64_triangle_gate_probe jp_rt64_face_index_probe jp_rt64_drawcall_account_probe jp_rt64_raster_handoff_probe analyze_jp_rt64_raster_v8; do
  git show "FETCH_HEAD:tools/japan_port/${name}.py" > "/tmp/${name}.py"
done

python3 /tmp/jp_rt64_raster_handoff_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --dry-run
```

Only after `validated only` and exact gate passes:

```bash
python3 /tmp/jp_rt64_raster_handoff_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --confirm-modify-private-rt64

cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4

GOEMON_JP_RT64_TRACE=1 ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-rt64-raster-v8.log"

python3 /tmp/analyze_jp_rt64_raster_v8.py "$HOME/goemon-jp-rt64-raster-v8.log"
```

The offline summary prints per-list source ranges, matched renderer instances, recorded draw commands, projection/scissor skips and missing pipelines; it does not print actor addresses or raw commands.

## Corrected offline analyzer (19 November 2026)

**Caution:** The originally published v8 analyzer aggregated every `RASTER BUILT`/`DRAW_RECORDED` log occurrence, including repeated recording of the same GameCall within one workload frame. The live summary showed `range=104` versus `built=208`, `recorded=208`; the user's `root=0x1938` trace demonstrated one frame and the same six GameCall IDs processed twice. That overcounts unique source contributions, not necessarily raster work. The corrected analyzer deduplicates by `(root,sample,frame,call)`, records distinct built/recorded source geometry separately from raw repeated draw commands, and reports `repeat_built`, `repeat_recorded`, and `raw_recorded` totals. See `docs/JAPAN_RT64_RASTER_HANDOFF_ANALYZER_CORRECTION.md`. No rendering or trace instrumentation changes are required.

## Interpretation

- `range=104`, `built=104`, `gpu_command_recorded=104`, `skip_projection=0`, `skip_scissor=0` (per sample, summing roots) means **all 104 encoded robot triangles are accounted for through CPU host graphics command recording**; still no GPU pixel visibility claim.
- `SKIP_PROJECTION` or `SKIP_SCISSOR` with nonzero overlapping robot triangles is a concrete RT64 CPU-side discard decision to investigate, not automatically an implementation defect. Compare against actual original renderer behaviour.
- `range=104` but `built<104` with no skip could mean unmatched projection/raw-vertex paths, rendering cutoff, frame scheduling or a diagnostic limitation. Do not infer missing geometry automatically.
- `gpu_command_recorded<104` while `built=104` and nonzero scissor skips narrows the loss to host raster filtering. Other differences require profiling at the relevant rendering stage.

Restore v7 in the local *private* workspace if a crash or compiler failure occurs:

```bash
cp lib/rt64/src/hle/rt64_interpreter.cpp.pre-jp-raster-v8 \
   lib/rt64/src/hle/rt64_interpreter.cpp
cp lib/rt64/src/render/rt64_framebuffer_renderer.cpp.pre-jp-raster-v8 \
   lib/rt64/src/render/rt64_framebuffer_renderer.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

Do not reapply old v4–v7 instruments to v8. Do not commit ROM assets, generated C or raw memory logs.

## Actual tests here

7 local Python tests pass (4 source/fail-closed/compiled C++ tests for v8 and 3 offline-summary tests). The C++ test compiles the actual bounded range registry and renderer tag helper with a simulated GameCall spanning two list intervals, concurrency exercises, and both scissor outcomes. `py_compile` passes. Exact upstream blob hashes and renderer anchor uniqueness were checked against GitHub connector results. **Not run here:** patch on the user's private v7 RT64 files, full native CMake build, Japanese gameplay, actual GPU execution or RT64 on-screen verification. Retain `RESEARCH_ONLY`.