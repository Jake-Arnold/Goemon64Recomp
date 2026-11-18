# Japanese native actor trace v2 — generation and per-draw guest Gfx windows

**Status: RESEARCH_ONLY.** This is a diagnostic of privately generated Japanese N64Recomp C, not a ROM patch, RT64 fix, actor model exporter or proof of equivalent original/N64 rendering. It upgrades the **already-applied v1 trace** in the user's existing `Goemon64Recomp-JP` build. Do **not** re-run the v1 injector after v2.

## Why upgrade

Native Japan user gameplay proved multiple live `actor_id=0x00FB` → `Task.heap_element` → renderer-`a0` bindings. Three actor slots were later sampled with model ID `0x0001` rather than initial `0x00FB`; v1 cannot tell if they were reinitialized. The two `graphics_1` words also identify distinct graphics modes, not simply mesh identifiers.

Independent original Japanese ROM MIPS disassembly (`0x800167D4` at ROM `0x173D4`) establishes:

- At `0x80016858`, the dispatcher loads `Object+0x2C`; `graphics_1 & 0x70000000` selects the graphics path, and `graphics_1 & 0x8FFFFFFE` is the candidate graphics-source address. The type `0x10000000` (`0x18000420`) uses the script-like path, while `0x40000000` (`0x4A000640`) calls `0x80019280`.
- For segmented values starting with `0x08...`, the original renderer indexes an eight-byte Object segment-base table starting at `Object+0x38`: base offset `0x38 + 8 * (segment - 8)`, plus the lower 24-bit offset. That is *not* a direct mesh-file-ID lookup.
- The original dispatcher at `0x80016FBC..0x80016FC4` advances a guest display-list command write cursor held in RDRAM at **`0x80161DBC`**; `func_800198D0` also writes through it. Capturing this cursor on dispatcher entry and return bounds the guest graphics commands emitted by that draw. This is **not yet** an observation of the eventual RT64/RSP submission.

The v1 user log therefore predicts these **candidate script/source** roots in live JP RAM:

| observed `graphics_1` | mode | segment | base from Object | resolved source |
|---|---:|---:|---|---|
| `0x18000420` | 1 | `0x08` | `0x803EAE40` | `0x803EB260` |
| `0x4A000640` | 4 | `0x0A` | `0x803A5040` | `0x803A5680` |

These addresses can change with scene or load placement; runtime validation is mandatory. First two words are sampled from each valid candidate source, but **are not labelled GBI until independently decoded**.

## Precise safety limits

- Offline source transformer validates exact **Japanese 32 MiB decompressed ROM** SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded` and seven original MIPS instruction anchors.
- Requires **exact original v1 helper SHA-256** and exact original two function signatures. It refuses missing, duplicate, modified or already-upgraded instrumentation.
- Modifies only the two existing, ignored private files `funcs_50.c` and `funcs_8.c` (looked up by function signature, not hard-coded filename); no original ROM, RDRAM, RT64 or GPU mutations.
- The generated dispatcher has a call-local wrapper around the original recompiled function; it samples the guest write cursor before and after that function. This changes native host call structure but preserves the original guest function body. Runtime equivalence requires live testing.
- Tracks 256 actor slots; increments a per-address generation on every observed initializer. Logs `REINIT` if the same address previously represented a target actor. Samples changed `model_id` only on subsequent renderer entry for that generation. It cannot see all intermediate writes or detect allocation outside the original initializer.
- Captures a maximum of 256 eight-byte guest Gfx commands per draw, and six windows per actor / generation or source change. Pointer range, alignment and monotonicity checks prevent arbitrary RAM scans; a bad window is reported as `GFX_WINDOW_UNAVAILABLE` rather than dereferenced.
- FNV-1a and opcode counters of commands `0x06`, `0xDE`, `0x01`, `0xDA` are raw evidence; do **not** infer display-list state, triangle count, real matrix submission or RT64 culling without further investigation.
- Enabled only with `GOEMON_JP_ACTOR_TRACE=1`; no hooks, files or logging when disabled.

## Upgrade from the currently verified user environment

The user's checkout is `~/Goemon64Recomp-JP`; the existing private generated code has **v1 already installed**, and the exact native-library/frontend paths are already known. Do not regenerate or re-inject v1.

```bash
cd ~/Goemon64Recomp-JP
# Update the research branch; do not merge it into the playable branch.
git fetch origin research/japan-native-actor-model-trace-20261118
# Use the verified fetched commit (or FETCH_HEAD if its commit is printed/verified).
git show FETCH_HEAD:tools/japan_port/jp_actor_model_trace_v2.py \
  > /tmp/jp_actor_model_trace_v2.py

# Back up the already instrumented private C units before changing them.
cp build-generated/japan/RecompiledFuncs/funcs_50.c \
   build-generated/japan/RecompiledFuncs/funcs_50.c.pre-model-trace-v2
cp build-generated/japan/RecompiledFuncs/funcs_8.c \
   build-generated/japan/RecompiledFuncs/funcs_8.c.pre-model-trace-v2

python3 /tmp/jp_actor_model_trace_v2.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --generated-dir build-generated/japan/RecompiledFuncs \
  --dry-run
# Only after PASS:
python3 /tmp/jp_actor_model_trace_v2.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --generated-dir build-generated/japan/RecompiledFuncs \
  --confirm-upgrade-private-generated-c

cmake --build build-generated/japan-native-lib --target GoemonRecompiledJapan -j4
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_ACTOR_TRACE=1 ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-model-trace-v2.log"

# After leaving the area/closing the game:
grep -F '[JP-MODEL2]' "$HOME/goemon-jp-model-trace-v2.log"
```

## Interpret output

- `TARGET actor=... gen=N`: target ID observed in a specific initializer generation.
- `REINIT actor=... previous_gen=N`: generic loader entered again for an address previously observed as `0x00FB`; this is evidence of reinitialization, but not of the allocator's reason.
- `STATE_CHANGE actor=... gen=N model=...->...`: model/object memory fields changed between two draw entries **without a traced reinitialization** for that actor address. It is not proof that the model was literally switched by a specific code path.
- `SOURCE ... mode=... seg=... address=... words=...`: renderer-derived candidate graphics script/data source, with two leading guest-memory words, **not necessarily raw F3DEX commands**.
- `GFX_WINDOW ... commands=... fnv32=... op06=... opDE=...`: raw guest Gfx commands produced during this actor's dispatcher call. `commands=0` is evidence of no synchronous command emission in that call, not proof that nothing reached RT64.
- `GFX_WINDOW_UNAVAILABLE ...`: no bounded contiguous guest command range could be verified. This is not a graphics fault conclusion.

If an executable crashes, run without the environment variable and/or restore both `.pre-model-trace-v2` source copies and rebuild the two native targets. Keep raw per-game logs and the copyrighted/generated code private; publish only minimal sanitized metadata.

## Verification and remaining gates

Development session: eight new Python tests passed, including host-C compiled execution with a synthetic wordswapped 8 MiB RDRAM buffer, mode 1/segment 8 and mode 4/segment 10 source translation, display-list cursor emission, same-generation model change, reinit generation and disabled mode. The seven original v1 tests are maintained separately.

**Not performed:** injecting this upgrader into the user's actual `funcs_50.c`/`funcs_8.c`, rebuilding the exact full native Japanese Linux executable, or capturing/validating a real actor Gfx window or RT64 RSP-submission thread. These gates must pass before any graphics root-cause or production fix claim. The woman's/child's face defects remain independent cases.