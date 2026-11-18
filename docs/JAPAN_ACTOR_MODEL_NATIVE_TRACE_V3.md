# Japanese native actor trace v3 — bounded guest graphics-command evidence

**Status: RESEARCH_ONLY.** This is an opt-in diagnostic for the Japanese Linux native recompilation. The tool upgrades the **already-installed v2** research instrumentation in the user's private, ignored generated C. It does not change the original ROM, game data, GPU/RT64 or any runtime settings. It requires independent testing on the user's private native build.

## Grounded v2 gameplay observations (18 November 2026)

The user reproduced the affected scene with the Japanese native executable and provided `[JP-MODEL2]` output. The original actor initializer (`0x8021D7C4`) and Object graphics dispatcher (`0x800167D4`) executed. Six `actor_id=0x00FB` instances were observed, divided across three consecutive scene groups. For one observed instance in each group, the tracked generation's `model_id` subsequently read as `0x0001` instead of `0x00FB`, with no `REINIT` record between those sampled observations; the same Object pointer remained bound. A separate `REINIT` record appeared later for one actor address. This is **not** proof that every actor allocation route was observed or that the `0x0001` value represents a rendering defect.

The native guest display-list cursor advanced consistently:

| Sampled state | `graphics_1` | Mode | Resolved candidate source | Commands produced in renderer call | `0x06` opcode count | `0x01` opcode count |
| --- | --- | --- | --- | --- | --- | --- |
| `model_id=0x00FB` | `0x18000420` | 1 | `0x803EB260` | 55 | 8 | 12 |
| `model_id=0x0001` | `0x4A000640` | 4 | `0x803A5680` | 8 | 2 | 2 |

For mode 1, hashes oscillated between two values across frames, suggesting that the emitted 8-byte words can vary in time; these differences have not yet been decoded. Mode-4 frame hashes also varied. A different hash alone cannot establish missing geometry, animation state or a graphics bug. The two sources are renderer-selected script/data inputs, **not verified ROM mesh files or display-list roots**. The captured command buffer is a native game RDRAM output; no RT64/RSP/GPU processing has been captured yet.

## What v3 adds

`jp_actor_model_trace_v3.py` validates the exact v2 helper SHA-256, the original JP 32-MiB decompressed ROM SHA-1 and the same seven original instruction anchors. It verifies the separate v2 actor/renderer C function signatures and the renderer wrapper, and adds **read-only, bounded full 8-byte command-word dumps** inside the existing v2 guest-command-window collector:

- Only **modes 1 and 4** and only the **first two nonempty windows for each mode** are eligible. Other modes and subsequent windows continue to use v2 summary-only logging.
- Only windows of **1–64 commands** are dumped (the observed modes have 55 and 8). At most 4 windows / 256 commands / 2,048 bytes of guest commands are read by the added logging across the full process. Counts are process-wide.
- Every trace has a `BEGIN` line (actor, generation, model, mode, window bounds), indexed `CMD` lines (`w0`, `w1`), and an `END` line. The underlying guest display-list buffer is not modified.
- It automatically creates `funcs_50.c.pre-model-trace-v3` before updating the exact actor-side generated C. `funcs_8.c` and the v2 renderer wrapper remain unchanged. The backup is refused if already present, and a repeated upgrade is refused.
- The `GOEMON_JP_ACTOR_TRACE=1` flag is still required. With tracing disabled, the added code is not entered.

The offline `analyze_jp_gfx_windows.py` parser accepts at most a 32-MiB log and strict complete `BEGIN/CMD/END` blocks. It prints only opcode counts and differences between mode-specific samples; it does **not** print raw command words or actor addresses. This helps separate structural opcode changes from dynamic command parameters without making unsupported claims about RT64.

## Execute in the existing Ubuntu Japanese recompilation checkout

The user has the correct directory and successfully built v2:

```bash
cd ~/Goemon64Recomp-JP

git fetch origin research/japan-native-actor-model-trace-20261118
git rev-parse FETCH_HEAD

git show FETCH_HEAD:tools/japan_port/jp_actor_model_trace_v3.py \
  > /tmp/jp_actor_model_trace_v3.py
git show FETCH_HEAD:tools/japan_port/analyze_jp_gfx_windows.py \
  > /tmp/analyze_jp_gfx_windows.py

python3 /tmp/jp_actor_model_trace_v3.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --generated-dir build-generated/japan/RecompiledFuncs \
  --dry-run
```

**Only after `validated only`:**

```bash
python3 /tmp/jp_actor_model_trace_v3.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --generated-dir build-generated/japan/RecompiledFuncs \
  --confirm-upgrade-private-generated-c

cmake --build build-generated/japan-native-lib \
  --target GoemonRecompiledJapan -j4
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP -j4

GOEMON_JP_ACTOR_TRACE=1 \
  ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-model-trace-v3.log"
```

After visiting the map `0x0003` robot area and closing the game:

```bash
python3 /tmp/analyze_jp_gfx_windows.py "$HOME/goemon-jp-model-trace-v3.log"
```

The analyzer is the best initial shareable output. To inspect the original full guest command words privately, use `grep -F '[JP-MODEL3]' "$HOME/goemon-jp-model-trace-v3.log"`, but do not commit or publish raw command dumps. If the game crashes, reproduce without `GOEMON_JP_ACTOR_TRACE=1` and restore the auto-created v3 backup, then rebuild the Japanese archive and frontend. Never run the v1 or v2 upgrader again on a v3 source.

## Verification limits

- 23 existing v1/v2/v3 research tests and 7 new offline-parser tests passed locally, including compiled synthetic host-C fixture verifying the v3 words, sample quotas and disabled environment mode. Python compilation checked. `--dry-run` against the user's real `funcs_50.c`, native Japanese relink and live v3 gameplay: **NOT RUN**.
- No exact-model file proof, matching-C acceptance, RT64 scene trace, original-emulator GBI comparison or confirmed rendering fix. Keep issue #13 open and draft PR #35 unmerged.