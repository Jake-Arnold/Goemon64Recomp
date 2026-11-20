# Japanese native robot texture segment provenance — v16 (RESEARCH_ONLY)

## Evidence

The user reproduced the missing robot body using the native recompilation with the 32 MiB decompressed Japanese ROM. The v13 data from that mode showed two LoadBlock source addresses whose first 64 bytes were all zero: 0x0078B6E0 (16 records) and 0x007953D0 (8). Subtracting 0x003C4000 yields addresses with respectively 42/64 and 64/64 nonzero first bytes. Whole 4,096-byte TMEM nonzero counts dropped 3812→0 and 4096→0. The v15 offline analyzer showed source_tex equals the high source in both configurations, width=1, siz=2, uls=ult=0, and RDP LoadBlock byte offset zero. The suspected high addresses therefore predate the load offset calculation.

These observations are not proof that the lower addresses hold the correct full 32×64 RGBA16 texture. The high addresses are within the runtime's 8 MiB RDRAM allocation.

## Narrow experiment

The pinned RT64 (klorfmorf/rt64@abb3d7ad0ed60a8a74aa839222d4c107e828b7f5) calls RSP::fromSegmented(segAddress) in RSP::setTextureImage, then RDP::setTextureImage, which stores maskAddress(address). A wrong segment-table base, a wrong raw G_SETTIMG operand, or a mask/extension anomaly could each produce an unexpected texture-image address.

tools/japan_port/jp_rt64_texture_segment_v16.py changes only private lib/rt64/src/hle/rt64_rsp.cpp, requiring exact Git blob d4d9883e9bab98e0e44988a58ca5f6a06906890e and decompressed JP ROM SHA-1 6f8745fecc3a5e7d4918c7a73353eb0726116ded. It preserves the actual fromSegmented to RDP::setTextureImage sequence. After the actual state update, it logs when the resulting RDP image address is one of:

- High sources 0x0078B6E0, 0x007953D0
- Lower controls 0x003C76E0, 0x003D13D0

Logs record the raw segmented operand, segment index, segment base, 24-bit raw offset, base+offset, fromSegmented result, stored RDP address, format/size/width, and extension flag. Identical raw/base/RDP tuples are emitted once per thread, capped to 32 unique tuples. No memory bytes are logged. GOEMON_JP_RT64_TEX_TRACE=1 enables the diagnostic; otherwise the only effect is the semantically identical call structure. Original ROM data, guest commands, address arithmetic, RDP texture loading and rendering are unchanged.

## Run on Ubuntu

Run from ~/Goemon64Recomp-JP:

    git fetch origin research/japan-native-actor-model-trace-20261118
    git show FETCH_HEAD:tools/japan_port/jp_rt64_texture_segment_v16.py > /tmp/jp_rt64_texture_segment_v16.py
    python3 /tmp/jp_rt64_texture_segment_v16.py --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 --dry-run

Only after v16: validated only:

    python3 /tmp/jp_rt64_texture_segment_v16.py --rom build-generated/japan/baserom.decompressed.z64 --rt64-dir lib/rt64 --confirm-modify-private-rt64
    cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
    GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 python3 /tmp/launch_jp_decompressed_test_v14.py --rom build-generated/japan/baserom.decompressed.z64 2>&1 | tee ~/goemon-jp-texture-segment-v16.log
    grep -F '[JP-RT64] TEX_SEG_V16' ~/goemon-jp-texture-segment-v16.log

Play through the same failing robot scene. Save full log privately; only publish bounded metadata. Do not reinstall earlier v8–v14 probes or replace source files with older versions.

## Interpretation

- base plus raw 24-bit offset resolves to the high address: the high value is already present in a segment base/raw command combination. Compare that base against original emulator or game-script segment setup before changing anything.
- Raw segmented operand already specifies the high offset with ordinary base: investigate original graphics command generation and memory relocation.
- resolved, raw_plus_base, and rdp disagree: investigate RT64 extension/mask path. Some masking is intentional.
- No TEX_SEG_V16 lines even though v13 loads remain: state may have been set earlier/differently or via an RDP path not caught by this narrow RSP method. Absence of a hit is not proof none was set.
- Do not blindly subtract 0x003C4000 from all textures.

## Rollback

Only if v16 patch was the sole subsequent editor of the RSP source:

    cp lib/rt64/src/hle/rt64_rsp.cpp.pre-jp-texture-segment-v16 lib/rt64/src/hle/rt64_rsp.cpp
    cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4

## Verification boundary

9 local Python unittest cases passed, including compiled C++ code exercising the real injected function on disabled and enabled modes and deduplication. py_compile passed. Source Git blob pin confirmed via pinned upstream GitHub tree. Native Ubuntu RT64 build and gameplay remain unexecuted. RESEARCH_ONLY.
