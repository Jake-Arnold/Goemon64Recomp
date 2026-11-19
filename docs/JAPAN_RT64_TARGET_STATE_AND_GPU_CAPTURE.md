# Goemon JP: narrow RT64 model-part transparency investigation (v9)

Status: **RESEARCH_ONLY**. Exact-source, ROM-gated, opt-in read-only RT64 diagnostic. No emulator/gfx code fix, ROM edit, shader edit, or GPU behaviour change.

## Evidence and revised scope

The user surveyed the Japanese native game and reported only **2–4 affected model appearances**, with **see-through sections**, rather than a global absence of meshes. The three previously documented types are a red-clothed woman, a child, and a low-level pink robot; the exact actor IDs of woman/child remain unverified. Keep these cases separate until demonstrated to have the same root cause.

Authenticated USA and JP ROMs have byte-identical relevant resource IDs `0x0197` (robot), `0x0152`, `0x0159` (empty), and `0x0339` (room). Their main dispatcher is semantically the same 683 MIPS instructions modulo relocated addresses/call targets. USA code and original-emulator output are valuable *reference oracles*, not reason to assume all actor animation state is equal across regions.

Live v4–v8 robot trace has proven 7/7 original nested lists, all 264 commands mapped, 104/104 encoded robot triangles through F3DEX handler, face-index creation, CPU draw-call accounting and unique host draw-command recording. No missing cull-gate, scissor, pipeline or segment-translation events. Repeated host recordings total 208 per sample but correspond to the same 104 source triangles and GameCall identities; they may represent ordinary repeated passes rather than a defect. **None of these stages establishes GPU visibility.**

## v9 fields and purpose

For each already tagged robot GameCall when `FramebufferRenderer::submitRasterScene` records the host indexed-triangle command, print one `[JP-RT64] TARGET_STATE` line containing: original `root/sample`, `frame/source_frame/call`, `target` index, guest framebuffer pair, actual color/depth image addresses, actual RT64 render-target addresses, face overlap, current F3DEX OtherMode H/L, alpha comparison, force blend, alpha-coverage flags, depth compare/update/zmode, GPU culling flag and raster scissor. Context is captured at actual host command recording, not guessed from source ROM alone. It can establish whether repeat recordings occur on the same or distinct target and which material-state tuples appear on affected robot surfaces. It **cannot** determine GPU alpha/depth pass/fail or pixel output.

Source security gates: exact decompressed Japanese retail ROM SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`, original pinned interpreter Git blob, deterministic v4→v8 interpreter and v7 state source, pinned original renderer Git blob `46289b1961b88f82f7d8437402e96881080bee96` from the v8 backup, exact installed v8 renderer transformation, no v9 backup. Only local private `lib/rt64/src/render/rt64_framebuffer_renderer.cpp` is modified, and its v8 bytes are backed up to `.pre-jp-target-state-v9`. If any gate fails, **stop**. A direct v9 attempt on v7 or a modified RT64 version must fail rather than patching arbitrary text.

### Install in existing Ubuntu Japanese checkout

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
for n in jp_rt64_robot_probe jp_rt64_triangle_gate_probe jp_rt64_face_index_probe jp_rt64_drawcall_account_probe jp_rt64_raster_handoff_probe jp_rt64_target_state_probe analyze_jp_rt64_target_state_v9; do
  git show "FETCH_HEAD:tools/japan_port/${n}.py" > "/tmp/${n}.py"
done
python3 /tmp/jp_rt64_target_state_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --dry-run
```

Only after `validated only`:

```bash
python3 /tmp/jp_rt64_target_state_probe.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --rt64-dir lib/rt64 --confirm-modify-private-rt64
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
GOEMON_JP_RT64_TRACE=1 ./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee ~/goemon-jp-rt64-target-v9.log
python3 /tmp/analyze_jp_rt64_target_state_v9.py ~/goemon-jp-rt64-target-v9.log
```

Go to the defective robot scene. The summary groups by distinct source GameCall and render-target identity, showing materials and whether calls repeat on different framebuffers. One original GameCall can contain multiple triangles, not necessarily one anatomical part; avoid assigning body parts based only on root offsets.

Restore v8 (only local research instrumentation):

```bash
cp lib/rt64/src/render/rt64_framebuffer_renderer.cpp.pre-jp-target-state-v9 \
   lib/rt64/src/render/rt64_framebuffer_renderer.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

## Actual GPU frame analysis on Linux: RenderDoc, Vulkan

The ChatGPT environment has neither the user's running native executable nor their GPU capture. A local RenderDoc frame is needed to test real GPU execution and pixel visibility. Prefer **one frozen scene containing an affected NPC and a nearby unaffected NPC**, with the see-through region clearly visible.

1. Ensure the native game is using **Vulkan** in its graphics settings. On Ubuntu, install RenderDoc (`sudo apt install renderdoc` if available in the configured repository) or obtain the Linux build from the official RenderDoc project. Start `qrenderdoc`.
2. In RenderDoc choose **File → Launch Application**; executable `~/Goemon64Recomp-JP/build-generated/japan-native-game/Goemon64RecompiledJP`, working directory `~/Goemon64Recomp-JP`. Add environment variable `GOEMON_JP_RT64_TRACE=1` (no native memory/GPU patch). Launch from RenderDoc rather than attaching after initialization.
3. Enter the problem scene and press **F12** to capture a single frame with the broken part visible. Save `.rdc` locally. Some Linux/NVIDIA Vulkan setups may need the RenderDoc Vulkan layer registered; follow the application's prompt to configure it. If overlays or key injection conflict, use the RenderDoc UI's **Capture Frame** control.
4. Open the capture. In **Event Browser**, locate indexed draws contributing to the NPC. In **Texture Viewer**, inspect the color and depth attachment *at the event*, not just the swapchain image. Use the **Mesh Viewer** (VS Input/VS Output) to check whether the intended geometry exists and its clip-space vertices are in view.
5. Select a pixel in the see-through section and open **Pixel History**. Evaluate whether intended fragments were generated, rejected by depth/stencil, discarded by alpha testing, or overwritten by later draws. Inspect **Pipeline State**: blend enables/factors, depth test and depth write, face cull mode, shader and scissor. Compare with an opaque part of the same model and an unaffected NPC in the same capture.
6. Repeat with a fixed original-JP emulator screenshot of the same pose/camera if possible. Matching geometry byte-for-byte does not guarantee texture/alpha/material state matches in the native RT64 pipeline.

Keep `.rdc` private initially: GPU captures may include proprietary textures/frames and can be large. Do not commit ROM bytes, extracted assets, raw game memory or GPU captures to the public repository.

### What would discriminate causes

- Missing geometry in the **VS Output** mesh viewer: investigate vertex/matrix transforms, backface orientation or indexing, despite 104 indexed triangles being recorded.
- Geometry in VS Output but pixel history shows **depth failure**: investigate Z compare/write/order or depth attachment state.
- Pixel history shows **alpha discard** or transparent output: investigate OtherMode alpha compare, coverage flags, blender and shader combiner.
- Correct on intermediary render target but absent on final backbuffer: investigate framebuffer selection, later overwrite, resolve/presentation and repeated target passes.
- Visible opaque part and invisible part share one `OtherMode` but differ vertex normals/winding: prioritise culling, transforms and per-triangle coverage over alpha assumptions.

**Tests run in this environment:** 10 Python unit tests including a compiled C++ synthetic context emitter; no actual native RT64 v9 build or GPU frame replay. No rendered fix claimed.