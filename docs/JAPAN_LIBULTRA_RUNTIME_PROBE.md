# Japanese libultra native-runtime dependency probe

**Status:** research-only, 15 November 2026. Do not enable in the default JP build until console/PFS behaviour and runtime linkage have been tested.

## Observed baseline

The Japanese N64Recomp probe generated 7,376 candidate functions (72 sections and 6,434 candidate overlay relocations). The native Linux compilation passed for 145 C units, plus `lookup.cpp`, producing a 20.4 MiB x86-64 `libGoemonRecompiledJapan.a` archive from 146 objects.

`nm` finds **82 unresolved unique symbols** after subtracting definitions in the archive itself. These are a mixture of expected runtime/library functions and native-port blockers; an unresolved symbol is not automatically a defect. Of these, the following eight `*_recomp` symbols are not present in the pinned `librecomp/src` source files checked at `fc4592a31414daf0040c19907e0b1976b2e48a67`: `__osCheckId_recomp`, `__osContRamRead_recomp`, `__osContRamWrite_recomp`, `__osPfsRWInode_recomp`, `__osPfsSelectBank_recomp`, `__osTimerInterrupt_recomp`, `__osViSwapContext_recomp`, and `osPiWriteIo_recomp`. Platform functions could still be supplied elsewhere in the complete executable; final linking must establish that.

## Leaf-function experiment

An opt-in script, `tools/japan_port/experimental_libultra_leaves.py`, takes the SHA-1-verified Japanese decompressed ROM and **only** rewrites these three exact function symbol names in a separate candidate TOML. Their original MIPS machine code is still used by N64Recomp:

| Original symbol | JP VRAM | MIPS bytes | Experimental alias |
| --- | --- | --- | --- |
| `__osCheckId` | `0x8004CFC0` | `0xFC` | `jp_impl___osCheckId` |
| `__osPfsRWInode` | `0x8004D0BC` | `0x320` | `jp_impl___osPfsRWInode` |
| `__osPfsSelectBank` | `0x8004D3DC` | `0x6C` | `jp_impl___osPfsSelectBank` |

The experiment was run locally with the exact decompressed JP SHA-1 `6f8745fecc3a5e7d4918c7a73353eb0726116ded`:

- N64Recomp completed with code generation exit 0 and the same 7,376 function candidates.
- The output audit passed: 72 sections, 57 overlay indices and all 6,434 candidate relocations unchanged.
- Clang C17 compiled **145/145** generated C units; `lookup.cpp` also compiled; a separate native archive was produced.
- After accounting for definitions inside the archive, unresolved imports fell from **82 to 79**, removing exactly the three renamed `*_recomp` dependencies; **no new imports** were introduced.

This proves that original JP machine code exists and can be statically compiled for these three routines. It **does not prove** correct controller pak reads/writes, saved-game persistence, or PC runtime behaviour.

## Reproduction (research output stays ignored)

```bash
python3 tools/japan_port/experimental_libultra_leaves.py \
  --rom build-generated/japan/baserom.decompressed.z64 \
  --symbols build-generated/japan/japan-PROVISIONAL.syms.toml \
  --output build-generated/japan/japan-libultra-leaves.syms.toml
```

For an independent recompiler probe, copy `mnsg.japan.toml` to a local ignored file and change **both** `symbols_file_path` to the experimental symbols and `output_func_path` to a unique experimental directory. Run the pinned `N64Recomp` against that config. Do not overwrite the baseline generated functions.

## Why not recompile all missing libultra functions?

An eight-function diagnostic renaming experiment (including PFS controller I/O, timer/VI and PI routines) succeeded at generating C, but exposed **20** undeclared `*_recomp` direct calls, up from **15** in the untouched baseline, because those functions depend on lower-level platform services. For example, `__osContRamRead` calls SI DMA and message-queue services, `__osTimerInterrupt` calls timer/compare handlers, and `osPiWriteIo` calls raw PI I/O. Compiling all original MIPS routines indiscriminately is therefore **not** an appropriate substitute for native platform emulation.

The next runtime milestone is a link-accurate list of imports and behaviourally justified implementations for PI, SI/controller-pak, timer and VI operations, followed by a native title-screen smoke test. No incomplete aliases, blank stubs or ROM-derived sources should be committed as part of a playable release.
