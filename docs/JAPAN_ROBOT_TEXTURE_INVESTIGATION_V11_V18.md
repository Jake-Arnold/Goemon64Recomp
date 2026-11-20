# Japanese native robot: texture / segment / TLB-mapping investigation (v11–v18)

**Status: RESEARCH_ONLY — updated 20 November 2026.** This is the canonical consolidated evidence ledger for the *Japanese native recompilation* rendering defect affecting the lowest-rank pink robot. Work is on `research/japan-native-actor-model-trace-20261118` and draft PR [#35](https://github.com/Jake-Arnold/Goemon64Recomp/pull/35), tracked by [issue #13](https://github.com/Jake-Arnold/Goemon64Recomp/issues/13). No game/RT64 rendering or memory mapping fix has been validated. The other affected actors (woman in red and child) remain separate/unexplained.

## Critical finding: v18 live user report

The user ran the SHA-1-gated, directly decompressed **32 MiB Japanese ROM** in the native recompilation with RT64 v18 instrumentation, then supplied the bounded `TEX_SEG_V16` and `TEX_ALIAS_V18` output from `~/goemon-jp-texture-alias-v18.log`. These are **user-observed game-run records**, not independently replayed by the author. The complete raw private log and actual native build transcript were not uploaded.

**Decoded texture-image commands and segment bases in the v18 session:**

| Raw G_SETTIMG address | Segment base at execution | RSP calculated address | Stored RDP address | Meaning |
| --- | --- | --- | --- | --- |
| `0x08000790` (seg 8, +`0x790`) | `0x003D0C40` | `0x003D13D0` | `0x003D13D0` | Lower comparison, observed once |
| `0x080019A0` (seg 8, +`0x19A0`) | `0x003C5D40` | `0x003C76E0` | `0x003C76E0` | Lower comparison, observed once |
| `0x0B000000` (seg 11, +0) | `0x7878B6E0` | `0x7878B6E0` | `0x0078B6E0` | Earlier failing high source, now traced to high segment base |
| `0x08001710` (seg 8, +`0x1710`) | `0x003CFCC0` | `0x003D13D0` | `0x003D13D0` | Second route to lower comparison |
| `0x0B000000` (seg 11, +0) | `0x787953D0` | `0x787953D0` | `0x007953D0` | Second earlier failing high source, high segment base |
| `0x0C000000` (seg 12, +0) | `0x787CA950` | `0x787CA950` | `0x007CA950` | v17 current-run empty-TMEM source |
| `0x0B000000` (seg 11, +0) | `0x787CA950` | `0x787CA950` | `0x007CA950` | Same source via segment 11 |

All seven reported rows had `fmt=0`, `siz=2`, `width=1`, `extend=0`, and `raw_plus_base == resolved`; RDP retained the low 24 bits for these virtual-looking high bases. The v16/v18 hook observes `RSP::setTextureImage` **after** the original RDP state update and performs no address substitutions. The exact raw `0x0B000000`/`0x0C000000` operands and their high bases show the high addresses predate RDP LoadBlock tile arithmetic; this does **not** establish whether the game-generated bases are legitimate TLB virtual aliases or incorrectly constructed pointers.

**v18 three-way RDRAM nonzero-byte counts**, observed twice (once from segment 12, once from segment 11) with identical values at texture-image-set time:

| RDRAM byte address | First 64 nonzero | Full following 4096 nonzero |
| --- | ---: | ---: |
| `0x007CA950` (RDP source, upper) | **0/64** | **0/4096** |
| `0x003CA950` (`0x007CA950 - 0x00400000`) | **30/64** | **1783/4096** |
| `0x00406950` (`0x007CA950 - 0x003C4000`) | **0/64** | **0/4096** |

This materially strengthens **a 4 MiB address-alias / missing guest TLB translation hypothesis** for the `0x787CA950` reference. It does **not** prove that `0x003CA950` is the correct full RGBA16 texture, that subtraction is the intended virtual-to-physical translation, that all actor defects share this cause, or that TMEM would decode correctly after rerouting. The v18 reads occur when a texture image is set, while v17's TMEM replay was recorded in a **different process/run**. No same-run TMEM replay result from v18 was supplied.

## Reproducible evidence chronology (do not conflate runs)

| Stage | Evidence | Correct interpretation |
| --- | --- | --- |
| Original Japanese model audit / v4–v7 | Authenticated file `0x0197`, seven nested F3DEX lists, **104 triangles** per list set; all reached RT64 CPU face-index / GameCall accounting | Geometry not simply missing from command generation; does not prove rasterized visibility |
| RenderDoc and v10/v11 | Original expected-opaque shell fragment sampled RGBA `(0,0,0,0)` and discarded; 32×64 decoded GPU texture blank in that capture. Same robot calls 140/144 use hash `0x8042C12B60EC2B4E`, and v11 TMEM queue had `0/4096` nonzero for that hash; contrast call 143 hash `0x4263CA7EF085E861` had `3550/4096` nonzero | At least this blank hashed CPU TMEM input predates GPU decoding. RenderDoc serials and descriptor slots are process-specific; a triangle count alone does not make a unique per-draw link |
| v12/v13, earlier high-load capture | High sources `0x0078B6E0` and `0x007953D0`, both 0/64 first bytes and whole-TMEM transitions `3812→0` and `4096→0`; lower controls `0x003C76E0` 42/64 and `0x003D13D0` 64/64. Each high/lower pair differed by `0x003C4000`; each appeared 16 and 8 times respectively | Strong address mismatch signature, but 64-byte sampling and repeated replay histories do not authenticate entire expected texture; high addresses are within 8 MiB RDRAM |
| v14 decompressed-ROM A/B | User reports **no visible improvement** using exact 32 MiB decompressed input in native recompilation rather than original compressed 16 MiB input | Runtime decompression is not necessary to reproduce the visible issue. Not proof that all memory states match across runs |
| v15, earlier high-load capture | `source_tex` exactly equals each high address; `LoadBlock` byte offset `0x0`, `width=1 siz=2 uls=ult=0`; formula matches | High addresses existed before the RDP load-offset arithmetic, rather than being introduced by it |
| v16 run (frames 1992–1997; analyzed by v17) | One lower RSP source `0x003D13D0` reported; **11** robot-hash uploads and **0** replay loads at the two earlier high addresses | Those earlier high addresses were not represented in *this* bounded history; a single v16 RSP event cannot prove an upstream bypass |
| v17 analysis of that same v16 run | **11/11** target hash snapshots had **0/4096** whole TMEM. All 11 recent-load histories contained high source `0x007CA950`, first64 `0/64`, `LoadBlock` index 104 and (in 5 histories) 106, causing whole-TMEM drops `3605→0` and `3550→0`; 352 total replay load rows, 32 per snapshot, no incomplete lists | `0x007CA950` is an immediate *observed* TMEM-clearing source in the v16 run. 16 appearances of the source across snapshots are not 16 independent actual load operations |
| v18 **new** run | Multiple upper and lower segmented `SetTextureImage` mappings, including `0x787CA950 → 0x007CA950`. Both upper-source 4 KiB comparisons all zero; 4 MiB-lower window has `1783/4096` nonzero; alternative minus-`0x003C4000` window all zero | Strong new evidence for an address/mapping mismatch. The v18 report alone does not include contemporaneous CPU TMEM hash replay or a graphical correction |

## Source-grounded address path

Exact pinned sources: `klorfmorf/rt64@abb3d7ad0ed60a8a74aa839222d4c107e828b7f5` and `klorfmorf/N64ModernRuntime@fc4592a31414daf0040c19907e0b1976b2e48a67`.

1. Original robot file `0x0197` emits segmented `G_SETTIMG` commands. The live v18 segments 11/12 have bases `0x7878B6E0`, `0x787953D0` or `0x787CA950`, depending on scene/command; segment 8 emitted corresponding lower addresses in the same v18 output.
2. `RSP::fromSegmented` computes `segments[seg] + (raw & 0x00FFFFFF)` (absent extension special case). `RSP::setTextureImage` forwards the result to `RDP::setTextureImage`; `maskAddress` reduces this to the physical-looking RDP address.
3. `RDP::loadBlock` captures `operation.texture = texture` when writing a deferred `LoadOperation`. `State::fullSyncFramebufferPairTiles` replays that operation, and `RDP::loadBlockOperation` reads the computed source directly from RDRAM. In v15 both earlier high sources had **zero** tile byte offset.
4. The pinned runtime has a stub `osMapTLB_recomp` (TODO) and TLB handling in `osVirtualToPhysical` is also TODO. This is a genuine implementation gap; no observation yet proves which guest TLB mapping Goemon intended for these specific pages. Do not infer a universal fixed offset from one address.

## Unresolved questions and next acceptance gates

1. **Guest mapping proof:** trace actual Japanese `osMapTLB` call arguments or guest TLB register state, and derive the virtual page mapping for each `0x787...` base. Determine whether `0x787CA950` should translate to `0x003CA950` and whether the `0x7878B6E0`/`0x787953D0` aliases are consistent with a dynamic mapping.
2. **Memory ownership / texture identity:** verify that the target 32×64 RGBA16 texels are expected to reside in the candidate physical window, via original emulator at equivalent scene/pose and/or verified file/decompression destination. The nonzero-byte count by itself cannot authenticate a texture.
3. **Same-run temporal proof:** collect both `TEX_ALIAS_V18` samples and the corresponding `TEX_REPLAY_TARGET`/`LOAD` for robot hash from the *same* process, or extend a bounded replay-time comparison. Current v18 RSP sampling and earlier v17 CPU TMEM replay cannot be assumed simultaneous.
4. **Fix only after mapping evidence:** implement faithful guest mapping/physical address handling at the proper runtime boundary; do **not** blindly subtract `0x00400000` or `0x003C4000` in RT64, patch ROM bytes, or globally remap all textures. Compare robot against original Project64/Mupen64 render and test unaffected actors.
5. **Other actors:** woman-in-red and child cases remain open independently. No proof yet of a common root cause or final rendering fix.

## Reproduction and trace tools

- [Original robot display-list audit](../tools/japan_port/audit_jp_robot_displaylists.py)
- [v13 high-address analyzer](../tools/japan_port/analyze_jp_rt64_high_address_v13.py)
- [v15 source vs tile-offset analyzer](../tools/japan_port/analyze_jp_rt64_texture_address_v15.py)
- [v16 segment provenance probe](../tools/japan_port/jp_rt64_texture_segment_v16.py)
- [v17 same-run TMEM analyzer](../tools/japan_port/analyze_jp_rt64_current_run_v17.py)
- [v18 opt-in RSP alias probe](../tools/japan_port/jp_rt64_texture_alias_v18.py)
- [v18 installation, rollback and limitations](JAPAN_RT64_TEXTURE_ALIAS_V18.md)

All ROMs, extracted binary resources, texture pixels, raw private logs and non-public generated C/ASM remain excluded from Git. No native game build or new gameplay execution was performed by the assistant for this documentation update. The latest evidence was supplied by the user in conversation and independently cross-checked for arithmetic and consistency against the pinned source path; no claim of independently reproduced gameplay is made.
