# Japanese native actor → graphics trace (opt-in; read-only)

This source-only research tool targets **the user's native Japanese Linux PC recompilation**, not Project64, Wine, or the original 16-MiB ROM. It changes only locally generated, ignored C files and never patches game memory or writes any ROM. The game is unchanged unless explicitly rebuilt with this instrumentation and launched with `GOEMON_JP_ACTOR_TRACE=1`.

## Corrected Japanese original addresses (18 November 2026)

The earlier Japanese actor initializer address `0x8021DE00` was **wrong**; it was an address in the middle of another original function. Previous manual debugger and script experiments at `0x8021DE70` were **not valid actor-ID sampling**.

The independently decompressed **Japanese rev-0 original 32 MiB ROM** was SHA-1 verified as `6f8745fecc3a5e7d4918c7a73353eb0726116ded`. Original `config/japan_0/splat.yaml` maps file_12 ROM `0x5CD620` to VMA `0x80212090`, so source offset `+0xB734` is **ROM `0x5D8D54`, guest `0x8021D7C4`**.

| Operation | Japanese VMA | ROM offset | Original instruction |
| --- | --- | --- | --- |
| Actor initializer entry | `0x8021D7C4` | `0x5D8D54` | `addiu sp,sp,-40` |
| A0 becomes actor pointer S0 | `0x8021D7CC` | `0x5D8D5C` | `move s0,a0` |
| Read actor ID | `0x8021D808` | `0x5D8D98` | `lhu t8,0(v0)` |
| Write actor ID `+0x5C` | `0x8021D814` | `0x5D8DA4` | `sh t8,0x5C(s0)` |
| Write model ID `+0x5E` | `0x8021D830` | `0x5D8DC0` | `sh t1,0x5E(s0)` |
| First instruction after stores | **`0x8021D834`** | `0x5D8DC4` | `lbu t3,-4780(t3)` |
| Object drawing dispatcher entry | `0x800167D4` | `0x173D4` | `addiu sp,sp,-112` |
| Graphics pointer at Object `+0x2C` | `0x80016858` | `0x17458` | `lw a3,0x2C(s0)` |

The earlier **USA** actor initializer `0x80218A54` was independently confirmed correct. The Japanese address error was not an expected cross-region offset.

## How the trace works

The Japanese actor initializer copies the incoming guest `a0` into saved `s0`, so the optional native instrumentation registers `ctx->r4` **at function entry** without reading incomplete actor state. Later, on entry to the Japanese object renderer, it reads bounded actor headers through the pinned native `MEM_H/MEM_W` macros and filters for `actor_id == 0x00FB` (the three static placements in map `0x0003`).

For each candidate it emits `TARGET_SEEN` with current `model_id` and `Task.heap_element` (`+0x18`). It emits `BOUND` and six `OVERLAY` records **only if** the draw-call argument `a0` equals the saved actor's object pointer. This is an observed live pointer equality; it does not assign a model ROM file. The renderer's Object graphics/overlay layout is still provisional for Japan and must be checked against screenshots or independent guest instructions. A child Object may render without direct pointer equality, so absence of `BOUND` is **not** a negative proof.

Captured private actor pointers are maintained in 256 bounded slots. The tracer does not follow object links, sample F3DEX commands, read arbitrary memory, create files, pause execution or interact with RT64. It logs once for each association or changed model / `graphics_1` value, avoiding per-frame spam.

## Setup in an existing native Linux build checkout

Use your existing checkout of `Jake-Arnold/Goemon64Recomp`; no Project64 files or Wine are involved. The native Japanese build must have already been generated and successfully built. The instrumentation is not an emulator plugin.

```bash
cd ~/Goemon64Recomp-JP
# From the feature branch containing this tool:
python3 -m unittest tools.japan_port.test_jp_actor_model_trace -v

python3 tools/japan_port/jp_actor_model_trace.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --generated-dir build-generated/japan/RecompiledFuncs \
  --confirm-modify-private-generated-c
```

The private generated directory may differ (`RecompiledFuncsJP`, etc.). The command checks the exact original Japanese ROM hash, the six original instruction anchors and **unique** generated C function signatures before modifying *any* file. It refuses a second application. Make a backup of the generated directory before applying experimental probes, or regenerate it to remove the hooks.

**Rebuild the Japanese static archive, then relink the Japanese executable** using your existing CMake build settings. The native target links `GOEMON_JAPAN_STATIC_LIB`; simply rebuilding the executable without recompiling this archive will not incorporate the trace. For a typical existing Ninja build:

```bash
cmake --build build-generated/japan-native-lib --target GoemonRecompiledJapan -j4
# Reconfigure the Japanese frontend only if the archive path or CMake cache changed.
cmake --build build --target Goemon64RecompiledJP -j4
```

The frontend build directory may be named differently; use the one already configured with `GOEMON_BUILD_JAPAN=ON` and `GOEMON_JAPAN_STATIC_LIB` pointing to the rebuilt archive. Confirm the final executable really links the rebuilt archive before treating absent output as meaningful.

```bash
# Launch from the repository root to preserve relative asset paths:
GOEMON_JP_ACTOR_TRACE=1 ./Goemon64RecompiledJP 2>&1 | tee "$HOME/goemon-jp-model-trace.log"
```

Enter Japanese map `0x0003`. If the actor is already loaded before the instrumentation starts, exit and re-enter or restart the scene. Relevant log lines look like:

```text
[JP-MODEL] LOADER_ENTRY JP=0x8021D7C4
[JP-MODEL] DRAW_ENTRY JP=0x800167D4
[JP-MODEL] TARGET_SEEN actor=0x........ actor_id=0x00FB model_id=0x.... object=0x........
[JP-MODEL] BOUND actor=0x........ model_id=0x.... object=0x........ gfx1=0x........ gfx2=0x........
[JP-MODEL] OVERLAY slot=0 file_id=0x.... vram=0x........
```

Only share redacted, relevant `[JP-MODEL]` lines. **Do not commit raw logs**, generated game C, ROMs, model assets or temporary binaries. Remove the instrumentation by regenerating the private C output and recompiling without the script (setting `GOEMON_JP_ACTOR_TRACE=0` simply disables its runtime effect).

## Verification limits

On the preparation host: original 32 MiB JP ROM SHA-1, all six opcode anchors, Python unit tests and synthetic compiled C path were checked. **The full Japanese native executable was not rebuilt or executed here**, because the source checkout, private recompiled archive, RT64 dependencies and GPU session are not available in this environment. Keep `Jake-Arnold/Goemon64Recomp` issue #13 open. The previous woman's intermittent face and the robot's missing geometry are distinct cases; no shared rendering root cause has been proven.