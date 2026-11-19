# Japanese native v14 — exact decompressed-ROM A/B input (RESEARCH_ONLY)

This experiment compares the **same Japanese native executable, generated MIPS code, RT64 texture renderer and game scene** when the runtime receives the original Japanese compressed ROM versus the **already decompressed 32 MiB Japanese ROM**. The baseline execution path is unchanged. The opt-in test changes **only the input ROM and the runtime's need to decompress it**. It does not patch the original ROM, texture data, graphics commands, MIPS code, or the main game's stored ROM.

## Exact inputs and runtime authentication

| Input | Size | SHA-1 | XXH3-64 |
|---|---:|---|---|
| Japanese normalized original `.z64` | 16 MiB | `9843ee979b5f6c80f5eda85df0baed9ae7c4e73b` | `0xD526A3DB80EB7924` |
| Japanese decompressed `.z64` | 32 MiB | `6f8745fecc3a5e7d4918c7a73353eb0726116ded` | `0xC519E0E26FA0D20E` |

The 32 MiB hash was derived independently by reproducing the ROM's 1,311 file-table entries, checking its **exact 32 MiB SHA-1**, then computing XXH3 using the same installed `libxxhash` algorithm used by pinned N64ModernRuntime. The original 16 MiB XXH3 was reproduced independently and matched the existing production `GameEntry` constant.

The Python launcher and installer each require the **exact 32 MiB SHA-1**. On test launch the native `GameEntry` is changed to expect the **exact 32 MiB XXH3**, so any other ROM is rejected by `recomp::select_rom`. `has_compressed_code=false`, `decompression_routine=nullptr`. Runtime `recomp::load_stored_rom` therefore passes the selected 32 MiB image to `set_rom_contents` directly. No output ROM is changed.

The test uses **`game_id=mnsg.jp.decomp-test`** and stores the ROM at `mnsg.jp.decomp-test.z64`, distinct from the normal `mnsg.jp.z64`. This also isolates save data by game ID. `mod_game_id` stays `mnsg.jp` and the native game and renderer code is identical. The launcher always uses `supported_games[0]`, so the mode *replaces* the sole registered JP entry **for that process only**; it does not register a second game or change the default launch.

## Install

Run in `~/Goemon64Recomp-JP`; these commands use the user-owned file already present in the private build tree. No file or asset is committed from local ROM storage.

```bash
cd ~/Goemon64Recomp-JP
git fetch origin research/japan-native-actor-model-trace-20261118
for name in jp_decompressed_runtime_test_v14 launch_jp_decompressed_test_v14; do
  git show "FETCH_HEAD:tools/japan_port/${name}.py" > "/tmp/${name}.py"
done

python3 /tmp/jp_decompressed_runtime_test_v14.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --main src/main/main.cpp --dry-run
```

The installer **fails closed** unless the input ROM has exactly the expected size, SHA-1 and big-endian N64 magic, the exact original main.cpp Git blob is present, both anchors match once, and no existing v14 backup exists. A passing dry run says `v14: validated only`.

Only after a passing dry run:

```bash
python3 /tmp/jp_decompressed_runtime_test_v14.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --main src/main/main.cpp --confirm-modify-private-main

cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

Retain the v8-v13 RT64 instrumentation as-is; it is not modified. Preserve the original `src/main/main.cpp.pre-jp-decompressed-rom-ab-v14` backup.

## Run exact decompressed-image test

```bash
GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 \
python3 /tmp/launch_jp_decompressed_test_v14.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --binary build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-decompressed-v14.log"
```

The Python launcher verifies the SHA-1 again and `execv`s the **same native executable** with `--test-decompressed-jp <absolute-ROM-path>`. The native process validates the image's exact XXH3, saves it under an isolated test name, and opens the normal JP launcher. Start the game and visit the same affected robot. Logs must include:

- `[JP-ROM-TEST] input=decompressed; expected_size=33554432; expected_xxh3=0xC519E0E26FA0D20E; no decompression`
- `[JP-ROM-TEST] Accepted exact expected XXH3 input; isolated stored ROM ready; launcher will use 32 MiB without decompression`

An error/rejection or missing proof line means the A/B test did **not** run successfully.

Run the **unchanged** baseline executable with no test flag:

```bash
GOEMON_JP_RT64_TRACE=1 GOEMON_JP_RT64_TEX_TRACE=1 \
./build-generated/japan-native-game/Goemon64RecompiledJP \
  2>&1 | tee "$HOME/goemon-jp-compressed-baseline-v14.log"
```

Normal startup still uses the 16 MiB `rom_hash=0xD526A3DB80EB7924`, `game_id=mnsg.jp` and `decompress_mnsg_japan`; the decompressed-mode import does **not** overwrite its ROM or saves.

If the previous v13 TMEM probe is installed, both logs may be analyzed with:

```bash
python3 /tmp/analyze_jp_rt64_high_address_v13.py "$HOME/goemon-jp-decompressed-v14.log"
python3 /tmp/analyze_jp_rt64_high_address_v13.py "$HOME/goemon-jp-compressed-baseline-v14.log"
```

## Interpretation

- **Missing robot shell in both modes:** runtime decompression of the compressed game ROM is not *required* to reproduce the problem. Continue inspecting the actual segment-base/texture-image address construction in native game code and RT64's RSP segment resolution, particularly the suspicious `+0x003C4000` relation. This does **not** prove precisely where that offset is added.
- **Shell appears only when using the decompressed input:** compare native `decompress_mnsg_japan`, file table, and `recomp::load_stored_rom` behavior. Check native runtime-derived image against exact 32 MiB SHA before assuming a graphics bug.
- **Test fails before gameplay:** cannot draw rendering conclusions. Investigate import/rejection and test's separate game ID, preserving the normal executable path.

**Important:** The native executable's game code was already generated from the 32 MiB decompressed ROM for **both** modes. This A/B test changes the **runtime ROM data source**, not the compiled MIPS code. A rendered image or same-run v13 trace is still needed to determine whether the missing shell persists; the input validation log alone cannot answer that question.

## Rollback

The installer never alters the original ROM and backs up only the exact `src/main/main.cpp`. Restore from its automatic backup **only if this probe is the sole subsequent editor of that file**:

```bash
cp src/main/main.cpp.pre-jp-decompressed-rom-ab-v14 src/main/main.cpp
cmake --build build-generated/japan-native-game --target Goemon64RecompiledJP -j4
```

The separate test game ID leaves an optional `mnsg.jp.decomp-test.z64` in the app's config directory; removal is not necessary to restore normal gameplay. Do not delete `mnsg.jp.z64` or normal saved games.

## Verification boundaries

- Local unit and synthetic compiled C++ tests check source guards, original mode, decompressed mode, rejected input and malformed arguments.
- The exact 32 MiB file SHA-1 and XXH3 were independently computed, but the local tool environment did not compile the entire real Ubuntu native executable or run gameplay.
- The source-only research script must **not** be merged as a production change until real native compilation and both gameplay modes have been validated.