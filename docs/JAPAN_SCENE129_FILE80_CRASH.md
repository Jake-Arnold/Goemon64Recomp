# Japanese native scene 129 crash: file 80 data pointer relocation

## Evidence — GDB, 16 November 2026

User's live Ubuntu GDB report: `goemon-jp-scene129-crash.log`.
The crashing `[Game] GAME` thread faults inside the exact JP
N64Recomp function `func_0800046C_741ACC` at
`build-generated/japan/RecompiledFuncs/funcs_144.c:3273`:

```text
ctx->f4.u32l = MEM_W(ctx->r11, 0X0);
#0 func_0800046C_741ACC
#1 func_800343A4_34FA4
#2 func_80002E9C_3A9C
#3 func_80001FE0_2BE0
#4 func_80000A98_1698
```

In the exact decompressed JP ROM
SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`,
the crashing function lives in `file_80` (ROM
`0x741660..0x742270`, Splat vram base `0x08000000`).
Its MIPS instruction at ROM `0x741C20` is
`lwc1 $f4, 0($t3)` and the address is derived from a
`0x08000B3C` pointer table, indexed by a small model index.
The host trace includes `rcx=0x880008f0`, consistent with
an unrelocated `0x080008F0` pointer being used as a native RDRAM
address; the GDB capture does not directly print `ctx->r11`,
so treat the exact `r11` value as an inference, not a measured fact.

### Exact file 80 inventory

The ROM file table gives file ID **80**, ROM start `0x741660`,
end `0x742270`, total size `0xC10`. The data section begins
at ROM `0x741F50` (offset `0x8F0`).

The entire data section was scanned for aligned words in the overlay's
`0x08000000..0x08000C10` range; **exactly six** were found:

| Overlay site offset | Original pointer | Target offset |
| --- | --- | --- |
| 0xB3C | 0x080008F0 | 0x8F0 |
| 0xB40 | 0x08000920 | 0x920 |
| 0xB44 | 0x08000974 | 0x974 |
| 0xB48 | 0x080009B0 | 0x9B0 |
| 0xB4C | 0x08000A28 | 0xA28 |
| 0xB50 | 0x08000A94 | 0xA94 |

The pinned N64ModernRuntime does not implement TLB address
remapping for these loaded overlay data pointers; the file 56
compatibility patch already employs the same pattern to fix 15
similar entries.

## Fix — v0.2.8-dev, experimental

`tools/japan_port/jp_file80_data_fixups.py` validates the entire
original decompressed Japanese ROM SHA-1, the file table, and the
complete six-pointer data section inventory before any generated
C changes.

The generated source patch modifies **only** file 80's six pointer
sites when the existing Japanese `jp_relocate_task_callbacks` hook
observes file ID 80 and the expected exact ROM bounds. It:

1. Resolves the loader's actual `base` destination.
2. Checks that all six currently loaded words are either their exact
   `0x0800...` original or already relocated `base+offset`.
3. Refuses partial relocation if **any** word is unexpected.
4. Rewrites only original values, allowing a retry without double
   relocation.
5. Preserves the existing file 56 15-pointer relocation.

No ROM modification. No USA change. No reset behaviour change.

`prepare_japan_recomp.py --prepare-native-hooks` now installs this
fix alongside the verified file 56 hook during **fresh** Japanese
code generation. For an already prepared Ubuntu workspace, patch
`funcs_8.c` in place once and rebuild the private JP static library
and then the native executable (without rebuilding/re-extracting ROM).

### Ubuntu testing — existing generated code

```bash
bash -e <<'SH'
cd ~/Goemon64Recomp-JP
git fetch origin fix/japan-scene129-file80-data
git switch fix/japan-scene129-file80-data 2>/dev/null ||
  git switch --track origin/fix/japan-scene129-file80-data
git pull --ff-only

python3 tools/japan_port/test_jp_file80_data_fixups.py

python3 tools/japan_port/jp_file80_data_fixups.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --source build-generated/japan/RecompiledFuncs/funcs_8.c \
  --output build-generated/japan/RecompiledFuncs/funcs_8.c --in-place

cmake --build build-generated/japan-native-lib --parallel 4
cmake --build build-generated/japan-native-game \
  --target Goemon64RecompiledJP --parallel 4

./build-generated/japan-native-game/Goemon64RecompiledJP --version
SH
```

Expected CLI version: `v0.2.8-dev (<git sha>) [timer-stage1]
[threads-audit] [guest-prep]`. Do not assume build success merely from
an older binary remaining on disk.

### Acceptance

- Enter **scene 129**, remain 30 seconds, exit, repeat 3 times.
- Japanese route that previously crashed in file 56 still works.
- Enemy/NPC models and HUD still render (existing face glitch is a
  separate open issue).
- No SIGSEGV. F8 remains diagnostic-only; game saves survive.
- On normal shutdown, timer worker prints its join message.

## Remaining uncertainty

The GDB trace proves the exact faulting function and floating-point
load, and the original ROM proves the six unrelocated data pointers.
The loader-time fix is a strong, bounded hypothesis consistent with
the earlier file 56 resolution. **Only a new user run can confirm
scene 129 is actually fixed.**

Native reset development continues in a separate branch. Following
this version, the reset milestone must use **v0.2.9-dev** or later.
