# Japanese RT64 robot raster v8 — unique GameCall accounting correction

**Status: RESEARCH_ONLY.** No graphics code, ROM, runtime hooks or GPU behaviour changed. This correction affects only `analyze_jp_rt64_raster_v8.py` and its tests.

## Observed diagnostic overcount

The user's live v8 summary showed `range=104`, `built=208`, and `gpu_command_recorded=208` in each of two samples. An examination of the sampled largest display list showed **one** `FACE_RANGE` (`frame=893`, `triangles=64`) and **two** `RASTER BUILT` / `DRAW_RECORDED` batches covering the **same six GameCall IDs** in that same frame. Their instance IDs differed by one and their per-call triangle partitions were identical (`4,8,6,20,18,8`). This is repeat recording of *one source range*, not another copy of the robot's mesh or a consequence of observing four NPCs.

The original v8 offline analyzer simply added every `overlap_tri` log occurrence, thereby inflating the unique source tally when RT64 recorded the same GameCall in multiple renderer passes. The corrected analyzer keys distinct original source contributions by `(root, sample, frame, call)`, correlates each renderer record with its source `FACE_RANGE`, and separately reports `raw_recorded`, `repeat_built` and `repeat_recorded`. Draw events have no `frame`/`call`, so the analyzer associates them with the preceding matching `RASTER BUILT` events through bounded FIFO matching using `(root, sample, instance, call_tri, overlap_tri)`. It reports warnings on unmatched/conflicting rows rather than guessing.

`built` and `gpu_command_recorded` now represent *unique source GameCall overlaps that were ever built/recorded* during the bounded capture. `raw_recorded` is the full sum of all observed host draw command recordings (including repeated passes). Duplicate recordings are not necessarily a rendering defect; legitimate framebuffer or scene processing may repeat them. This analyzer does **not** determine why a GameCall was processed twice or whether the second command was executed by GPU.

## Verification

- Six offline Python unittests pass, including a synthetic two-pass repeated GameCall fixture, a reused renderer instance ID across distinct GameCalls, two distinct frames/samples with identical call IDs, a split-overlap case, empty input, and malformed source range.
- Python compilation passes.
- Re-running the script on the user's actual full local Ubuntu log has **not** been performed here; the updated analyzer remains to be run against it.
- Live v4–v7 traces already confirm 104/104 guest triangles, cull-gate passes, face-index entries and GameCall conservation; there is no demonstrated CPU geometry loss. Actual GPU execution and visible pixels remain unverified.

## Ubuntu command

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
git show FETCH_HEAD:tools/japan_port/analyze_jp_rt64_raster_v8.py > /tmp/analyze_jp_rt64_raster_v8.py
python3 /tmp/analyze_jp_rt64_raster_v8.py ~/goemon-jp-rt64-raster-v8.log
```

No native build, ROM writes, source-patch upgrades or new gameplay capture is required for this correction.