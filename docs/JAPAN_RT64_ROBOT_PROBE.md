# Original-Japanese robot graphics — pinned RT64 dispatch probe

**Status: `RESEARCH_ONLY` (source-only, read-only, opt-in).** This is **not** a graphics fix, a ROM patch, a GPU draw-call profiler, an original-emulator trace or a matching-C promotion.

## Evidence and exact target

The native Japanese v3 trace recorded the following guest display-list operations for actor ID `0x00FB`, model ID `0x00FB`, `Object.graphics_1=0x18000420`: 55 top-level commands with eight `G_DL` calls; seven of those invoke known geometry in segment `0x08`. The game emitted a segment base `0x003EAE40` for segment 8, and both segments 11 and 12 were set to `0x787CA950` in the observed captured list. The 55-command output is not itself evidence of RT64 execution.

The **authenticated original normalized Japanese 16 MiB ROM** SHA-1 is `9843ee979b5f6c80f5eda85df0baed9ae7c4e73b`. Its compressed file `0x0197` decodes to 15,120 bytes, SHA-256 `470489e151c6375cdd4844084a4299e4a1f0809e8de5d7f7420832eda893041e`. Its seven display lists have exactly:

| Root offset | End (exclusive) | Command count | Encoded triangle calls | Texture-image segments |
| --- | --- | ---: | ---: | --- |
| `0x12F0` | `0x13F0` | 32 | 8 | 9 |
| `0x1420` | `0x1520` | 32 | 8 | 9 |
| `0x1538` | `0x1628` | 30 | 10 | 9 |
| `0x1640` | `0x16F0` | 22 | 2 | 10 |
| `0x1708` | `0x17F8` | 30 | 10 | 9 |
| `0x1810` | `0x18C0` | 22 | 2 | 10 |
| `0x1938` | `0x1C38` | 96 | 64 | 12, 9, 11 |
| **Total** | | **264** | **104** | |

The **pinned RT64 submodule revision** in the GitHub fork is `abb3d7ad0ed60a8a74aa839222d4c107e828b7f5`. Its `src/hle/rt64_interpreter.cpp` has blob SHA-1 `dccaa871f42671fad4dc65439155db5b4bbac27c`. The exact source's `Interpreter::processDisplayLists()` fetches an opcode, looks up the GBI function and runs it. The F3DEX GBI maps `0xB1` to `tri2`, which calls `RSP::drawIndexedTri` twice, and maps `0xBF` to `tri1`. The original pinned RSP increments `State::drawCall.triangleCount` after the early *cull-both* guard. That counter measures internal triangle accumulation; it does **not** prove GPU rasterization or visibility.

For F3DEX `0xFD` (`G_SETTIMG`), the pinned RT64 path is `GBI_F3D::setTextureImage` -> `RSP::setTextureImage` -> `RSP::fromSegmented` -> `RDP::setTextureImage`. Physical RDP masking uses `0x00FFFFFF` unless `extendRDRAM` applies. With segment bases `0x787CA950`, raw `0x0B000000` or `0x0C000000` **should** resolve to `0x007CA950`; this must still be observed live. Neither segment value is intrinsically proof of invalid geometry or texture data.

## What the probe does

`tools/japan_port/jp_rt64_robot_probe.py` first checks the **exact private Japanese decompressed 32 MiB ROM SHA-1** `6f8745fecc3a5e7d4918c7a73353eb0726116ded`, the *original RT64 interpreter Git blob SHA-1* and four unique code anchors. It refuses any modified/unknown RT64 interpreter, existing probe, or existing backup. It modifies only the **local ignored RT64 submodule source** `lib/rt64/src/hle/rt64_interpreter.cpp`; it does not commit a submodule-pointer change, modify guest memory, change RSP/RT64 algorithms or introduce new game hooks.

Runtime flag `GOEMON_JP_RT64_TRACE=1` enables processing-time logging. The probe samples at most **two complete executions of each of the seven lists** in the observed segment-8 memory area. It uses RT64's actual `DisplayList*` and `State::RDRAM` pointer to identify physically executed list offsets (not merely submitted pointers). It logs:

- `BEGIN`: entry into a verified list root, active segment bases and RT64 GBI variant;
- `TEX`: for each interpreted `G_SETTIMG`, its segment, raw address, RT64 segmented resolution, actual RDP texture address and whether those agree;
- `END`: actual RT64 interpreter command/mapping counts, original-ROM expected counts, triangle opcode totals, internal triangle-count deltas, ambiguous counter resets, texture mismatches, vertex and matrix opcode counts.

It cannot attribute GPU triangle visibility, texture-cache decoding, final culling, render-state scissoring, fragment discard or screenshot appearance. A correctly emitted and interpreted sequence can still display incorrectly. Absence of any `BEGIN` line could mean the RT64 source revision, segment base or selected scene differs, **not** that the original game model is absent.

## Run in the existing Linux Japanese checkout

Keep original v3 generated C; do not re-run its installer. Fetch only the tool from research PR #35:

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
git rev-parse FETCH_HEAD

git show FETCH_HEAD:tools/japan_port/jp_rt64_robot_probe.py > /tmp/jp_rt64_robot_probe.py
python3 /tmp/jp_rt64_robot_probe.py \
  --rt64-dir lib/rt64 \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --dry-run
```

If and **only if** the dry run says the pinned RT64 file and ROM both pass:

```bash
python3 /tmp/jp_rt64_robot_probe.py \
  --rt64-dir lib/rt64 \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --confirm-modify-private-rt64

cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP -j4

GOEMON_JP_RT64_TRACE=1 \
  ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-rt64-robot.log"
```

Visit Japanese map `0x0003` (Small Pink Robot) and exit normally. Then:

```bash
grep -F '[JP-RT64]' "$HOME/goemon-jp-rt64-robot.log"
```

No environment flag means no RT64 diagnostic output. **Do not override a hash or source mismatch**: a newer local RT64 version needs separate inspection and a new source-gated patcher.

## Restoration

A successful install automatically creates `lib/rt64/src/hle/rt64_interpreter.cpp.pre-jp-robot-probe`. To restore exactly the prior file:

```bash
cd ~/Goemon64Recomp-JP
cp lib/rt64/src/hle/rt64_interpreter.cpp.pre-jp-robot-probe \
   lib/rt64/src/hle/rt64_interpreter.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

Do not commit the modified RT64 submodule or ship a binary compiled with an active probe. Keep raw scene traces local; report only bounded `[JP-RT64]` metadata. This diagnostic belongs in a **draft research PR**, not a game release.

## Gates actually completed

- Exact original Japanese 16 MiB ROM source/file decoding: **PASS**, seven list bounds and resource SHA-256 independently verified against the user-uploaded ROM.
- Pinned RT64 source anchors: **PASS**, uniquely observed in GitHub at the commit above; exact source Git blob hash retrieved.
- Python tests and host-compiled synthetic C++ execution: **PASS** (10 tests). Disabled mode, two-sample quota, list start/end, triangle count, segment-C resolution, source drift and ROM rejection covered.
- Actual private RT64 submodule source modification, CMake native RT64 rebuild and user gameplay capture: **NOT RUN** here.
- RT64 GPU rasterization, missing limb reproduction with reference emulator, original-ROM matching-C proof and final rendering fix: **NOT RUN**.