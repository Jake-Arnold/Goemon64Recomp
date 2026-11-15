# Japanese native recompilation port

The goal is a **native** Japanese PC build of *Ganbare Goemon: Neo Momoyama Bakufu no Odori* alongside the existing USA *Mystical Ninja Starring Goemon* build.

This branch currently contains only **ROM validation, region parameters and a non-executable overlay inventory tool**. No Japanese N64Recomp output, PC binary or gameplay has been produced. Upstream USA code and build settings are deliberately unchanged.

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

**Observed from the project-supplied Japanese source snapshot:**
- 72 section candidates
- **7,351 Japanese function candidates**, uniquely mapped to sections
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

**Verified locally against the supplied Japanese ROM:** merged TOML parses correctly and contains **72 candidate sections**, **7,351 functions**, and **6,434 candidate overlay relocation records**. Ten focused synthetic unit tests passed for the relocation scanner and TOML merger. The output is intentionally kept outside the repository and should not yet be supplied to a shipping PC runtime or described as a completed recompile. No `N64Recomp` or `RSPRecomp` executable is bundled with the provided archives, so native generation is an independent upcoming build step.


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

