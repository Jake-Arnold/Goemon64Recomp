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

A fresh local split of the supplied ROMs produced:

| Check | USA baseline | Japan |
| --- | ---: | ---: |
| Decompressed ROM exact SHA-1 | Pass | Pass |
| Relocatable overlay sections scanned | 57 | 57 |
| Sections with symbolic candidates | 55 | 55 |
| ROM instruction words checked | 137,104 | 136,620 |
| R_MIPS_HI16 candidates | 2,858 | 2,907 |
| R_MIPS_LO16 candidates | 2,858 | 2,907 |
| R_MIPS_26 candidates | 389 | 380 |
| **Total relocation candidates** | **6,105** | **6,194** |

For the USA audit, the pinned `Goemon64RecompSyms/mnsg.syms.toml` contains **6,351** relocation records (2,981 HI16, 2,981 LO16, 389 MIPS26). All **70 USA overlay sections** were compared by candidate count and ordered-record fingerprints: **59 sections match their authoritative records exactly**, accounting for **4,696 records** (including 13 static overlays with zero relocations). There are **11 discrepant sections**, concentrated in `file_24`, `file_30`, `file_42`, `file_44`, `file_47`, `file_48`, `file_49`, `file_56`, `file_60`, `file_65` and `file_69`. In the USA check the scanner misses at least 248 expected records and emits two extra candidates compared with the authoritative per-section totals. These discrepancies may represent non-symbolic relocation sites or disassembly decisions; they require direct examination.

**Critical limitation:** The Japanese output is a provisional lower-bound candidate set and must not be treated as a complete N64Recomp relocation table. ROM-word and count checks do not prove all relocation decisions are correct. The **next gate** is to resolve the eleven discrepancy classes on USA, repeat the full address-aware audit for Japan, and integrate only validated metadata into Japan-specific recompilation symbols. No Japanese PC executable was generated by this step.

