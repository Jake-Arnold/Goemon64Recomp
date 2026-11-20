# Japanese robot source alias / mapped-address hypothesis — v18 (RESEARCH_ONLY)

## Source-grounded observations

The user's v17 analysis of the actual v16 decompressed-ROM gameplay log returned 11 robot-hash 0x8042C12B60EC2B4E uploads, all with whole CPU TMEM=0/4096. All 11 recent-load replay windows contained the same source 0x007CA950 dropping nonzero TMEM to zero, at index 104 (and five also at index 106). First 64 source bytes were zero. Neither previously observed high source 0x0078B6E0 nor 0x007953D0 occurred in the same recorded replay windows.

Earlier original-Japanese file-0x0197 robot RT64 probes showed segment-B/C base 0x787CA950 and texture references using those segments. RT64 can mask the corresponding RSP address to 0x007CA950. The pinned runtime klorfmorf/N64ModernRuntime@fc4592a implements neither osMapTLB_recomp nor TLB virtual-to-physical translation. A TLB or 4 MiB address alias is therefore worth investigating, but is NOT a demonstrated root cause.

## v18 read-only source probe

The installer tools/japan_port/jp_rt64_texture_alias_v18.py requires the exact already-installed v16 private RSP source, its pinned original backup, and the exact decompressed Japanese ROM (33,554,432 bytes; SHA-1 6f8745fecc3a5e7d4918c7a73353eb0726116ded). It modifies only the ignored private src/hle/rt64_rsp.cpp, after creating backup .pre-jp-texture-alias-v18. It does not change a texture address or rendering behavior.

With GOEMON_JP_RT64_TEX_TRACE=1 and a physical RDP texture-image address equal to 0x007CA950, v18 reports first-64-byte and whole-4096-byte nonzero counts at 0x007CA950 (high source), 0x003CA950 (4 MiB lower), and 0x00406950 (lower by 0x003C4000). All three checked ranges fit in the pinned runtime's 8 MiB. No raw bytes are emitted. v16's original bounded duplicate suppression remains in effect.

These samples are from RSP::setTextureImage, not the later CPU TMEM load replay. Changes between those moments cannot be excluded. A nonzero lower source is not proof it contains the correct RGBA16 texture or that subtracting an offset is a valid fix.

## Ubuntu

Fetch the already-installed v16 source verifier, the v18 upgrader and the v14 launcher into /tmp:

    cd ~/Goemon64Recomp-JP
    git fetch origin research/japan-native-actor-model-trace-20261118
    git show FETCH_HEAD:tools/japan_port/jp_rt64_texture_segment_v16.py > /tmp/jp_rt64_texture_segment_v16.py
    git show FETCH_HEAD:tools/japan_port/jp_rt64_texture_alias_v18.py > /tmp/jp_rt64_texture_alias_v18.py
    git show FETCH_HEAD:tools/japan_port/launch_jp_decompressed_test_v14.py > /tmp/launch_jp_decompressed_test_v14.py
    python3 /tmp/jp_rt64_texture_alias_v18.py --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 --dry-run

Only after it prints "v18: validated only":

    python3 /tmp/jp_rt64_texture_alias_v18.py --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 --confirm-modify-private-rt64
    cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
    GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 python3 /tmp/launch_jp_decompressed_test_v14.py --rom build-generated/japan/baserom.decompressed.z64 2>&1 | tee ~/goemon-jp-texture-alias-v18.log
    grep -E '\[JP-RT64\] TEX_(SEG_V16|ALIAS_V18)' ~/goemon-jp-texture-alias-v18.log

Visit the same robot. Keep source guards; never blindly subtract 4 MiB or 0x003C4000 in actual rendering.

## Rollback

Only after successful v18 installation, provided no subsequent edits to the RSP source:

    cp lib/rt64/src/hle/rt64_rsp.cpp.pre-jp-texture-alias-v18 lib/rt64/src/hle/rt64_rsp.cpp
    cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4

## Verification

Nine local synthetic Python source/guard tests and a standalone compiled C++ harness were run. The C++ harness verified the new alias counts from three known memory windows and no output when tracing is disabled. Actual native Japanese game build and gameplay were not run. RESEARCH_ONLY.

## Actual user v18 gameplay trace — 20 November 2026

The user successfully ran the v18 native decompressed-Japanese-ROM probe and reported all seven deduplicated `TEX_SEG_V16` lines plus two identical `TEX_ALIAS_V18` lines. The following exact bounded metadata are now **observed**, rather than hypothetical:

| Raw G_SETTIMG / segment base | RDP image address |
| --- | --- |
| `0x08000790`, seg8=`0x003D0C40` | `0x003D13D0` |
| `0x080019A0`, seg8=`0x003C5D40` | `0x003C76E0` |
| `0x0B000000`, seg11=`0x7878B6E0` | `0x0078B6E0` |
| `0x08001710`, seg8=`0x003CFCC0` | `0x003D13D0` |
| `0x0B000000`, seg11=`0x787953D0` | `0x007953D0` |
| `0x0C000000`, seg12=`0x787CA950` | `0x007CA950` |
| `0x0B000000`, seg11=`0x787CA950` | `0x007CA950` |

For both `0x007CA950` image-set observations: **high first64=0/64, whole4096=0/4096**; minus 4 MiB at `0x003CA950`: **30/64 and 1783/4096 nonzero**; minus `0x003C4000` at `0x00406950`: **0/64 and 0/4096 nonzero**. This strongly favors examining a 4 MiB alias / TLB mapping, but **no authoritative virtual-to-physical mapping nor intended texture identity has been proven**. `extend=0`; for all logged lines, `raw_plus_base=resolved` and RDP stored the corresponding low address. These are image-set-time reads, not the later TMEM replay-time samples.

Cross-run warning: 11/11 blank robot TMEM uploads and `0x007CA950` block loads were measured in the earlier v16 session, **not asserted from the above v18 grep**. See the [full consolidated ledger](JAPAN_ROBOT_TEXTURE_INVESTIGATION_V11_V18.md) for precise chronology, unresolved mapping gates and evidence limitations.
