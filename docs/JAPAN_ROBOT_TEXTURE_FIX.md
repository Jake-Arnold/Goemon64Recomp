# Japanese native robot body texture fix

The Japanese recompiler incorrectly relocated four pairs of instructions that construct a graphics operand. Removing those relocations restores the opaque pink shell in a native Linux gameplay comparison in Oedo Castle, map `0x0003`. The patch is scoped to the authenticated Japanese rev 0 ROM and uses the existing relocation scanner's exact-site exclusions.

## Address provenance

The robot setup constructs `0x08003B10` and passes it to `func_8021F4D4_5DAA64`. For selector 2, the original code at `0x8021F538–0x8021F54C` computes `object->asset_base + operand - 0x08000000` and stores the result in the selected object slot. The calls for slots 3 and 4 share the operand. The draw routine at `0x80019320–0x8001936C` emits those slots as F3DEX segments B and C, removing the KSEG0 prefix. RT64 then resolves the segmented texture and issues an ordinary RDP load.

Each of the four pairs below supplies that same operand to the setter for both slots. Splat's symbolic annotations interpret `0x08003B10` as an address into the current executable overlay. It is a graphics operand relative to the object's asset instead. Applying the overlay relocation first inserts the executable overlay's load base into the formula.

| Japanese overlay | HI16 site | LO16 site |
| --- | --- | --- |
| `file_32` | `0x080017E8` | `0x080017F4` |
| `file_32` | `0x08001F8C` | `0x08001F98` |
| `file_32` | `0x08003260` | `0x0800326C` |
| `file_74` | `0x080037C4` | `0x080037D0` |

In the side-by-side run, the game file table held model `0x0197` at `0x803B0900` and executable `file_32` at tagged address `0xC03AC000` (physical `0x003AC000`). The guest display lists recorded the following addresses:

| | Baseline | Corrected |
| --- | --- | --- |
| Operand passed to the setter | `0x803AFB10` | `0x08003B10` |
| Object slot computed by the setter | `0xF8760410` | `0x803B4410` |
| Segment B/C word emitted to the RSP | `0x78760410` | `0x003B4410` |
| Physical source selected by RT64 masking | `0x00760410` | `0x003B4410` |

The injected physical base changes with overlay placement. In v18 the recorded file `0x0197` base was `0x003EAE40`, so the original operand predicts `0x003EE950`. The bad address `0x007CA950` differs from that prediction by `0x003DC000`, a plausible executable overlay placement. The old run did not capture its file table, so that placement is inferred. `0x003CA950` is a separate RDRAM window. The two earlier high addresses also have a double-base signature, but those runs did not capture the operand and its owning overlay.

The guest separately maps overlay windows in `func_80001E50` at the call to `osMapTLB` at `0x80001F38`. It supplies PageMask 0, paired physical pages 0x1000 bytes apart and increments the virtual bases by 0x2000. The libultra routine at `0x800412B0` programs EntryHi and the two EntryLo registers before `tlbwi` at `0x80041344`. Those CPU mappings explain why overlay callbacks need their existing native bridge. The robot texture setter does arithmetic on an operand and emits a display-list segment. The erroneous `0x787…` value is produced by that arithmetic, so it needs no TLB entry or renderer remap.

## Validation

- Regenerated native C from the verified Japanese ROM and private Splat input with the pinned N64Recomp. The result had 72 sections, 7,376 functions and 6,426 relocation entries. Compiled the changed Japanese objects and relinked a separate executable against the existing Linux build. Both instances used isolated copies of the save and configuration.
- Tested map `0x0003` with the original compressed ROM. The baseline showed missing body surfaces. The patched build showed the pink robot's face and opaque shell. The blue robot, stage and player rendered in the same encounter.
- Read the emitted segment words in both processes. The corrected address had 4,068/4,096 nonzero source bytes and all 2,048 RGBA16 alpha bits set. RT64 replay recorded 4,068 bytes in TMEM after `LoadBlock` from `0x003B4410`. The 32×64 texture was decoded and added to the cache as `0x35F8C62C861D14BF`. A baseline replay captured the same failure shape at a separate allocation, `0x007A2150`, with zero TMEM bytes and the previously reported blank hash.
- Repeated the encounter with the verified 32 MiB ROM loaded directly. The same segment words and decoded texture hash were observed, and the pink body rendered in gameplay.
- The exact-site regression tests that the exclusion applies only to the registered ROM digest and preserves another use of the same operand. Nineteen focused tests and the native decompression regression passed. The full metadata suite had the same 11 historical probe errors and failures as the baseline. Full local workflow validation was limited by a missing repository secret for the Linux release jobs.
- The prior original-emulator comparison is user-reported. The other two reported actors and the file 74 setup path still need individual visual checks.

To build the correction in a separate Japanese checkout, follow the existing [native code generation instructions](JAPAN_PORT.md#pinned-n64recomp-host-toolchain-and-japanese-code-generation-probe), including the native hooks required by that checkout. Regenerate the private Japanese sources from this branch before rebuilding the Japanese archive and relinking `Goemon64RecompiledJP`. Run the game and compare the small pink swatting robot in Oedo Castle 1F, Silver Key Room.
