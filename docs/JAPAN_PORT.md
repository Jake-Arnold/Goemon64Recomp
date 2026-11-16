# Japanese native recompilation port

The goal is a **native** Japanese PC build of *Ganbare Goemon: Neo Momoyama Bakufu no Odori* alongside the existing USA *Mystical Ninja Starring Goemon* build.

This branch now contains source-only preparation for **Japanese N64Recomp code generation**, plus verification and regression tools. A complete diagnostic Japanese N64Recomp pass has generated C output locally; **no Japanese playable PC executable or gameplay validation exists yet**. Upstream USA source/build configuration remains unchanged.

## Native code-generation milestone (15 November 2026)

A real run of the *exact* Goemon-pinned Linux `N64Recomp` binary (`07fcdac76da3e47105238d45defe83d56c2821f5`) completed with **exit code 0** against the user-supplied exact Japanese 32 MiB decompressed ROM. Its output includes native-compatible `funcs_*.c` files, `funcs.h`, `lookup.cpp` and `recomp_overlays.inl` in a private ignored workspace; **none of these generated game-code files are committed**.

- **72 sections** (entry, main, 70 overlays); **57 relocatable overlay sections** explicitly have `relocs` arrays, including empty arrays for `file_52` and `file_76`.
- **7,376 Japanese functions**, including 24 recovered from a C-designated Splat region and a ROM-verified split of two handwritten libultra routines.
- **6,434 candidate relocations** after Japanese BSS inclusion and ten reviewed graphics-segment exclusions.
- **No deliberate `ignored` functions** in the successful diagnostic configuration. The pinned N64Recomp symbol list recognises `send_mesg` and `handle_CpU` as OS functions supplied by the host runtime, so their handwritten exception code is not compiled directly.
- Only diagnostic warning: an ambiguous JAL target `0x801D0B90` in `func_800023F4_2FF4` fell back to runtime function lookup; an indirect tail call in `recomp_entrypoint` was also reported.

This is **not yet a native executable** and **not proof of runtime correctness**. Japanese boot, data/patch symbol compatibility, RSP execution, scene overlays, UI and saves must be tested with the PC runtime.

### Reproduce the exact Japanese all-assembly build inputs

From the root of a local `mnsg-japan` checkout that contains the verified Japanese decompressed ROM and `splat` environment:

```bash
python3 /path/to/Goemon64Recomp/tools/japan_port/fullasm_config.py \
  --japan-splat config/japan_0/splat.yaml \
  --output config/japan_0/splat.recomp-probe.yaml

python3 -m splat split config/japan_0/splat.recomp-probe.yaml
# If using the portable archived environment, invoke Splat via its own script
# with the bundled Python, PYTHONHOME, PYTHONPATH and LD_LIBRARY_PATH.

python3 /path/to/Goemon64Recomp/tools/japan_port/candidate_symbols.py \
  --japan-splat config/japan_0/splat.yaml \
  --asm-root build-generated/japan_recomp/asm \
  --output /tmp/goemon-japan/allasm-candidates.toml

python3 /path/to/Goemon64Recomp/tools/japan_port/refine_libultra.py \
  --rom config/japan_0/baserom.decompressed.z64 \
  --candidate-symbols /tmp/goemon-japan/allasm-candidates.toml \
  --output /tmp/goemon-japan/refined-candidates.toml

python3 /path/to/Goemon64Recomp/tools/japan_port/reloc_candidates.py \
  --asm-root build-generated/japan_recomp/asm \
  --splat config/japan_0/splat.yaml \
  --rom config/japan_0/baserom.decompressed.z64 \
  --output /tmp/goemon-japan/relocs.json

python3 /path/to/Goemon64Recomp/tools/japan_port/merge_candidate_symbols.py \
  --japan-splat config/japan_0/splat.yaml \
  --candidate-symbols /tmp/goemon-japan/refined-candidates.toml \
  --candidate-relocations /tmp/goemon-japan/relocs.json \
  --output /tmp/goemon-japan/japan-PROVISIONAL.syms.toml

python3 /path/to/Goemon64Recomp/tools/japan_port/probe_config.py \
  --rom config/japan_0/baserom.decompressed.z64 \
  --symbols /tmp/goemon-japan/japan-PROVISIONAL.syms.toml \
  --output-dir /tmp/goemon-japan/native-probe \
  --n64recomp /path/to/pinned/N64Recomp
```

The source Splat configuration remains unchanged; the separate all-ASM configuration converts **189 C-designated subsegments** into assembly, recovering **24 extra executable functions** previously missing from the symbol table. The `refine_libultra.py` tool checks exact ROM SHA-1 and instruction words at `0x4A204`, `0x4A2B8` and `0x4A2E8`, then splits `func_80049604_4A204` (0xE8 bytes) into `send_mesg` (0xB4 bytes) and `handle_CpU` (0x34 bytes). Both are recognized runtime-supplied libultra symbols in the pinned N64Recomp `src/symbol_lists.cpp`. The no-ignored-functions diagnostic run finished in under one second on the local host.

## Audio RSP proof: Japanese microcode is identical

The audio RSP microcode used by the existing USA PC port (`aspMain.toml`) was located **byte-for-byte unchanged** in the Japanese decompressed ROM:

| Parameter | USA | Japan |
| --- | --- | --- |
| ROM text offset | `0x546B0` | `0x54930` |
| Text size | `0xE20` | `0xE20` |
| RSP text address | `0x04001080` | `0x04001080` |
| RSP text SHA-1 | `21e05bb9b4b3611e0cc2374c3ad6cc26adf2b385` | Same |

The exact pinned `RSPRecomp` binary was run locally on both region-specific input configurations with the same `aspMain` name and original indirect branch targets. **Both processes exited 0, produced exactly 73,090 bytes of C++ output, and the generated `aspMain.cpp` files were byte-identical** (SHA-1 `12847fc9fac0b2d446d37a5bb8afc80d7da7c7e1`).

The `tools/japan_port/rsp_config.py` source-only helper strictly verifies both decompressed ROM revisions, byte-identical RSP task contents, and the original USA `aspMain.toml` format. It then writes a new Japanese RSPRecomp config pointing at the shifted Japanese offset and an output C++ file outside version control:

```bash
python3 /path/to/Goemon64Recomp/tools/japan_port/rsp_config.py \
  --usa-rom /path/to/mnsg/config/usa/baserom.decompressed.z64 \
  --japan-rom /path/to/mnsg/config/japan_0/baserom.decompressed.z64 \
  --usa-config /path/to/Goemon64Recomp/aspMain.toml \
  --output-config /tmp/goemon-japan/aspMain-japan.toml \
  --output-cpp /tmp/goemon-japan/rsp/aspMain.cpp

/path/to/pinned/RSPRecomp /tmp/goemon-japan/aspMain-japan.toml
```

This confirms **the existing audio RSP task does not need a separate Japanese translation**. It does not yet validate audio running inside the native PC runtime.

## Native compilation milestone: Linux static archive

The locally generated Japanese `RecompiledFuncsJP` passed a second real toolchain gate with Clang 17 and CMake/Ninja: **145 C translation units**, `lookup.cpp`, and a final **33 MiB `libGoemonRecompiledJapan.a`** archive, with **exit code 0**. The complete build used the exact source-ROM SHA-1, pinned N64Recomp header and the fork's `trace.h`. This is an object-code library, **not** an executable.

Source-only build support is in [`tools/japan_port/native_compile/`](../tools/japan_port/native_compile/README.md), which does not alter the USA CMake build. The dedicated `runtime_externs.h` declares 15 host ABI imports missing from the generated C header but deliberately provides no substitute implementations. A `nm -g` audit found 82 unresolved symbols across the archive (71 `*_recomp` runtime calls and 11 runtime/maths/dispatcher symbols); the eventual PC application must resolve all of them.

The ROM-free GitHub Actions metadata workflow passed **75 tests**, including synthetic native CMake archive compilation and missing-input rejection: <https://github.com/Jake-Arnold/Goemon64Recomp/actions/runs/43774274464>. Native gameplay, actual runtime linking, overlay activation and UI are still untested. No generated Japanese game code or object file was committed.

## Native runtime integration gates

The C++ ROM decompressor is now region-parameterised in `src/game/rom_decompression.cpp`. The existing USA `goemon64::decompress_mnsg` entrypoint is retained unchanged; `goemon64::decompress_mnsg_japan` uses Japanese file-table offset `0x58258`, game code `NG5J`, and CRCs `0x673A3EDC` / `0x2491ADFC`. The Japanese routine is **not yet registered in the launcher**, because a valid Japanese native executable must be linked first.

The source-only `include/goemon_rom_regions.hpp` records the XXH3-64 hashes of the original normalised 16 MiB images: USA `0xDB1BC7EE0E6BEBA1`, Japan `0xD526A3DB80EB7924`. The USA result exactly reproduces the current launcher `rom_hash` field. The Japanese name field in the N64 ROM is non-ASCII (Japanese encoded), so the future launcher should not blindly reuse `"MYSTICAL NINJA"`.

GitHub CI now compiles and runs `tools/japan_port/test_runtime_decompression.cpp` against the **real C++ decompressor implementation** with ROM-free synthetic USA and Japanese tables. It validates regional game codes, CRCs, file table handling, payload copies and output alignment. This is a structural regression, not the complete original-game ROM SHA proof.

### Isolated native Japanese library

An opt-in `tools/japan_port/native_compile/CMakeLists.txt` builds the privately generated Japanese C sources, using the pinned SDK's `recomp.h` and *declaration-only* runtime imports. A local Clang build produced `libGoemonRecompiledJapan.a` successfully. No game assets or generated C are committed. The archive is not itself a playable program.

The repository's `tools/japan_port/native_link_audit.py` can audit unresolved symbols:

```bash
python3 tools/japan_port/native_link_audit.py \
  --archive /path/to/private/libGoemonRecompiledJapan.a \
  --output /tmp/goemon-japan/native-link-audit.json
```

The archive audit recorded **82 unresolved unique external names** after internal definitions are removed: **71** `*_recomp` host-runtime functions, **6** libc/math functions and **5** recompilation dispatch/platform functions. This is a normal *link-preparation* status, not evidence of 82 missing game functions. The tool can also accept repeated `--provider /path/to/library.a` arguments to find which names a native runtime archive exports. Actual ABI compatibility and final linkage still require a real link test.

**Next gates:** link the generated Japanese C archive with the correctly pinned N64ModernRuntime and platform code; reconcile Japanese-specific patches and data symbol addresses; register a Japanese-only native `GameEntry`, overlay table and clean launcher path; then verify title screen, input, scenes, audio, saves and gameplay. Do not wire Japanese ROM selection to the existing USA executable.

## Verified input revisions (SHA-1)

| File | Expected SHA-1 |
| --- | --- |
| USA compressed .z64 | `df8083a54296b8c151917c5333e1c85f014a2a66` |
| USA decompressed 32 MiB | `6ea0ed71032ce08fc2745f412d84936382197494` |
| Japanese original byte-swapped .n64 | `b6386455c0b8f573e315976bbb47548cbafcedb3` |
| Japanese normalised .z64 | `9843ee979b5f6c80f5eda85df0baed9ae7c4e73b` |
| Japanese decompressed 32 MiB | `6f8745fecc3a5e7d4918c7a73353eb0726116ded` |

The Japanese source .n64 has `37804012` magic, which indicates *adjacent-byte-swapped* V64 encoding. File extension is not authoritative.

The Japanese internal game code is `NG5J` (USA: `NG5E`). Japanese ROM file-table entry begins at `0x58258` (USA: `0x57FD8`). Japanese decompressed header CRCs are `0x673A3EDC`, `0x2491ADFC` (USA: `0x9CC11F4B`, `0xABAA8538`). These constants are not interchangeable.

## Running the bootstrap

Use the user's local ROMs and a separate, ignored work directory. This repository never distributes game data.

```bash
python3 -m unittest discover -s tools/japan_port -p 'test_*.py' -v

python3 tools/japan_port/rom.py prepare \
  --japan "/path/to/Ganbare Goemon - Neo Momoyama Bakufu no Odori (Japan).n64" \
  --output /tmp/goemon-japan/baserom.z64

python3 tools/japan_port/rom.py decompress \
  --rom /tmp/goemon-japan/baserom.z64 \
  --rommy /path/to/mnsg/tools/rommy.py \
  --manifest /path/to/mnsg/config/japan_0/rommy.yaml \
  --output /tmp/goemon-japan/baserom.decompressed.z64 \
  --python /path/to/python-with-lzkn64

python3 tools/japan_port/inventory.py \
  --japan-splat /path/to/mnsg/config/japan_0/splat.yaml \
  --usa-splat /path/to/mnsg/config/usa/splat.yaml \
  --output /tmp/goemon-japan/overlay-inventory.json
```

The `--manifest` argument is required and must refer to the **Japanese** ROMMY manifest; it is not created automatically in the output directory.

## Findings and next milestone

The supplied Japanese decomp configuration contains 70 executable overlay *candidates* named `file_11` through `file_80`. All 70 have region-dependent ROM or RAM locations. Examples:

| Overlay | USA ROM | Japanese ROM |
| --- | --- | --- |
| file_11 | `0x587370` | `0x58CB60` |
| file_12 | `0x5C8770` | `0x5CD620` |
| file_13 | `0x5F6840` | `0x5FB610` |

The Japanese Splat YAML references `config/japan_0/reloc_addrs/reloc_addrs.txt`, **absent from the provided source archive**. Splat extraction nonetheless completed locally. These overlay candidates are not sufficient to claim valid N64Recomp sections, function boundaries, relocation targets or jump tables.

**Next:** reconstruct Japanese function/section/relocation metadata from the decompressed Japanese image and validated decomp mappings; generate independent Japanese recompiled functions and RSP code; then bring up a separate Japanese executable. The old USA symbol map and patches must not be reused as if addresses match.

Licensing: preserve upstream GPLv3 COPYING and credits. Never commit ROMs, extracted assets, generated game instructions, assembly, object files or runtime ROM data.

## Section candidate milestone

The local source archive was inspected with the `sections.py` helper:

```bash
python3 tools/japan_port/sections.py \
  --japan-splat /path/to/mnsg/config/japan_0/splat.yaml \
  --usa-splat /path/to/mnsg/config/usa/splat.yaml \
  --output /tmp/goemon-japan/sections.json
```

Observed: **72 candidate sections per region** (entry + main + 70 named overlays). **71 differ** in their recorded metadata (main + every overlay), while entry remains aligned. These counts agree with the 72 section declarations in the existing USA `Goemon64RecompSyms/mnsg.syms.toml`; the sample USA entry/main/overlay sizes match the Splat-derived spans. This is evidence for source-section structure, **not** proof of executable-function or relocation coverage. Japanese symbols must still be derived and validated independently.


## Candidate function inventory

The supplied Japanese Splat output was scanned for `nonmatching` function annotations and the first ROM/VRAM instruction comments. Data/BSS assembly files were excluded. Every candidate was checked against its Japanese section's ROM-to-VRAM correspondence and its declared byte size.

**Initial partial extraction (superseded by the all-assembly extraction above):**
- 72 section candidates
- **7,351 initial Japanese function candidates**, uniquely mapped to sections (now 7,376 after the all-ASM and libultra fixes)
- **0** mapping failures, **0** overlaps and **0** sections without functions
- 1,816,416 total function bytes in 2,329,376 bytes of candidate sections (about 78%; non-function bytes include data and padding)
- Candidate TOML generated and successfully parsed by Python `tomllib`

For comparison, the upstream pinned USA `mnsg.syms.toml` contains 7,376 function entries across 72 sections. This **does not** establish that the remaining Japanese code is fully covered.

Generate the Japan-only candidate symbol file locally after the Splat extraction:

```bash
python3 tools/japan_port/candidate_symbols.py \
  --japan-splat /path/to/mnsg/config/japan_0/splat.yaml \
  --asm-root /path/to/mnsg/asm/japan_0 \
  --output /tmp/goemon-japan/japan-candidates.syms.toml
```

The generated file must stay out of version control. This is a candidate **function** table only: `relocs` entries, required data symbols, indirect branches, and any functions omitted by extraction still need independent reconstruction. **No Japanese N64Recomp run or native PC boot is claimed.**


## Relocation-file clarification

The missing Japanese Splat `reloc_addrs/reloc_addrs.txt` is **not itself a complete N64Recomp relocation table**. The supplied USA counterpart is predominantly Splat disassembly overrides marked `MIPS_NONE` to suppress false-positive symbolic relocations (315 such entries, versus two explicit HI16/LO16 overrides). Its absence did not prevent Japanese Splat extraction. It must not be copied from USA.

The existing USA N64Recomp symbols contain **6,351 actual relocation entries** across 55 sections: 2,981 `R_MIPS_HI16`, 2,981 `R_MIPS_LO16` and 389 `R_MIPS_26`. Region-correct Japanese equivalents remain ungenerated. Distinguish these from disassembler false-positive suppression annotations.


## Symbolic overlay relocation recovery — verified locally

Run the region-scoped scanner using the decompressed ROM and extracted assembly:

```bash
python3 tools/japan_port/reloc_candidates.py \
  --asm-root /path/to/mnsg/asm/japan_0 \
  --splat /path/to/mnsg/config/japan_0/splat.yaml \
  --rom /path/to/mnsg/config/japan_0/baserom.decompressed.z64 \
  --output /tmp/goemon-japan/reloc-candidates.json
```

The scanner checks the SHA-1 from the region's Splat configuration; matches each annotated instruction to the exact ROM word; checks MIPS HI16, LO16 and J/JAL encodings; checks intra-overlay bounds, duplicate sites and HI16/LO16 counts. It accepts symbol expressions with a numeric addend. It intentionally excludes unaudited constants and symbol references in data tables.

A re-audit with the Japanese overlay BSS extents included changed the results substantially:

| Check | USA baseline | Japan |
| --- | ---: | ---: |
| Decompressed ROM exact SHA-1 | Pass | Pass |
| Relocatable overlay sections scanned | 57 | 57 |
| Sections with symbolic candidates | 55 | 55 |
| ROM instruction words checked | 137,104 | 136,620 |
| Raw symbolic relocation candidates | 6,355 | 6,444 |
| Reviewed false segmented-graphics references excluded | 4 | 10 |
| R_MIPS_HI16 retained | 2,981 | 3,027 |
| R_MIPS_LO16 retained | 2,981 | 3,027 |
| R_MIPS_26 retained | 389 | 380 |
| **Retained relocation candidates** | **6,351** | **6,434** |

The previous 6,105 / 6,194 counts excluded symbol targets in **overlay BSS**. That was a scanner error, not evidence of missing assembly. The overlay's `bss_size` must extend the valid target region while the relocation *site* remains in ROM-backed instructions.

For USA the retained 6,351 entries were checked against the pinned `Goemon64RecompSyms/mnsg.syms.toml` by their **type, site address and target address**, producing **70/70 exact sections and no missing or extra relocations**. Before exclusions, four spimdisasm symbolisations are false relocations for segmented graphics address calculations. They occur at `file_30` sites `0x080043E4/0x080043E8` and `file_56` sites `0x08001390/0x080013AC`. Those instruction contexts are byte-identical in Japan. The Japanese version has six additional reviewed references of the same graphics-address kind. Explicit exclusions are scoped to the **decompressed ROM's SHA-1**, not applied to arbitrary revisions.

The 6,434 Japanese records are nevertheless **candidates**, not an authoritative complete relocation map: independent Japanese instruction-level review and runtime tests remain necessary. Count matches on USA do not prove there are no additional Japanese false positives or unannotated references. No Japanese PC executable has yet been generated.

## Combined provisional N64Recomp symbol/relocation TOML

The `merge_candidate_symbols.py` command accepts the locally generated Japanese function TOML and verified-ROM relocation candidate JSON, validating region SHA-1, unique section names, relocation-site uniqueness, relocation target bounds and supported types. It outputs a TOML file that uses the same section/functions/relocs structure as the USA symbol file, but is explicitly labelled **INCOMPLETE**.

```bash
python3 tools/japan_port/merge_candidate_symbols.py \
  --japan-splat /path/to/mnsg/config/japan_0/splat.yaml \
  --candidate-symbols /tmp/goemon-japan/japan-candidates.syms.toml \
  --candidate-relocations /tmp/goemon-japan/reloc-candidates.json \
  --output /tmp/goemon-japan/japan-PROVISIONAL.syms.toml
```

**Initially verified:** merged TOML contained 72 candidate sections, 7,351 functions and 6,434 relocation candidates. The current refined symbol map contains **7,376 functions**, 72 sections and 6,434 relocation candidates; see the current milestone above. Ten focused synthetic unit tests passed for the relocation scanner and TOML merger. The output is intentionally kept outside the repository and is not ready for a shipping PC runtime. The pinned N64Recomp host tools were built by GitHub Actions, and native C code generation was then successfully exercised locally (see above).


## Exact USA difference audit and automated checks

After checking out the pinned `Goemon64RecompSyms` submodule, the same scanner can be run against the USA decompressed ROM and USA assembly output. For an exact record-level difference report:

```bash
python3 tools/japan_port/audit_relocations.py \
  --reference Goemon64RecompSyms/mnsg.syms.toml \
  --candidates /tmp/goemon-usa/reloc-candidates.json \
  --output /tmp/goemon-usa/reloc-differences.json
```

The report lists **missing and extra actual relocation triples** (type, site VRAM, target VRAM) for every section. This is the diagnostic input for reconstructing the still-ambiguous Japanese sites; it does not transfer USA addresses to Japan.

A dedicated GitHub Actions workflow (`.github/workflows/japan-port-metadata.yml`) executes Python metadata unit tests on PR changes without needing ROMs, extracted assets, or N64Recomp. Local checks confirmed **13 new synthetic tests** for relocation extraction, difference reporting and TOML merging. The earlier ROM tests are also included in workflow discovery.


## Shared audio RSP microcode and experimental N64Recomp input (15 November 2026)

The 0xE20-byte audio RSP program referenced by `aspMain.toml` is **byte-for-byte identical** in both verified compressed source ROMs. USA offset: `0x546B0`; Japanese offset: `0x54930`. The 3,616-byte audio microcode SHA-1 is `21e05bb9b4b3611e0cc2374c3ad6cc26adf2b385`. This permits reusing the current `aspMain` recompilation for this audio microcode. It does not prove that every RSP microcode or audio/game integration path is identical.

```bash
python3 tools/japan_port/verify_rsp.py \
  --usa "/path/to/Mystical Ninja Starring Goemon (USA).z64" \
  --japan "/path/to/Ganbare Goemon - Neo Momoyama Bakufu no Odori (Japan).n64"
```

The experimental region-specific `mnsg.japan.toml` points N64Recomp at a **separate generated directory** and the Japanese candidate map. It intentionally retains only the shared, region-independent overlay **identifiers**, not the USA symbol addresses or instruction patch. It is not incorporated into the native CMake executable.

Prepare all private inputs in one command from the extracted Japanese sources:

```bash
python3 tools/japan_port/prepare_japan_recomp.py \
  --japan-splat /path/to/mnsg/config/japan_0/splat.yaml \
  --japan-asm /path/to/mnsg/asm/japan_0 \
  --japan-decompressed-rom /path/to/mnsg/config/japan_0/baserom.decompressed.z64
```

The tool enforces the pinned SHA-1, **72 sections**, **7,351 functions**, **6,434 relocations**, and the expected overlay identifiers, and places the provisional symbol TOML and ROM in ignored `build-generated/japan/` paths. The combined provisional TOML was independently generated from the current supplied Japanese extraction and parsed successfully. It is 1,009,693 bytes before any further cleanup.

When a locally compiled `N64Recomp` executable is available, an **explicit exploratory trial** can be run with the same arguments plus `--run-recompiler --recompiler /absolute/path/to/N64Recomp`. A successful code-generation trial will still require relocation review, runtime integration, Japanese patch porting, boot tests, and gameplay verification before a playable PC port can be claimed.

For the exact USA regression gate, run:

```bash
python3 tools/japan_port/compare_relocations.py \
  --usa-relocations /tmp/goemon-usa/reloc-candidates.json \
  --reference-symbols Goemon64RecompSyms/mnsg.syms.toml
```

The USA comparison is 70/70 exact section relocation triples, **6,351 records**. **Japanese counts remain candidates**, because Japan lacks an independent ground-truth relocation map and native PC boot is not yet demonstrated.

### Next executable milestone

1. Compile N64Recomp from the upstream source (not included in the supplied archives) in a clean Linux checkout.
2. Run `prepare_japan_recomp.py` using the verified project-root resources and invoke the experimental Japanese N64Recomp input.
3. Audit missing symbols, generated code and unresolved indirect branches, preserving the USA build.
4. Only after code generation is independently validated, integrate a separate `Goemon64RecompiledJP` runtime and perform title-screen/gameplay validation.

No proprietary game bytes, extracted MIPS code or compiled game code should be committed to the GitHub fork.

## Pinned N64Recomp host toolchain and Japanese code-generation probe

The existing PC port pins its N64ModernRuntime submodule at `fc4592a31414daf0040c19907e0b1976b2e48a67`, whose nested N64Recomp revision is `07fcdac76da3e47105238d45defe83d56c2821f5`. We use that **exact** N64Recomp revision, not the latest upstream `main`, to reduce tool/runtime mismatches.

A ROM-free GitHub Actions workflow, `.github/workflows/japan-port-recompilers.yml`, builds Linux x86-64 `N64Recomp` and `RSPRecomp` and uploads both as a downloadable workflow artifact. The first run passed all build, pin and artifact steps: [pinned recompiler build](https://github.com/Jake-Arnold/Goemon64Recomp/actions/runs/43771738688). This is a **host toolchain build**, not a game port.

After regenerating the provisional Japanese symbol and relocation TOML with the latest scripts, create a diagnostic-only config outside the repository:

```bash
python3 tools/japan_port/probe_config.py \
  --rom /tmp/goemon-japan/baserom.decompressed.z64 \
  --symbols /tmp/goemon-japan/japan-PROVISIONAL.syms.toml \
  --output-dir /tmp/goemon-japan/native-probe
```

This strictly verifies the expected 32 MiB Japanese ROM SHA-1, the 72 Japanese sections, the exact `recomp_entrypoint` alias at `0x80000400`, 57 relocatable overlay names, and that the supplied metadata includes the expanded BSS relocation inventory. It creates:

- `japan.recomp.probe.toml` with Japanese-specific absolute input and output paths, no USA patches
- `japan.overlays.txt` for the 57 relocatable overlays
- `japan.probe-manifest.json` with source identity, candidate counts, and generated paths

After obtaining the workflow artifact's Linux `N64Recomp` binary, the same command can add `--n64recomp /path/to/N64Recomp` to execute a native code-generation **probe** and capture its exit status. Neither a generated TOML nor a successful tool invocation proves a playable game: remaining tasks include Japanese data symbols, indirect targets, RSP validation, overlay registration, an isolated Japanese runtime and gameplay tests.



## First linked native JP frontend, title, and opening-scene validation

On 16 November 2026 the fork was rebuilt in a separate local Linux target, `Goemon64RecompiledJP`, preserving the USA `Goemon64Recompiled` target. Both were compiled and linked successfully against the existing pinned runtime/frontend. The Japanese target uses `mnsg.jp` ROM identity, `Goemon64RecompiledJP` save/config namespace, `launcher-jp.rml`, its own generated JP `recomp_overlays.inl`, and deliberately does not register USA patch binaries.

Real Japanese game startup was tested under SDL/X11 and software Vulkan (Lavapipe) using the user-supplied normalised 16 MiB ROM. The launcher recognised the exact Japanese ROM; a Japanese title scene, Japanese Controller Pak selection menu, input response, a subsequent opening cinematic and original Japanese dialogue rendered and advanced. These are *real native game frames*, not an emulator or static illustration.

### Essential Japan-specific fixes

**Executable overlay registration.** Without the USA-only required patch, the Japanese loader `func_80001BA0_27A0` loaded code into RAM but did not register its active section with N64ModernRuntime. The call to `0x801D0B90` therefore aborted. A ROM-SHA1-gated source-only transformation, `tools/japan_port/jp_loader_hook.py`, injects the native `load_overlays` bridge into privately generated `funcs_0.c`. It uses the region-verified Japanese ROM file table at VRAM `0x80057658`, properly sign-extended as an N64Recomp GPR. The loader patch was tested through real native game startup; the initial unknown-function abort is gone.

**Audio signedness correction.** The native game then threw `std::bad_alloc` through `osAiSetNextBuffer_recomp` because the Japanese audio scheduler used the same unsigned clamp error already fixed in USA. The Japanese ROM instruction `0x00E3082B` at `0x80037F00` is replaced by `0x00E3082A` (`sltu` to `slt`) in `mnsg.japan.toml`. The pinned N64Recomp independently regenerated the function with `SIGNED(ctx->r7) < SIGNED(ctx->r3)` and completed with exit code 0. A local rebuilt binary then rendered the actual Japanese title and opening scenes without the allocation failure.

Reproduce the private native loader hook **after** generating Japanese C and before compiling it:

```bash
python3 tools/japan_port/jp_loader_hook.py \
  --rom /private/japan/baserom.decompressed.z64 \
  --source /private/japan/RecompiledFuncsJP/funcs_0.c \
  --output /private/japan/RecompiledFuncsJP/funcs_0.c \
  --in-place
```

Do not commit `funcs_0.c` or any other generated game code. The script refuses incorrect ROM revisions, missing loader functions, and repeated application.

### Remaining playability blocker

The native executable currently proceeds through introductory scenes, but a subsequent gameplay transition can fail at unresolved TLB-addressed function pointer `0x08000C18`. The USA version's `patches/required.c` includes region-specific corrections for functions involving TLB overlay tasks (`func_8001481C_1541C` and `func_8001198C_1258C`); their Japanese equivalents and relocation offsets need to be adapted and tested, without reusing the USA addresses. Free movement, scene transitions, combat and saving have **not** been fully verified. The Japanese port is **bootable and interactive but not yet confirmed fully playable**.
