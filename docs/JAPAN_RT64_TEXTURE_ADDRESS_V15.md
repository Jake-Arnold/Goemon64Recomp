# Japanese native robot TMEM address provenance — v15 (RESEARCH_ONLY)

## Observation (19 November 2026)

In the user's real JP v13/v14 replay log, two high RDRAM source addresses produced **24 stable records** across repeated captures:

| final source_start | count | first 64 bytes at high source | first 64 at source minus 0x003C4000 | whole-TMEM before -> after |
| --- | ---: | ---: | ---: | ---: |
| a | 16 | 0 | 42 | 3812 -> 0 |
| b | 8 | 0 | 64 | 4096 -> 0 |

Both high addresses are **inside the runtime's 8 MiB RDRAM**. The corresponding lower addresses are 0x003C76E0 and 0x003D13D0. High samples are all zero, while lower controls have data. These are 64-byte counts, not proof that the entire lower source ranges contain the intended model textures.

The user separately confirmed the missing robot body persists in the opt-in native decompressed-ROM v14 mode. Runtime ROM decompression is therefore not necessary for the visual defect.

## RT64 source path

At klorfmorf/rt64@abb3d7ad0ed60a8a74aa839222d4c107e828b7f5:
1. RSP::setTextureImage passes RSP::fromSegmented(segAddress) to RDP::setTextureImage; the conversion adds the current segment base to the offset unless the extension path applies.
2. RDP::setTextureImage stores the address via maskAddress. RDP::loadBlockOperation computes textureStart = loadTexture.address + ((uls << siz) >> 1) + ((width << siz) >> 1) * ult. RDP::loadTileOperation computes textureStart = loadTexture.address + (((uls >> 2) << siz) >> 1) + ((width << siz) >> 1) * (ult >> 2).
3. State::fullSyncFramebufferPairTiles replays the stored loadOp.texture through the RDP operations for CPU TMEM. v12/v13 instrumentation already logs all operands to reconstruct these addresses.

## Run

From ~/Goemon64Recomp-JP:

    git fetch origin research/japan-native-actor-model-trace-20261118
    git show FETCH_HEAD:tools/japan_port/analyze_jp_rt64_texture_address_v15.py > /tmp/analyze_jp_rt64_texture_address_v15.py
    python3 /tmp/analyze_jp_rt64_texture_address_v15.py ~/goemon-jp-decompressed-v14.log

The offline tool groups only the two suspicious source addresses by replay configuration. It prints source_tex, byte_offset, reconstructed source_start agreement, format/width/coordinates, texture hash and high/lower 64-byte counts. It does not print ROM or texture bytes or mutate the game.

If formula=MATCH and ORIGIN reports a high image base, the high address was present in loadOp.texture.address before replay tile arithmetic. Then inspect the original RSP::setTextureImage segmented operand, segment base and resolved address in the same robot call. If the load byte offset itself is large, inspect load tile coordinates and width/size instead. A formula mismatch invalidates the inference until investigated.

Do not blindly subtract 0x003C4000 from all textures: the lower 64-byte controls are insufficient to authenticate a complete valid RGBA16 texture.

## Verification

Nine local parser/RT64 address arithmetic unittest cases and Python syntax check passed. No native CMake build, ROM rebuild, gameplay trace or model fix performed. RESEARCH_ONLY.
