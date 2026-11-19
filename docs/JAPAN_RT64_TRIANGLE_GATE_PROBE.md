# Japanese robot RT64 culling-gate diagnostic (v5)

**Status: RESEARCH_ONLY.** This is a strictly opt-in, read-only diagnostic on the user's **already instrumented v4** RT64 interpreter. The original Japanese ROM is neither modified nor published. It does not change draw/cull decisions, rendering settings, textures, matrices or GPU workloads.

## Why this diagnostic is needed

The user's real Japanese native RT64 trace confirmed **all 7 original file-0x0197 nested F3DEX display lists execute with all 264 commands mapped**, and 9/9 texture image address resolutions match their expected physical addresses for both samples. In particular texture segments `0x0B` and `0x0C` resolve from `0x787CA950` to physical `0x007CA950`; this weakens the earlier segmented texture-address mismatch hypothesis.

However, the existing probe records 104 encoded triangle calls per set of seven lists, but its `tri_queued` totals only 72, with **11 ambiguous delta measurements**. The name `tri_queued` in v4 actually represents increments in `state->drawCall.triangleCount` before/after each F3DEX `G_TRI2`/`G_TRI1` command. RT64 may flush, swap/reset, or otherwise change that counter inside the call path, so counter differences are **not proof of missing GPU geometry**.

Pinned RT64 source commit **`abb3d7ad0ed60a8a74aa839222d4c107e828b7f5`** has F3DEX `tri2()` calling `RSP::drawIndexedTri()` *twice* and `tri1()` calling it once; the latter function returns immediately if `(geometryMode & cullBothMask) == cullBothMask`, without incrementing the counter. This exact gate can be measured before the F3DEX handler runs, without patching `rt64_rsp.cpp` or changing the renderer.

The v5 upgrade adds `gate_pass=` and `gate_skip=` to the existing `[JP-RT64] END` records, along with one bounded `CULL_GATE` record per sampled list whenever both-sided culling activates. `gate_pass + gate_skip` should equal `tri_encoded` if the same, pinned F3DEX microcode is active; it remains an *expected function-call/gate* count, **not proof of actual GPU visibility**. With v5 installed, `tri_queued` continues to be logged unchanged for cross-reference.

## Verification and safety gate

`jp_rt64_triangle_gate_probe.py` *requires*:

1. The exact original Japanese 32-MiB decompressed ROM SHA-1 (`6f8745fecc3a5e7d4918c7a73353eb0726116ded`).
2. The untouched `.pre-jp-robot-probe` file from v4 with pinned Git blob SHA-1 `dccaa871f42671fad4dc65439155db5b4bbac27c`.
3. Current `lib/rt64/src/hle/rt64_interpreter.cpp` byte-for-byte equal to **v4's deterministic transformation of that pinned original**, with no manual edits or drift.
4. No existing `.pre-jp-tri-gate-v5` backup.

Any mismatch aborts before changes. On install, v5 backs up the current v4 source, changes only this same interpreter file, and keeps the v4 original backup. It does not reapply v4. **Never edit/override the hash guards to get a patch applied.**

## Ubuntu instructions (existing user's Japanese recomp checkout)

```bash
cd ~/Goemon64Recomp-JP

git fetch origin research/japan-native-actor-model-trace-20261118
# Fetch BOTH scripts; v5 imports the pinned v4 module from /tmp.
git show FETCH_HEAD:tools/japan_port/jp_rt64_robot_probe.py > /tmp/jp_rt64_robot_probe.py
git show FETCH_HEAD:tools/japan_port/jp_rt64_triangle_gate_probe.py > /tmp/jp_rt64_triangle_gate_probe.py

python3 /tmp/jp_rt64_triangle_gate_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 \
  --dry-run
```

Only if the last command reports `validated only`:

```bash
python3 /tmp/jp_rt64_triangle_gate_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 \
  --confirm-modify-private-rt64

cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-rt64-cull-v5.log"
```

Enter the affected robot scene, then filter the trace:

```bash
grep -E '\[JP-RT64\] (END|CULL_GATE)' "$HOME/goemon-jp-rt64-cull-v5.log"
```

A list with `tri_encoded=2 gate_pass=0 gate_skip=2` was rejected by the actual RT64 early culling *condition* at the time of its triangle command; that may be deliberate game state, not a defect. A list with `tri_encoded=2 gate_pass=2 gate_skip=0` passed the early gate, even if `tri_queued=0`; the old counter then under-represents actual calls. Next, examine the game-side geometry mode/culling setup or GPU draw packets depending on the results.

To restore v4 if needed:

```bash
cp lib/rt64/src/hle/rt64_interpreter.cpp.pre-jp-tri-gate-v5 \
   lib/rt64/src/hle/rt64_interpreter.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

Do not rerun an older upgrader on v5. `GOEMON_JP_RT64_TRACE=0` disables all probe logging at runtime. Raw ROM, full graphics command dumps and user memory/log files must not be committed.

## Verification status

- v4 helper source anchors and pinned early-return predicate inspected: PASS.
- ROM-free source transformation/reapplication/drift checks: PASS.
- Compiled C++ fixture with actual v4 helper plus v5 gate-count change: PASS (gated case, passing case, counter-reset case, disabled mode).
- The user's actual local pristine v4 backup and actual Japanese CMake relink: **NOT RUN HERE**.
- Live v5 RT64 graphics capture, GPU rasterization and visual fix: **NOT RUN / NOT CLAIMED**.