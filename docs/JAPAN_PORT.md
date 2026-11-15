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

